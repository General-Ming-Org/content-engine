"""Content calendar — generation orchestrated per user.

The research topic pool is shared, but content generation is per-user:
- Each user's domain preferences select different topics from the same pool.
- A topic can be picked by multiple users; we use the same topic but mark
  `posts.research_id` / `articles.research_id` independently per user.
- `ResearchTopic.status` stays a coarse pool-level signal — flipped to "used"
  the first time any user consumes it.

Per-user posting schedule, voice prefs, and domain weights all live in
`user_settings` rows scoped to that user.
"""
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from database import AsyncSessionLocal
from models.content import Article, Post
from models.research import ResearchTopic
from models.settings import UserSetting
from models.user import User
from services.ai.claude_client import generate as claude_generate
from services.content.linkedin import generate_post, generate_post_from_stance
from services.content.prompts import PAIRING_DECISION_PROMPT
from services.content.substack import generate_article

logger = structlog.get_logger(__name__)

DEFAULT_DOMAINS = ["ai_ml", "software_eng", "sre_infra", "data_eng"]
DEFAULT_SCHEDULE = {
    "linkedin": {"days": ["tuesday", "wednesday", "thursday"], "time": "14:00"},
    "substack": {"day": "saturday", "time": "14:00"},
}
DEFAULT_MAX_POSTS_PER_USER_PER_RUN = 3


def _stance_from_topic(topic: ResearchTopic) -> dict[str, Any] | None:
    """Read extracted stance from topic sources. None → legacy synthesis path."""
    if not topic.sources or not isinstance(topic.sources, list):
        return None
    first = topic.sources[0] if isinstance(topic.sources[0], dict) else {}
    stance = first.get("stance")
    return stance if isinstance(stance, dict) and stance.get("thesis") else None


async def _decide_pairing(topic: ResearchTopic, synthesis: dict[str, Any]) -> str:
    prompt = PAIRING_DECISION_PROMPT.format(
        title=topic.title,
        domain=topic.domain,
        summary=topic.summary or "",
        key_facts_count=len(synthesis.get("key_facts", [])),
        suggested_voice=synthesis.get("suggested_voice", "analytical"),
    )
    decision = (await claude_generate(
        task="content_pairing_decision",
        system="Answer with exactly one of: paired, linkedin_only, substack_only. No other text.",
        user=prompt,
        max_tokens=16,
        temperature=0.0,
    )).strip().lower()
    if decision not in ("paired", "linkedin_only", "substack_only"):
        decision = "linkedin_only"
    return decision


async def _load_user_pref(user_id: UUID, key: str, default: Any) -> Any:
    async with AsyncSessionLocal() as db:
        row = (
            await db.execute(
                select(UserSetting).where(
                    UserSetting.user_id == user_id,
                    UserSetting.key == key,
                )
            )
        ).scalar_one_or_none()
        return row.value if row else default


