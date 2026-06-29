"""LinkedIn post generation via Claude. Per-user voice anchoring + Research Brain."""
import json
from typing import Any
from uuid import UUID

import structlog

from services.ai.claude_client import generate
from services.ai.vector_store import KIND_POSTS, get_vector_store
from services.content.prompts import (
    BANNED_PHRASES,
    LINKEDIN_POST_SYSTEM_PROMPT,
    LINKEDIN_POST_USER_PROMPT,
    STYLE_BRIEF_FOR_DRAFT,
    STANCE_LINKEDIN_DRAFT_USER_PROMPT,
    _BANNED_PHRASE_LIST,
)
from services.content.tone import load_tone_preferences, tone_system_constraints, validate_hashtags

logger = structlog.get_logger(__name__)


def _validate_post(content: str, tone: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    if len(content) < 1200:
        issues.append(f"Too short: {len(content)} chars (min 1200)")
    if len(content) > 1800:
        issues.append(f"Too long: {len(content)} chars (max 1800)")
    for phrase in BANNED_PHRASES:
        if phrase.lower() in content.lower():
            issues.append(f"Banned phrase found: '{phrase}'")
    issues.extend(validate_hashtags(content, tone))
    return issues


def _build_system_prompt(tone: dict[str, Any], personality_overlay: str) -> str:
    base = LINKEDIN_POST_SYSTEM_PROMPT.format(banned_phrases=_BANNED_PHRASE_LIST)
    constraints = tone_system_constraints(tone)
    base = base.replace(
        "- 0-2 emojis maximum. If you use one, it must add meaning, not decoration.\n"
        "- 3-5 hashtags at the end, on their own line, researched and relevant (not generic like #tech)",
        constraints,
    )
    if personality_overlay:
        base = base + "\n\n" + personality_overlay
    return base


async def _retrieve_voice_examples(
    user_id: UUID, title: str, domain: str, limit: int = 5
) -> str:
    try:
        store = get_vector_store()
        hits = await store.search(
            kind=KIND_POSTS,
            query_text=title,
            limit=limit,
            score_threshold=0.4,
            filter_payload={"user_id": str(user_id), "domain": domain},
        )
    except Exception as exc:
        logger.debug("voice_examples_unavailable", error=str(exc))
        return ""

    if not hits:
        return ""

    def perf_score(h: dict[str, Any]) -> float:
        meta = h["payload"].get("engagement_total", 0) or 0
        return float(meta) * 0.001 + h["score"]

    hits.sort(key=perf_score, reverse=True)
    top = hits[:3]

    examples = "\n\n---\n\n".join(
        h["payload"].get("text", "")[:1500] for h in top if h["payload"].get("text")
    )
    return (
        "Below are prior posts you wrote on similar topics. Match the voice — not the wording. "
        "Do not repeat phrases or examples from these. They exist only to anchor tone:\n\n"
        + examples
    )


async def _build_draft_context(
    user_id: UUID,
    query_text: str,
    domain: str,
    focus_area: str,
) -> tuple[str, str]:
    personality = ""
    try:
        from services.brain.personality import get_personality_overlay

        personality = await get_personality_overlay(user_id)
    except Exception as exc:
        logger.debug("personality_overlay_unavailable", error=str(exc))

    style_block = ""
    try:
        from services.brain.style_brief import get_style_brief

        brief = await get_style_brief(focus_area, domain)
        if brief:
            style_block = STYLE_BRIEF_FOR_DRAFT.format(style_brief=brief)
    except Exception as exc:
        logger.debug("style_brief_unavailable", error=str(exc))

    voice_examples = await _retrieve_voice_examples(user_id, query_text, domain)
    parts = [p for p in [voice_examples, style_block] if p]
    prefix = "\n\n---\n\n".join(parts) if parts else ""
    return personality, prefix


async def generate_post(
    user_id: UUID,
    title: str,
    domain: str,
    voice_style: str,
    key_facts: list[str],
    why_it_matters: str,
    trade_offs: str,
) -> dict[str, Any]:
    tone = await load_tone_preferences(user_id)
    personality, prefix = await _build_draft_context(user_id, title, domain, title)
    system = _build_system_prompt(tone, personality)

    user = LINKEDIN_POST_USER_PROMPT.format(
        title=title,
        domain=domain,
        voice_style=voice_style,
        key_facts=json.dumps(key_facts),
        why_it_matters=why_it_matters,
        trade_offs=trade_offs or "None",
    )
    if prefix:
        user = prefix + "\n\n---\n\n" + user

    content = (await generate(
        task="linkedin_post",
        system=system,
        user=user,
        max_tokens=800,
        temperature=0.7,
    )).strip()

    lines = content.split("\n")
    hashtag_line = next((l for l in reversed(lines) if l.strip().startswith("#")), "")
    hashtags = [tag.strip() for tag in hashtag_line.split() if tag.startswith("#")]
    violations = _validate_post(content, tone)

    novelty: dict[str, Any] = {}
    try:
        from services.brain.novelty_gate import check_novelty

        novelty = await check_novelty(user_id, title, content, domain)
        if novelty.get("should_regenerate") and novelty.get("suggested_angle"):
            user_retry = user + f"\n\nSharpen the angle: {novelty['suggested_angle']}"
            content = (await generate(
                task="linkedin_post",
                system=system,
                user=user_retry,
                max_tokens=800,
                temperature=0.7,
            )).strip()
            violations = _validate_post(content, tone)
    except Exception as exc:
        logger.debug("novelty_gate_skipped", error=str(exc))

    if violations:
        logger.warning("post_quality_violations", violations=violations, title=title)

    return {
        "content": content,
        "hashtags": hashtags,
        "violations": violations,
        "novelty": novelty,
    }


async def generate_post_from_stance(
    user_id: UUID,
    stance: dict[str, Any],
) -> dict[str, Any]:
    tone = await load_tone_preferences(user_id)
    focus_area = stance.get("focus_area") or stance.get("topic") or "engineering"
    domain = focus_area_to_domain_label(focus_area)
    thesis = stance.get("thesis", "")
    attribution = stance.get("attribution", "")
    attribution_line = (
        f"- Practitioner voice to attribute/paraphrase: {attribution}"
        if attribution
        else "- No named attribution — argue as your own informed view."
    )

    personality, prefix = await _build_draft_context(user_id, thesis, domain, focus_area)
    system = _build_system_prompt(tone, personality)

    user = STANCE_LINKEDIN_DRAFT_USER_PROMPT.format(
        thesis=thesis,
        anti_position=stance.get("anti_position", ""),
        evidence=stance.get("evidence", ""),
        focus_area=focus_area,
        source_url=stance.get("source_url", ""),
        attribution_line=attribution_line,
    )
    if prefix:
        user = prefix + "\n\n---\n\n" + user

    content = (await generate(
        task="linkedin_post",
        system=system,
        user=user,
        max_tokens=800,
        temperature=0.7,
    )).strip()

    lines = content.split("\n")
    hashtag_line = next((l for l in reversed(lines) if l.strip().startswith("#")), "")
    hashtags = [tag.strip() for tag in hashtag_line.split() if tag.startswith("#")]
    violations = _validate_post(content, tone)

    novelty: dict[str, Any] = {}
    try:
        from services.brain.novelty_gate import check_novelty

        novelty = await check_novelty(user_id, thesis, content, domain)
        if novelty.get("should_regenerate") and novelty.get("suggested_angle"):
            user_retry = user + f"\n\nSharpen the angle: {novelty['suggested_angle']}"
            content = (await generate(
                task="linkedin_post",
                system=system,
                user=user_retry,
                max_tokens=800,
                temperature=0.7,
            )).strip()
            violations = _validate_post(content, tone)
    except Exception as exc:
        logger.debug("novelty_gate_skipped", error=str(exc))

    if violations:
        logger.warning("post_quality_violations", violations=violations, thesis=thesis[:80])

    return {
        "content": content,
        "hashtags": hashtags,
        "violations": violations,
        "novelty": novelty,
    }


def focus_area_to_domain_label(focus_area: str) -> str:
    from services.research.queries import focus_area_to_domain

    return focus_area_to_domain(focus_area)
