"""Per-user metric collection from LinkedIn API + Substack."""
import uuid
from datetime import date, datetime, timezone
from typing import Any
from uuid import UUID

import httpx
import structlog
from sqlalchemy import select

from database import AsyncSessionLocal
from models.analytics import Goal, MetricSnapshot
from models.content import Post
from models.user import User
from services.credentials.store import get_linkedin_credential, get_substack_credential

logger = structlog.get_logger(__name__)


async def _collect_linkedin_for(user_id: UUID) -> dict[str, Any]:
    cred = await get_linkedin_credential(user_id)
    if not cred or not cred.get("access_token"):
        return {}

    metrics: dict[str, Any] = {}
    headers = {
        "Authorization": f"Bearer {cred['access_token']}",
        "X-Restli-Protocol-Version": "2.0.0",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(
                "https://api.linkedin.com/v2/networkSizes/~?edgeType=CompanyFollowedByMember",
                headers=headers,
            )
            if resp.status_code == 200:
                metrics["followers"] = resp.json().get("firstDegreeSize", 0)
        except Exception as exc:
            logger.warning("linkedin_follower_count_failed", user_id=str(user_id), error=str(exc))

        try:
            resp = await client.get(
                "https://api.linkedin.com/v2/analyticsQuery?type=PROFILE_VIEWS",
                headers=headers,
            )
            if resp.status_code == 200:
                metrics["profile_views"] = resp.json().get("total", 0)
        except Exception as exc:
            logger.warning("linkedin_profile_views_failed", user_id=str(user_id), error=str(exc))

    async with AsyncSessionLocal() as db:
        from models.research import ResearchTopic
        from services.publishing.linkedin_api import get_post_metrics
        from services.ai.ingestion import index_published_post

        posts = (await db.execute(
            select(Post).where(
                Post.user_id == user_id,
                Post.status == "published",
                Post.linkedin_post_id.isnot(None),
            )
        )).scalars().all()

        total_imp = total_eng = 0
        for post in posts:
            pm = await get_post_metrics(user_id, post.linkedin_post_id)
            likes = pm.get("likes", 0)
            comments = pm.get("comments", 0)
            shares = pm.get("shares", 0)
            engagement_total = likes + comments + shares
            impressions = pm.get("impressions", 0)
            engagement_rate = (
                round(engagement_total / impressions * 100, 2) if impressions else 0.0
            )
            post.metrics = {
                "likes": likes,
                "comments": comments,
                "shares": shares,
                "engagement_total": engagement_total,
                "impressions": impressions,
                "engagement_rate": engagement_rate,
                "collected_at": datetime.now(timezone.utc).isoformat(),
            }
            total_imp += impressions
            total_eng += engagement_total

            domain = "software_eng"
            if post.research_id:
                topic = (
                    await db.execute(
                        select(ResearchTopic).where(ResearchTopic.id == post.research_id)
                    )
                ).scalar_one_or_none()
                if topic:
                    domain = topic.domain
            try:
                await index_published_post(
                    user_id=post.user_id,
                    post_id=post.id,
                    content=post.content,
                    domain=domain,
                    voice_style=post.voice_style,
                    metadata={
                        "linkedin_post_id": post.linkedin_post_id,
                        "engagement_total": engagement_total,
                    },
                )
            except Exception as exc:
                logger.debug("post_reindex_skipped", post_id=str(post.id), error=str(exc))

        await db.commit()

        metrics["impressions_total"] = total_imp
        metrics["avg_engagement_rate"] = (
            round(total_eng / total_imp * 100, 2)
            if total_imp
            else round(total_eng / len(posts), 2) if posts else 0.0
        )
        metrics["post_count"] = len(posts)
    return metrics


async def _collect_substack_for(user_id: UUID) -> dict[str, Any]:
    cred = await get_substack_credential(user_id)
    if not cred or not cred.get("publication_url"):
        return {}
    pub_url = cred["publication_url"].rstrip("/")
    metrics: dict[str, Any] = {}
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{pub_url}/api/v1/publication-info")
            if resp.status_code == 200:
                metrics["subscriber_count"] = resp.json().get("freeSubscriberCount", 0)
    except Exception as exc:
        logger.warning("substack_metrics_failed", user_id=str(user_id), error=str(exc))
    return metrics


async def _update_goal_progress_for(user_id: UUID, li_metrics: dict, sub_metrics: dict) -> None:
    metric_map = {
        "linkedin_followers": li_metrics.get("followers", 0),
        "substack_subscribers": sub_metrics.get("subscriber_count", 0),
        "avg_engagement_rate": li_metrics.get("avg_engagement_rate", 0),
    }
    today = date.today()
    async with AsyncSessionLocal() as db:
        goals = (await db.execute(
            select(Goal).where(Goal.user_id == user_id, Goal.status == "active")
        )).scalars().all()
        for goal in goals:
            current = metric_map.get(goal.metric_name, goal.current_value)
            goal.current_value = current
            if current >= goal.target_value:
                goal.status = "achieved"
            elif goal.target_date < today:
                goal.status = "missed"
        await db.commit()


async def _collect_for_user(user_id: UUID) -> dict[str, Any]:
    today = date.today()
    li = await _collect_linkedin_for(user_id)
    sub = await _collect_substack_for(user_id)

    async with AsyncSessionLocal() as db:
        if li:
            db.add(MetricSnapshot(
                id=uuid.uuid4(),
                user_id=user_id,
                snapshot_date=today,
                platform="linkedin",
                data=li,
                created_at=datetime.now(timezone.utc),
            ))
        if sub:
            db.add(MetricSnapshot(
                id=uuid.uuid4(),
                user_id=user_id,
                snapshot_date=today,
                platform="substack",
                data=sub,
                created_at=datetime.now(timezone.utc),
            ))
        await db.commit()

    await _update_goal_progress_for(user_id, li, sub)
    return {"linkedin": li, "substack": sub}


async def collect_all_metrics() -> dict[str, Any]:
    """Top-level metric task — iterate active users."""
    async with AsyncSessionLocal() as db:
        users = (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()

    per_user = {}
    for u in users:
        try:
            per_user[str(u.id)] = await _collect_for_user(u.id)
        except Exception as exc:
            logger.error("collect_metrics_user_failed", user_id=str(u.id), error=str(exc))
            per_user[str(u.id)] = {"error": str(exc)}
    return {"users": per_user}
