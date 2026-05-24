"""Substack article generation via Claude. Per-user voice anchoring."""
import json
from typing import Any
from uuid import UUID

import structlog

from services.ai.claude_client import generate_json
from services.ai.vector_store import KIND_ARTICLES, get_vector_store
from services.content.prompts import (
    BANNED_PHRASES,
    SUBSTACK_ARTICLE_SYSTEM_PROMPT,
    SUBSTACK_ARTICLE_USER_PROMPT,
    _BANNED_PHRASE_LIST,
)

logger = structlog.get_logger(__name__)


def _validate_article(body: str) -> list[str]:
    issues = []
    words = len(body.split())
    if words < 1000:
        issues.append(f"Too short: ~{words} words (min ~1500)")
    if words > 3500:
        issues.append(f"Too long: ~{words} words (max ~3000)")
    for phrase in BANNED_PHRASES:
        if phrase.lower() in body.lower():
            issues.append(f"Banned phrase: '{phrase}'")
    if "```" not in body and "    " not in body:
        issues.append("No code block found — consider adding a concrete example")
    return issues


async def _retrieve_voice_examples(
    user_id: UUID, title: str, domain: str, limit: int = 2
) -> str:
    try:
        store = get_vector_store()
        hits = await store.search(
            kind=KIND_ARTICLES,
            query_text=title,
            limit=limit,
            score_threshold=0.5,
            filter_payload={"user_id": str(user_id), "domain": domain},
        )
    except Exception as exc:
        logger.debug("voice_examples_unavailable", error=str(exc))
        return ""

    if not hits:
        return ""

    examples = "\n\n=====\n\n".join(
        h["payload"].get("text", "")[:3000] for h in hits if h["payload"].get("text")
    )
    return (
        "Below are openings and structures from prior articles you wrote on related topics. "
        "Use them only to anchor voice — do not repeat phrasing, examples, or arguments:\n\n"
        + examples
    )


async def generate_article(
    user_id: UUID,
    title: str,
    domain: str,
    voice_style: str,
    summary: str,
    key_facts: list[str],
    why_it_matters: str,
    trade_offs: str,
    is_paired: bool = False,
) -> dict[str, Any]:
    """Generate a Substack article. Returns {title, subtitle, body_markdown, violations}."""
    system = SUBSTACK_ARTICLE_SYSTEM_PROMPT.format(banned_phrases=_BANNED_PHRASE_LIST)

    voice_examples = await _retrieve_voice_examples(user_id, title, domain)
    user = SUBSTACK_ARTICLE_USER_PROMPT.format(
        title=title,
        domain=domain,
        voice_style=voice_style,
        summary=summary,
        key_facts=json.dumps(key_facts),
        why_it_matters=why_it_matters,
        trade_offs=trade_offs or "None",
        is_paired="Yes — assume reader saw the LinkedIn teaser" if is_paired else "No — self-contained",
    )
    if voice_examples:
        user = voice_examples + "\n\n---\n\n" + user

    data = await generate_json(
        task="substack_article",
        system=system,
        user=user,
        max_tokens=4096,
        temperature=0.7,
    )

    body = data.get("body", "")
    violations = _validate_article(body)
    if violations:
        logger.warning("article_quality_violations", violations=violations, title=title)

    return {
        "title": data.get("title", title),
        "subtitle": data.get("subtitle", ""),
        "body_markdown": body,
        "violations": violations,
    }
