"""Two-axis gates applied after stance extraction, before persistence or drafting.

RELEVANCE  — is this in my lane?  (MY_FOCUS_AREAS; hard filter)
DEBATABILITY — is this worth arguing?  (score threshold; skip day if none pass)
"""
from typing import Any

import structlog

from services.research.queries import DEBATABILITY_MIN_SCORE, MY_FOCUS_AREAS

logger = structlog.get_logger(__name__)


def _normalize(text: str) -> str:
    return " ".join(text.lower().split())


def passes_relevance_gate(stance: dict[str, Any]) -> bool:
    """Hard filter: stance must be credibly in the author's lane."""
    focus_area = stance.get("focus_area") or stance.get("topic") or ""
    if not focus_area:
        logger.info("stance_relevance_rejected", reason="missing_focus_area", thesis=stance.get("thesis", "")[:80])
        return False

    normalized = _normalize(focus_area)
    for area in MY_FOCUS_AREAS:
        area_norm = _normalize(area)
        if normalized == area_norm:
            return True
        if area_norm in normalized or normalized in area_norm:
            return True
        area_tokens = set(area_norm.split())
        focus_tokens = set(normalized.split())
        if len(area_tokens & focus_tokens) >= 2:
            return True

    logger.info(
        "stance_relevance_rejected",
        reason="outside_lane",
        focus_area=focus_area,
        thesis=stance.get("thesis", "")[:80],
    )
    return False


def passes_debatability_gate(stance: dict[str, Any]) -> bool:
    score = float(stance.get("debatability_score") or 0)
    if score < DEBATABILITY_MIN_SCORE:
        logger.info(
            "stance_debatability_rejected",
            score=score,
            threshold=DEBATABILITY_MIN_SCORE,
            thesis=stance.get("thesis", "")[:80],
        )
        return False
    return True


def apply_stance_gates(stances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply relevance (hard) then debatability (threshold). No score blending."""
    after_relevance = [s for s in stances if passes_relevance_gate(s)]
    surviving = [s for s in after_relevance if passes_debatability_gate(s)]
    logger.info(
        "stance_gates_applied",
        input_count=len(stances),
        after_relevance=len(after_relevance),
        surviving=len(surviving),
        debatability_threshold=DEBATABILITY_MIN_SCORE,
    )
    return surviving
