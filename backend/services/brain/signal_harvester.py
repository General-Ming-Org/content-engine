"""Tavily search for high-traction LinkedIn posts."""
from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlparse

import httpx
import structlog
from sqlalchemy import select

from config import get_settings
from database import AsyncSessionLocal
from models.brain import InspirationPost, UserVoiceProfile
from services.brain.queries import (
    HARVEST_MAX_STORE,
    LINKEDIN_TAVILY_CONFIG,
    RAW_CONTENT_FETCH_LIMIT,
    TRACTION_MIN_SCORE,
    focus_area_to_domain,
    get_harvest_queries,
)
from services.content.prompts import LINKEDIN_SIGNAL_SCORE_PROMPT

logger = structlog.get_logger(__name__)


def _dedupe_by_url(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for r in results:
        url = (r.get("url") or "").strip()
        if not url or "linkedin.com" not in url.lower():
            continue
        fp = hashlib.md5(url.encode()).hexdigest()
        if fp in seen:
            continue
        seen.add(fp)
        out.append(r)
    return out


async def _search_tavily(query: str, include_raw: bool = False) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.tavily_api_key:
        logger.warning("tavily_not_configured")
        return []

    cfg = LINKEDIN_TAVILY_CONFIG
    async with httpx.AsyncClient(timeout=30) as client:
        body: dict[str, Any] = {
            "api_key": settings.tavily_api_key,
            "query": query,
            "search_depth": str(cfg["search_depth"]),
            "max_results": int(cfg["max_results"]),
            "include_raw_content": include_raw,
            "days": int(cfg["days"]),
            "include_domains": list(cfg["include_domains"]),
        }
        resp = await client.post("https://api.tavily.com/search", json=body)
        resp.raise_for_status()
        return resp.json().get("results", [])


async def _search_serper(query: str) -> list[dict[str, Any]]:
    settings = get_settings()
    if not settings.serper_api_key:
        return []
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            "https://google.serper.dev/search",
            headers={"X-API-KEY": settings.serper_api_key},
            json={"q": query, "num": 5},
        )
        resp.raise_for_status()
        organic = resp.json().get("organic", [])
        return [
            {"title": r.get("title", ""), "url": r.get("link", ""), "content": r.get("snippet", "")}
            for r in organic
            if "linkedin.com" in (r.get("link") or "").lower()
        ]


async def _collect_focus_areas() -> list[str]:
    from services.brain.queries import default_focus_areas

    async with AsyncSessionLocal() as db:
        profiles = (await db.execute(select(UserVoiceProfile))).scalars().all()
    areas: set[str] = set()
    for p in profiles:
        if p.focus_areas:
            areas.update(p.focus_areas)
    if areas:
        return sorted(areas)
    return default_focus_areas()


async def _score_signals(
    results: list[dict[str, Any]], focus_areas: list[str]
) -> list[dict[str, Any]]:
    if not results:
        return []
    from services.ai.claude_client import generate_json

    prompt = LINKEDIN_SIGNAL_SCORE_PROMPT.format(
        focus_areas=json.dumps(focus_areas),
        results=json.dumps(results[:20], indent=2)[:8000],
    )
    try:
        data = await generate_json(
            task="linkedin_signal_score",
            system="Return only valid JSON.",
            user=prompt,
            max_tokens=2000,
        )
        return data.get("signals", [])
    except Exception as exc:
        logger.warning("linkedin_signal_score_failed", error=str(exc))
        return []


def _composite_traction(engagement_estimate: int, focus_match: bool) -> float:
    eng_norm = min(max(engagement_estimate, 1), 10) / 10.0
    relevance = 1.0 if focus_match else 0.5
    recency = 0.8
    return round(0.4 * recency + 0.3 * eng_norm + 0.3 * relevance, 3)


async def _url_exists(url: str) -> bool:
    async with AsyncSessionLocal() as db:
        existing = (
            await db.execute(select(InspirationPost).where(InspirationPost.url == url))
        ).scalar_one_or_none()
        return existing is not None


async def harvest_signals() -> dict[str, Any]:
    """Discover and store high-traction LinkedIn posts."""
    focus_areas = await _collect_focus_areas()
    queries = get_harvest_queries(focus_areas)
    if not queries:
        return {"status": "complete", "stored": 0, "reason": "no_queries"}

    import asyncio

    raw_batches = await asyncio.gather(*[_search_tavily(q) for q in queries])
    all_results: list[dict[str, Any]] = []
    for batch in raw_batches:
        all_results.extend(batch)

    if len(all_results) < 3:
        for q in queries[:2]:
            all_results.extend(await _search_serper(q))

    deduped = _dedupe_by_url(all_results)
    signals = await _score_signals(deduped, focus_areas)
    if not signals:
        return {"status": "complete", "stored": 0, "results_found": len(deduped)}

    ranked: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
    url_to_result = {(r.get("url") or ""): r for r in deduped}
    for sig in signals:
        url = sig.get("url", "")
        if not url or await _url_exists(url):
            continue
        focus_match = bool(sig.get("focus_area_match"))
        traction = _composite_traction(int(sig.get("engagement_estimate", 5)), focus_match)
        ranked.append((traction, sig, url_to_result.get(url, {})))

    ranked.sort(key=lambda x: x[0], reverse=True)
    top = ranked[:HARVEST_MAX_STORE]

    stored = 0
    raw_fetches = 0
    for traction, sig, raw in top:
        if traction < TRACTION_MIN_SCORE:
            continue
        focus_area = sig.get("focus_area_match") or focus_areas[0]
        hook = (sig.get("hook_preview") or raw.get("title") or "")[:200]
        full_text: str | None = None
        if raw_fetches < RAW_CONTENT_FETCH_LIMIT:
            query = f"site:linkedin.com {urlparse(sig.get('url', '')).path}"
            enriched = await _search_tavily(query, include_raw=True)
            for item in enriched:
                if item.get("url") == sig.get("url") and item.get("raw_content"):
                    full_text = str(item["raw_content"])[:4000]
                    break
            raw_fetches += 1

        post_id = uuid.uuid4()
        async with AsyncSessionLocal() as db:
            db.add(
                InspirationPost(
                    id=post_id,
                    url=sig.get("url", ""),
                    author_handle=sig.get("author_handle") or None,
                    hook_text=hook or "Unknown hook",
                    full_text=full_text,
                    focus_area=focus_area,
                    domain=focus_area_to_domain(focus_area),
                    traction_score=traction,
                    pattern_tags=None,
                    status="new",
                    harvested_at=datetime.now(timezone.utc),
                )
            )
            await db.commit()
        stored += 1

        from services.brain.pattern_extractor import extract_patterns_for_post

        await extract_patterns_for_post(post_id)

    logger.info("brain_harvest_complete", stored=stored, found=len(deduped))
    return {"status": "complete", "stored": stored, "results_found": len(deduped)}
