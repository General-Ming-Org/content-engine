"""Tavily/Serper search integration with domain-balanced query rotation."""
import asyncio
import hashlib
from typing import Any

import httpx
import structlog

from config import get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()

# Rotating queries per domain — prevents staleness and ensures broad coverage.
DOMAIN_QUERIES: dict[str, list[str]] = {
    "ai_ml": [
        "latest AI ML research papers 2025",
        "LLM fine-tuning techniques benchmarks",
        "RAG retrieval augmented generation production",
        "AI inference optimization edge deployment",
        "multimodal models vision language production",
        "AI safety alignment techniques 2025",
        "vector databases embedding search performance",
        "AI agents tool use production systems",
    ],
    "software_eng": [
        "software architecture patterns 2025",
        "distributed systems consensus reliability",
        "database performance optimization techniques",
        "API design REST GraphQL gRPC comparison",
        "observability tracing metrics logs engineering",
        "platform engineering developer experience IDP",
        "Rust Go performance systems programming",
        "WebAssembly WASM production use cases",
    ],
    "sre_infra": [
        "Kubernetes production reliability patterns",
        "cloud cost optimization FinOps engineering",
        "incident management postmortem SRE practices",
        "eBPF Linux kernel observability 2025",
        "GitOps ArgoCD FluxCD production patterns",
        "service mesh Istio Linkerd Envoy comparison",
        "chaos engineering resilience testing",
        "SLO error budget burn rate monitoring",
    ],
    "data_eng": [
        "data lakehouse architecture 2025",
        "Apache Spark Flink streaming processing",
        "dbt data transformation analytics engineering",
        "data quality testing pipeline validation",
        "real-time analytics OLAP column stores",
        "Iceberg Delta Lake Hudi table formats comparison",
        "data mesh federated governance patterns",
        "MLOps feature store model serving production",
    ],
}

_query_counters: dict[str, int] = {domain: 0 for domain in DOMAIN_QUERIES}

SWEEP_ENRICH_CONCURRENCY = 1


def _sweep_limits() -> tuple[int, int]:
    """(results per domain, max topics to enrich) from env."""
    s = get_settings()
    per_domain = max(1, s.research_sweep_per_domain)
    max_topics = max(1, s.research_sweep_max_topics)
    return per_domain, max_topics


def _next_query(domain: str) -> str:
    queries = DOMAIN_QUERIES[domain]
    idx = _query_counters[domain] % len(queries)
    _query_counters[domain] += 1
    return queries[idx]


async def search_tavily(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    """Search Tavily and return raw results."""
    if not settings.tavily_api_key:
        logger.warning("tavily_not_configured")
        return []
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://api.tavily.com/search",
            json={
                "api_key": settings.tavily_api_key,
                "query": query,
                "search_depth": "advanced",
                "max_results": max_results,
                "include_raw_content": False,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])


async def search_serper(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    """Serper fallback search."""
    if not settings.serper_api_key:
        return []
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.serper_api_key, "Content-Type": "application/json"},
            json={"q": query, "num": max_results},
        )
        resp.raise_for_status()
        data = resp.json()
        organic = data.get("organic", [])
        return [{"title": r.get("title"), "url": r.get("link"), "content": r.get("snippet")} for r in organic]


async def search(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    """Search with Tavily; fall back to Serper on failure."""
    try:
        results = await search_tavily(query, max_results)
        if results:
            return results
    except Exception as exc:
        logger.warning("tavily_failed_falling_back", error=str(exc))
    return await search_serper(query, max_results)


def _url_fingerprint(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


async def sweep(task_id: str | None = None) -> dict[str, Any]:
    """Run a full research sweep across all four domains."""
    from services.research.dedupe import archive_duplicate_topics
    from services.research.deep_dive import enrich_topic
    from services.research.errors import ResearchProviderError
    from services.research.progress import progress_enriching
    from services.research.scorer import score_and_store

    archived = await archive_duplicate_topics()
    if archived:
        logger.info("research_sweep_deduped_existing", archived=archived)

    per_domain, max_topics = _sweep_limits()
    logger.info(
        "research_sweep_start",
        task_id=task_id,
        per_domain=per_domain,
        max_topics=max_topics,
    )
    all_results: list[dict[str, Any]] = []

    # Search all domains in parallel
    search_tasks = {
        domain: search(_next_query(domain), max_results=per_domain)
        for domain in DOMAIN_QUERIES
    }
    domain_results = await asyncio.gather(
        *[search_tasks[d] for d in DOMAIN_QUERIES],
        return_exceptions=True,
    )

    for domain, results in zip(DOMAIN_QUERIES.keys(), domain_results):
        if isinstance(results, Exception):
            logger.error("domain_search_failed", domain=domain, error=str(results))
            continue
        for r in results:
            r["domain"] = domain
        all_results.extend(results)

    if len(all_results) > max_topics:
        all_results = all_results[:max_topics]

    logger.info("research_sweep_raw_results", count=len(all_results))

    total = len(all_results)
    stored = 0
    skipped = 0
    skip_reasons: dict[str, int] = {}
    for index, result in enumerate(all_results, start=1):
        if task_id:
            progress_enriching(
                task_id,
                current=index,
                total=total,
                topic_title=result.get("title"),
            )
        try:
            enriched = await enrich_topic(result)
            if not enriched:
                skipped += 1
                skip_reasons["already_indexed"] = skip_reasons.get("already_indexed", 0) + 1
                logger.info(
                    "research_topic_skipped",
                    title=result.get("title"),
                    reason="already_indexed",
                )
                continue

            topic = await score_and_store(enriched)
            if topic:
                stored += 1
            else:
                skipped += 1
                skip_reasons["duplicate"] = skip_reasons.get("duplicate", 0) + 1
        except ResearchProviderError as exc:
            logger.error(
                "research_sweep_blocked_provider",
                title=exc.title,
                message=exc.message,
            )
            return {
                "status": "blocked",
                "reason": exc.title,
                "message": exc.message,
                "results_processed": stored + skipped,
                "results_found": len(all_results),
                "results_stored": stored,
                "results_skipped": skipped,
            }
        except Exception as exc:
            skipped += 1
            skip_reasons["error"] = skip_reasons.get("error", 0) + 1
            logger.warning(
                "research_topic_skipped",
                title=result.get("title"),
                reason="error",
                error=str(exc)[:500],
            )

    logger.info(
        "research_sweep_complete",
        stored=stored,
        skipped=skipped,
        skip_reasons=skip_reasons,
    )
    return {
        "status": "complete",
        "results_found": len(all_results),
        "results_stored": stored,
        "results_skipped": skipped,
        "skip_reasons": skip_reasons,
    }
