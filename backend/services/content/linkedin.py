"""LinkedIn post generation via Claude. Per-user voice anchoring."""
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
    _BANNED_PHRASE_LIST,
)

logger = structlog.get_logger(__name__)


def _validate_post(content: str) -> list[str]:
    issues = []
    if len(content) < 1200:
        issues.append(f"Too short: {len(content)} chars (min 1200)")
    if len(content) > 1800:
        issues.append(f"Too long: {len(content)} chars (max 1800)")
    for phrase in BANNED_PHRASES:
        if phrase.lower() in content.lower():
            issues.append(f"Banned phrase found: '{phrase}'")
    hashtag_count = content.count("#")
    if hashtag_count < 3:
        issues.append(f"Too few hashtags: {hashtag_count} (min 3)")
    if hashtag_count > 5:
        issues.append(f"Too many hashtags: {hashtag_count} (max 5)")
    return issues


async def _retrieve_voice_examples(
    user_id: UUID, title: str, domain: str, limit: int = 3
) -> str:
    """Pull prior posts from *this user's* corpus on similar topics. Scoped by
    user_id payload — never leaks one user's voice into another's prompt."""
    try:
        store = get_vector_store()
        hits = await store.search(
            kind=KIND_POSTS,
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

    examples = "\n\n---\n\n".join(
        h["payload"].get("text", "")[:1500] for h in hits if h["payload"].get("text")
    )
    return (
        "Below are prior posts you wrote on similar topics. Match the voice — not the wording. "
        "Do not repeat phrases or examples from these. They exist only to anchor tone:\n\n"
        + examples
    )


async def generate_post(
    user_id: UUID,
    title: str,
    domain: str,
    voice_style: str,
    key_facts: list[str],
    why_it_matters: str,
    trade_offs: str,
) -> dict[str, Any]:
    """Generate a LinkedIn post. Returns {content, hashtags, violations}."""
    system = LINKEDIN_POST_SYSTEM_PROMPT.format(banned_phrases=_BANNED_PHRASE_LIST)

    voice_examples = await _retrieve_voice_examples(user_id, title, domain)
    user = LINKEDIN_POST_USER_PROMPT.format(
        title=title,
        domain=domain,
        voice_style=voice_style,
        key_facts=json.dumps(key_facts),
        why_it_matters=why_it_matters,
        trade_offs=trade_offs or "None",
    )
    if voice_examples:
        user = voice_examples + "\n\n---\n\n" + user

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

    violations = _validate_post(content)
    if violations:
        logger.warning("post_quality_violations", violations=violations, title=title)

    return {"content": content, "hashtags": hashtags, "violations": violations}
