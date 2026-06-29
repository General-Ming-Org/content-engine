"""Pre-queue novelty checks — thesis and hook similarity."""
from __future__ import annotations

from typing import Any
from uuid import UUID

import structlog

from services.ai.vector_store import KIND_INSPIRATION, KIND_POSTS, KIND_RESEARCH, get_vector_store
from services.content.prompts import NOVELTY_ASSESSMENT_PROMPT

logger = structlog.get_logger(__name__)

THESIS_SIMILARITY_THRESHOLD = 0.88
HOOK_SIMILARITY_THRESHOLD = 0.85
NOVELTY_REGEN_THRESHOLD = 6


async def check_novelty(
    user_id: UUID,
    thesis: str,
    draft_content: str,
    domain: str,
) -> dict[str, Any]:
    hook = draft_content[:200]
    warnings: list[str] = []
    metadata: dict[str, Any] = {}

    store = get_vector_store()
    try:
        thesis_hits = await store.search(
            kind=KIND_RESEARCH,
            query_text=thesis,
            limit=3,
            score_threshold=THESIS_SIMILARITY_THRESHOLD,
        )
        if thesis_hits:
            warnings.append("thesis_similar_to_recent_research")
            metadata["thesis_similarity"] = thesis_hits[0]["score"]

        own_hits = await store.search(
            kind=KIND_POSTS,
            query_text=thesis,
            limit=3,
            score_threshold=THESIS_SIMILARITY_THRESHOLD,
            filter_payload={"user_id": str(user_id)},
        )
        if own_hits:
            warnings.append("thesis_similar_to_own_posts")
            metadata["own_thesis_similarity"] = own_hits[0]["score"]

        hook_hits = await store.search(
            kind=KIND_INSPIRATION,
            query_text=hook,
            limit=3,
            score_threshold=HOOK_SIMILARITY_THRESHOLD,
            filter_payload={"domain": domain},
        )
        if hook_hits:
            warnings.append("hook_similar_to_inspiration")
            metadata["hook_similarity"] = hook_hits[0]["score"]
    except Exception as exc:
        logger.debug("novelty_vector_check_failed", error=str(exc))

    from services.ai.claude_client import generate_json

    try:
        assessment = await generate_json(
            task="novelty_assessment",
            system="Return only valid JSON.",
            user=NOVELTY_ASSESSMENT_PROMPT.format(thesis=thesis, hook=hook),
            max_tokens=512,
        )
        metadata["novelty_score"] = assessment.get("novelty_score", 10)
        metadata["value_additions"] = assessment.get("value_additions", [])
        metadata["suggested_angle"] = assessment.get("suggested_angle", "")
        if metadata["novelty_score"] < NOVELTY_REGEN_THRESHOLD:
            warnings.append("low_novelty_score")
    except Exception as exc:
        logger.warning("novelty_assessment_failed", error=str(exc))
        metadata["novelty_score"] = None

    if warnings:
        logger.warning("novelty_gate_warnings", warnings=warnings, user_id=str(user_id))

    return {
        "warnings": warnings,
        "metadata": metadata,
        "should_regenerate": metadata.get("novelty_score", 10) < NOVELTY_REGEN_THRESHOLD
        and bool(metadata.get("suggested_angle")),
        "suggested_angle": metadata.get("suggested_angle", ""),
    }
