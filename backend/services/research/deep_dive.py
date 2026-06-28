"""Multi-source extraction + Claude synthesis for research enrichment.

LEGACY_SUBSTANCE_PATH: This module treats fetched URLs + snippets as substance to
neutralize via RESEARCH_SYNTHESIS_PROMPT. The daily opinion sweep uses
stance_extractor.py instead. See LEGACY_SUBSTANCE_PATHS.md before removing.

Two cache layers before we burn tokens:
  1. Vector DB check — if a recent topic is >85% semantically similar to this one,
     reuse its synthesis instead of re-fetching sources and re-synthesizing.
  2. Tavily MCP — sources come through the MCP search interface, which can serve
     cached results.

Claude calls go through `services.ai.claude_client` for model selection + prompt caching.
"""
import json
import re
from datetime import datetime, timezone
from typing import Any

import httpx
import structlog

from services.ai.claude_client import generate_json
from services.ai.vector_store import KIND_RESEARCH, get_vector_store
from services.content.prompts import RESEARCH_SYNTHESIS_PROMPT
from services.research.errors import classify_provider_error
from services.research.sanitize import sanitize_payload, sanitize_text

logger = structlog.get_logger(__name__)


async def _fetch_url_content(url: str) -> str | None:
    if url.lower().split("?")[0].endswith(".pdf"):
        logger.debug("pdf_fetch_skipped", url=url)
        return None
    try:
        async with httpx.AsyncClient(
            timeout=15,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"},
        ) as client:
            resp = await client.get(url)
            if resp.status_code != 200:
                return None
            text = resp.text
            text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return sanitize_text(text[:8000])
    except Exception as exc:
        logger.debug("url_fetch_failed", url=url, error=str(exc))
        return None


async def synthesize_topic(topic_title: str, sources: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Synthesize raw sources into structured notes via Claude."""
    sources_text = json.dumps(
        [{"title": s.get("title"), "url": s.get("url"), "content": s.get("content", "")[:2000]} for s in sources],
        indent=2,
    )
    prompt = RESEARCH_SYNTHESIS_PROMPT.format(topic=topic_title, sources=sources_text)
    try:
        return await generate_json(
            task="research_synthesis",
            system="You are a senior technical researcher. Respond with JSON only.",
            user=prompt,
            max_tokens=1024,
            temperature=0.3,
        )
    except Exception as exc:
        provider_error = classify_provider_error(exc)
        if provider_error:
            raise provider_error from exc
        logger.error("research_synthesis_failed", topic=topic_title, error=str(exc))
        return None


async def check_cache(topic_title: str, snippet: str) -> dict[str, Any] | None:
    """Look up the vector store for an existing synthesis on this topic.
    Returns the cached payload if a high-similarity match exists; None otherwise.
    """
    try:
        store = get_vector_store()
        hits = await store.search(
            kind=KIND_RESEARCH,
            query_text=f"{topic_title}\n\n{snippet}",
            limit=1,
        )
        if hits:
            top = hits[0]
            logger.info(
                "research_cache_hit",
                title=topic_title,
                cached_id=top["id"],
                score=top["score"],
            )
            return top["payload"]
    except Exception as exc:
        logger.debug("research_cache_unavailable", error=str(exc))
    return None


async def enrich_topic(raw_result: dict[str, Any]) -> dict[str, Any] | None:
    """Fetch sources and synthesize a raw search result into a structured topic.
    Short-circuits if the vector store already has a near-identical topic.
    """
    title = raw_result.get("title", "")
    url = raw_result.get("url", "")
    domain = raw_result.get("domain", "software_eng")
    snippet = raw_result.get("content", "")

    cached = await check_cache(title, snippet)
    if cached and cached.get("synthesis"):
        # Topic already synthesized and indexed — do not insert another row.
        logger.info("research_skipped_via_cache", title=title)
        return None

    source_urls = [url] if url else []
    if len(source_urls) < 3 and raw_result.get("related_urls"):
        source_urls.extend(raw_result["related_urls"][:2])

    sources: list[dict[str, Any]] = []
    for src_url in source_urls[:4]:
        content = await _fetch_url_content(src_url)
        sources.append({
            "url": src_url,
            "title": title,
            "content": content or snippet,
            "extracted_at": datetime.now(timezone.utc).isoformat(),
        })

    if not sources:
        logger.warning("no_sources_for_topic", title=title)
        return None

    synthesis = await synthesize_topic(title, sources)
    if not synthesis:
        return None

    if synthesis.get("confidence", 0) < 5:
        logger.info(
            "research_topic_skipped",
            title=title,
            reason="low_confidence",
            confidence=synthesis.get("confidence"),
        )
        return None

    return sanitize_payload({
        "title": title,
        "summary": synthesis.get("summary", ""),
        "sources": sources,
        "domain": domain,
        "synthesis": synthesis,
        "from_cache": False,
    })