async def generate_for_topic(
    research_topic_id: str,
    user_id: UUID,
    task_id: str | None = None,
) -> dict[str, Any]:
    """Generate content for a single research topic, attributed to a specific user."""
    from services.content import progress as gen_progress

    async with AsyncSessionLocal() as db:
        topic = (
            await db.execute(select(ResearchTopic).where(ResearchTopic.id == uuid.UUID(research_topic_id)))
        ).scalar_one_or_none()
        if not topic:
            err = f"Topic {research_topic_id} not found"
            if task_id:
                gen_progress.progress_fail(task_id, err)
            return {"error": err}

        if task_id:
            gen_progress.progress_start(task_id, topic_id=research_topic_id, topic_title=topic.title)

        stance = _stance_from_topic(topic)

        # LEGACY_SUBSTANCE_PATH: synthesis/key_facts branch below — see LEGACY_SUBSTANCE_PATHS.md
        synthesis = {}
        if not stance and topic.sources:
            first_source = topic.sources[0] if isinstance(topic.sources, list) else {}
            synthesis = first_source.get("synthesis", {})

        voice_style = synthesis.get("suggested_voice", "opinionated" if stance else "analytical")
        key_facts = synthesis.get("key_facts", [topic.summary or ""])
        why_it_matters = synthesis.get("why_it_matters", "")
        trade_offs = synthesis.get("trade_offs", "")

        if task_id:
            gen_progress.progress_update(
                task_id,
                phase="pairing",
                percent=15,
                message="Choosing LinkedIn, Substack, or both…",
            )
        # Stance topics are LinkedIn-first — arguing a take, not teaching a tutorial.
        decision = "linkedin_only" if stance else await _decide_pairing(topic, synthesis)
        created: dict[str, Any] = {
            "decision": decision,
            "topic_id": research_topic_id,
            "user_id": str(user_id),
        }
        now = datetime.now(timezone.utc)

        post = None
        if decision in ("paired", "linkedin_only"):
            if task_id:
                gen_progress.progress_update(
                    task_id,
                    phase="linkedin",
                    percent=40,
                    message="Writing LinkedIn post…",
                )
            post_data = (
                await generate_post_from_stance(user_id=user_id, stance=stance)
                if stance
                else await generate_post(
                    user_id=user_id,
                    title=topic.title,
                    domain=topic.domain,
                    voice_style=voice_style,
                    key_facts=key_facts,
                    why_it_matters=why_it_matters,
                    trade_offs=trade_offs,
                )
            )
            post = Post(
                id=uuid.uuid4(),
                user_id=user_id,
                research_id=topic.id,
                content=post_data["content"],
                hashtags=post_data["hashtags"],
                voice_style=voice_style,
                status="queued",
                queued_at=now,
                is_manual=False,
            )
            db.add(post)
            await db.flush()
            created["post_id"] = str(post.id)

        article = None
        if decision in ("paired", "substack_only"):
            if task_id:
                gen_progress.progress_update(
                    task_id,
                    phase="article",
                    percent=70,
                    message="Writing Substack article…",
                )
            article_data = await generate_article(
                user_id=user_id,
                title=topic.title,
                domain=topic.domain,
                voice_style=voice_style,
                summary=topic.summary or "",
                key_facts=key_facts,
                why_it_matters=why_it_matters,
                trade_offs=trade_offs,
                is_paired=(decision == "paired"),
            )
            article = Article(
                id=uuid.uuid4(),
                user_id=user_id,
                research_id=topic.id,
                title=article_data["title"],
                subtitle=article_data.get("subtitle"),
                body_markdown=article_data["body_markdown"],
                voice_style=voice_style,
                status="queued",
                queued_at=now,
                is_manual=False,
                linked_post_id=post.id if post is not None else None,
            )
            db.add(article)
            await db.flush()
            created["article_id"] = str(article.id)

            if decision == "paired" and post is not None:
                post.linked_article_id = article.id

        # Pool-level marker. First user to consume a topic flips it; others can still
        # use it (we don't gate generation on status, only the next-batch picker).
        if topic.status == "new":
            topic.status = "used"

        if task_id:
            gen_progress.progress_update(
                task_id,
                phase="saving",
                percent=92,
                message="Saving to your queue…",
            )
        await db.commit()
        if task_id:
            if created.get("error"):
                gen_progress.progress_fail(task_id, str(created["error"]))
            else:
                gen_progress.progress_finish(task_id, created)
        logger.info("content_generated", **created)
        return created


async def _generate_for_user(user_id: UUID) -> dict[str, Any]:
    """Pick top stance topics by debatability score. Skip day if none qualify."""
    max_per_run = await _load_user_pref(user_id, "max_posts_per_run", DEFAULT_MAX_POSTS_PER_USER_PER_RUN)

    async with AsyncSessionLocal() as db:
        candidates = (
            await db.execute(
                select(ResearchTopic)
                .where(ResearchTopic.status.in_(["new", "used"]))
                .order_by(ResearchTopic.relevance_score.desc())
                .limit(max_per_run * 3)
            )
        ).scalars().all()

    topics = [t for t in candidates if _stance_from_topic(t)][:max_per_run]

    if not topics:
        logger.info(
            "content_generation_skipped",
            user_id=str(user_id),
            reason="no_debatable_stances",
        )
        return {
            "user_id": str(user_id),
            "generated": [],
            "count": 0,
            "skipped": True,
            "reason": "no_debatable_stances",
        }

    generated = []
    for topic in topics:
        result = await generate_for_topic(str(topic.id), user_id)
        generated.append(result)
    return {"user_id": str(user_id), "generated": generated, "count": len(generated)}


async def generate_scheduled_content() -> dict[str, Any]:
    """Iterate over all active users and generate content for each."""
    async with AsyncSessionLocal() as db:
        users = (
            await db.execute(select(User).where(User.is_active.is_(True)))
        ).scalars().all()

    results = []
    for user in users:
        try:
            results.append(await _generate_for_user(user.id))
        except Exception as exc:
            logger.error("generate_for_user_failed", user_id=str(user.id), error=str(exc))
            results.append({"user_id": str(user.id), "error": str(exc)})
    return {"users": results, "count": len(results)}
