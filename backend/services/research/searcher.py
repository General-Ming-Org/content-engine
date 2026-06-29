"""Tavily/Serper search for opinion-rich practitioner sources."""
import asyncio
import hashlib
import uuid
from typing import Any

import httpx
import structlog

from config import get_settings
from services.research.queries import (
    SOURCE_PREFERENCES,
    SWEEP_MAX_STANCES,
    TAVILY_SEARCH_CONFIG,
    get_sweep_queries,
)

logger = structlog.get_logger(__name__)

SWEEP_ENRICH_CONCURRENCY = 1


def _tavily_params() -> dict[str, Any]:
    """Tunable search params — edit TAVILY_SEARCH_CONFIG and SOURCE_PREFERENCES in queries.py."""
    cfg = TAVILY_SEARCH_CONFIG
    prefs = SOURCE_PREFERENCES
    return {
        "days": int(cfg["days"]),
        "max_results": int(cfg["max_results"]),
        "search_depth": str(cfg["search_depth"]),
        "include_domains": list(prefs.get("include_domains", [])),
        "exclude_domains": list(prefs.get("exclude_domains", [])),
    }


async def search_tavily(query: str, max_results: int | None = None) -> list[dict[str, Any]]:
    """Search Tavily with opinion-source domain bias and recency window."""
    settings = get_settings()
    if not settings.tavily_api_key:
        logger.warning("tavily_not_configured")
        return []

    params = _tavily_params()
    async with httpx.AsyncClient(timeout=30) as client:
        body: dict[str, Any] = {
            "api_key": settings.tavily_api_key,
            "query": query,
            "search_depth": params["search_depth"],
            "max_results": max_results if max_results is not None else params["max_results"],
            "include_raw_content": False,
            "days": params["days"],
        }
        if params["include_domains"]:
            body["include_domains"] = params["include_domains"]
        if params["exclude_domains"]:
            body["exclude_domains"] = params["exclude_domains"]

        resp = await client.post("https://api.tavily.com/search", json=body)
        resp.raise_for_status()
        data = resp.json()
        return data.get("results", [])


async def search_serper(query: str, max_results: int = 8) -> list[dict[str, Any]]:
    """Serper fallback — no domain/recency filters (Tavily is preferred for opinion mining)."""
    settings = get_settings()
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


async def search(query: str, max_results: int | None = None) -> list[dict[str, Any]]:
    """Search with Tavily (opinion-tuned); fall back to Serper on failure."""
    params = _tavily_params()
    limit = max_results if max_results is not None else int(params["max_results"])
    try:
        results = await search_tavily(query, max_results=limit)
        if results:
            return results
    except Exception as exc:
        logger.warning("tavily_failed_falling_back", error=str(exc))
    try:
        return await search_serper(query, max_results=limit)
    except Exception as exc:
        logger.warning("serper_failed", error=str(exc))
        return []


def _dedupe_results(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for r in results:
        url = r.get("url") or ""
        fp = _url_fingerprint(url) if url else hashlib.md5(str(r.get("title", "")).encode()).hexdigest()[:12]
        if fp in seen:
            continue
        seen.add(fp)
        unique.append(r)
    return unique


def _url_fingerprint(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()[:12]


async def sweep(user_id: uuid.UUID, task_id: str | None = None) -> dict[str, Any]:
    """Opinion-mining sweep for one user: search → extract stances → gate → store."""
    from services.research.dedupe import archive_duplicate_topics
    from services.research.errors import ResearchProviderError
    from services.research.progress import progress_enriching
    from services.research.scorer import store_stance
    from services.research.stance_extractor import extract_stances_from_results
    from services.research.stance_gates import apply_stance_gates

    archived = await archive_duplicate_topics(user_id)
    if archived:
        logger.info("research_sweep_deduped_existing", user_id=str(user_id), archived=archived)

    queries = get_sweep_queries(user_id)
    tavily_params = _tavily_params()
    logger.info(
        "opinion_sweep_start",
        user_id=str(user_id),
        task_id=task_id,
        query_count=len(queries),
        tavily_days=tavily_params["days"],
        tavily_max_results=tavily_params["max_results"],
        include_domains=tavily_params["include_domains"],
        exclude_domains=tavily_params["exclude_domains"],
    )

    search_outcomes = await asyncio.gather(
        *[search(q) for q in queries],
        return_exceptions=True,
    )

    raw_results: list[dict[str, Any]] = []
    for query, outcome in zip(queries, search_outcomes):
        if isinstance(outcome, Exception):
            logger.error("opinion_search_failed", query=query, error=str(outcome))
            continue
        for r in outcome:
            r["search_query"] = query
        raw_results.extend(outcome)

    raw_results = _dedupe_results(raw_results)
    logger.info("opinion_sweep_raw_results", count=len(raw_results))

    if not raw_results:
        return {
            "status": "complete",
            "results_found": 0,
            "results_stored": 0,
            "results_skipped": 0,
            "skip_reasons": {"no_search_results": 1},
        }

    if task_id:
        progress_enriching(task_id, current=1, total=1, topic_title="Extracting stances…")

    try:
        stances = await extract_stances_from_results(raw_results)
    except ResearchProviderError as exc:
        logger.error("opinion_sweep_blocked_provider", title=exc.title, message=exc.message)
        return {
            "status": "blocked",
            "reason": exc.title,
            "message": exc.message,
            "results_found": len(raw_results),
            "results_stored": 0,
            "results_skipped": len(raw_results),
        }

    gated = apply_stance_gates(stances)
    if not gated:
        logger.info(
            "opinion_sweep_skipped_day",
            reason="no_debatable_stances_in_lane",
            extracted=len(stances),
        )
        return {
            "status": "complete",
            "results_found": len(raw_results),
            "results_stored": 0,
            "results_skipped": len(raw_results),
            "skip_reasons": {"no_debatable_stances": 1},
        }

    to_store = gated[:SWEEP_MAX_STANCES]
    stored = 0
    skipped = 0
    skip_reasons: dict[str, int] = {}

    for index, stance in enumerate(to_store, start=1):
        if task_id:
            progress_enriching(
                task_id,
                current=index,
                total=len(to_store),
                topic_title=stance.get("thesis", "")[:80],
            )
        try:
            topic = await store_stance(stance, user_id)
            if topic:
                stored += 1
            else:
                skipped += 1
                skip_reasons["duplicate"] = skip_reasons.get("duplicate", 0) + 1
        except Exception as exc:
            skipped += 1
            skip_reasons["error"] = skip_reasons.get("error", 0) + 1
            logger.warning(
                "stance_store_failed",
                thesis=stance.get("thesis", "")[:80],
                error=str(exc)[:500],
            )

    logger.info(
        "opinion_sweep_complete",
        stored=stored,
        skipped=skipped,
        extracted=len(stances),
        gated=len(gated),
    )
    return {
        "status": "complete",
        "results_found": len(raw_results),
        "results_stored": stored,
        "results_skipped": skipped + (len(gated) - stored),
        "skip_reasons": skip_reasons,
    }
