"""Extract practitioner stances from search results — the opinion layer of the pipeline.

Input: raw Tavily/Serper hits (title, url, content snippet).
Output: ranked structured stances ready for gating and drafting.
"""
import json
from typing import Any

import structlog

from services.content.prompts import STANCE_EXTRACTION_PROMPT
from services.research.queries import MY_FOCUS_AREAS

logger = structlog.get_logger(__name__)


def _format_results_for_prompt(results: list[dict[str, Any]]) -> str:
    payload = [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "snippet": (r.get("content") or "")[:1500],
            "search_query": r.get("search_query", ""),
        }
        for r in results
    ]
    return json.dumps(payload, indent=2)


async def extract_stances_from_results(
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Mine real opinions from search snippets. Returns empty list on failure or no opinions."""
    if not results:
        return []

    prompt = STANCE_EXTRACTION_PROMPT.format(
        focus_areas=json.dumps(MY_FOCUS_AREAS),
        results=_format_results_for_prompt(results),
    )

    try:
        from services.ai.claude_client import generate_json
        from services.research.errors import classify_provider_error

        data = await generate_json(
            task="stance_extraction",
            system=(
                "You extract debatable practitioner opinions from source text. "
                "Reject neutral summaries. Respond with JSON only."
            ),
            user=prompt,
            max_tokens=2048,
            temperature=0.2,
        )
    except Exception as exc:
        provider_error = None
        try:
            from services.research.errors import classify_provider_error

            provider_error = classify_provider_error(exc)
        except Exception as classify_exc:
            logger.debug("provider_error_classification_failed", error=str(classify_exc))
        if provider_error:
            raise provider_error from exc
        logger.warning(
            "stance_extraction_unavailable",
            error=str(exc)[:300],
            hint="TODO: wire LLM client or check API keys",
        )
        return []

    raw_stances = data.get("stances") if isinstance(data, dict) else []
    if not isinstance(raw_stances, list):
        return []

    stances: list[dict[str, Any]] = []
    for item in raw_stances:
        if not isinstance(item, dict):
            continue
        thesis = (item.get("thesis") or "").strip()
        if not thesis:
            continue
        stances.append({
            "thesis": thesis,
            "anti_position": (item.get("anti_position") or "").strip(),
            "evidence": (item.get("evidence") or "").strip(),
            "source_url": (item.get("source_url") or "").strip(),
            "topic": (item.get("topic") or thesis[:60]).strip(),
            "focus_area": (item.get("focus_area") or "").strip(),
            "debatability_score": float(item.get("debatability_score") or 0),
            "attribution": (item.get("attribution") or "").strip(),
        })

    stances.sort(key=lambda s: s["debatability_score"], reverse=True)
    logger.info("stances_extracted", count=len(stances), from_results=len(results))
    return stances
