"""Per-user daily summary and weekly deep-dive reports.

Each user gets their own report row in strategy_reports. The top-level
generate_daily() / generate_weekly() iterate active users and produce one
report per user, attributed by user_id.
"""
import json
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

import structlog
from sqlalchemy import select

from database import AsyncSessionLocal
from models.analytics import Goal, MetricSnapshot, StrategyReport
from models.content import Article, Post
from models.engagement import EngagementAction
from models.user import User
from services.ai.claude_client import generate_json
from services.analytics.benchmarks import compare_to_benchmark
from services.content.prompts import DAILY_SUMMARY_PROMPT, WEEKLY_DEEP_DIVE_PROMPT

logger = structlog.get_logger(__name__)


def _day_start(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)


async def _gather_daily_for(user_id: UUID, today: date) -> dict[str, Any]:
    start = _day_start(today)
    end = _day_start(today + timedelta(days=1))

    async with AsyncSessionLocal() as db:
        posts = (await db.execute(
            select(Post).where(
                Post.user_id == user_id,
                Post.published_at >= start,
                Post.published_at < end,
            )
        )).scalars().all()
        articles = (await db.execute(
            select(Article).where(
                Article.user_id == user_id,
                Article.published_at >= start,
            )
        )).scalars().all()
        engagements = (await db.execute(
            select(EngagementAction).where(
                EngagementAction.user_id == user_id,
                EngagementAction.created_at >= start,
            )
        )).scalars().all()
        li_snap = (await db.execute(
            select(MetricSnapshot).where(
                MetricSnapshot.user_id == user_id,
                MetricSnapshot.platform == "linkedin",
            ).order_by(MetricSnapshot.snapshot_date.desc()).limit(1)
        )).scalar_one_or_none()

    return {
        "posts_published": [
            {"title": p.content[:80], "platform": "linkedin", "metrics": p.metrics or {}}
            for p in posts
        ],
        "articles_published": [
            {"title": a.title, "platform": "substack", "metrics": a.metrics or {}}
            for a in articles
        ],
        "comments_received": len(engagements),
        "replies_sent": sum(1 for e in engagements if e.status == "posted"),
        "linkedin_metrics": li_snap.data if li_snap else {},
    }


async def _generate_daily_for(user_id: UUID) -> dict[str, Any]:
    today = date.today()
    data = await _gather_daily_for(user_id, today)
    report_json = await generate_json(
        task="daily_summary",
        system="You are a content analytics assistant. Respond with JSON only.",
        user=DAILY_SUMMARY_PROMPT.format(data=json.dumps(data, indent=2)),
        max_tokens=1024,
    )

    async with AsyncSessionLocal() as db:
        report = StrategyReport(
            id=uuid.uuid4(),
            user_id=user_id,
            report_type="daily_summary",
            period_start=today,
            period_end=today,
            report_json=report_json,
            created_at=datetime.now(timezone.utc),
        )
        db.add(report)
        await db.commit()

    from services.notifications.notifier import create_user_system
    await create_user_system(
        user_id,
        title=f"Daily Summary — {today.strftime('%b %d')}",
        message=report_json.get("headline", "Daily summary ready"),
    )
    return {"report_id": str(report.id)}


async def _generate_weekly_for(user_id: UUID) -> dict[str, Any]:
    today = date.today()
    week_start = today - timedelta(days=7)

    async with AsyncSessionLocal() as db:
        posts = (await db.execute(
            select(Post).where(
                Post.user_id == user_id,
                Post.published_at >= _day_start(week_start),
                Post.status == "published",
            )
        )).scalars().all()
        snapshots = (await db.execute(
            select(MetricSnapshot).where(
                MetricSnapshot.user_id == user_id,
                MetricSnapshot.snapshot_date >= week_start,
                MetricSnapshot.platform == "linkedin",
            ).order_by(MetricSnapshot.snapshot_date.asc())
        )).scalars().all()
        goals = (await db.execute(
            select(Goal).where(Goal.user_id == user_id, Goal.status == "active")
        )).scalars().all()

    impressions = [p.metrics.get("impressions", 0) for p in posts if p.metrics]
    avg_impressions = sum(impressions) / len(impressions) if impressions else 0
    benchmark = compare_to_benchmark({"engagement_rate_pct": 0, "impressions": avg_impressions})

    data = {
        "posts": [
            {
                "title": p.content[:80],
                "platform": "linkedin",
                "published_at": p.published_at.isoformat() if p.published_at else None,
                "metrics": p.metrics or {},
                "voice_style": p.voice_style,
            }
            for p in posts
        ],
        "metric_trend": [{"date": s.snapshot_date.isoformat(), **s.data} for s in snapshots],
        "benchmark_comparison": benchmark,
        "goals": [
            {
                "metric_name": g.metric_name,
                "current": g.current_value,
                "target": g.target_value,
                "target_date": g.target_date.isoformat(),
                "pct_complete": round(g.current_value / g.target_value * 100, 1) if g.target_value else 0,
            }
            for g in goals
        ],
    }

    report_json = await generate_json(
        task="weekly_deep_dive",
        system="You are a content strategy analyst. Respond with JSON only.",
        user=WEEKLY_DEEP_DIVE_PROMPT.format(
            data=json.dumps(data, indent=2),
            start_date=str(week_start),
            end_date=str(today),
        ),
        max_tokens=2048,
    )

    async with AsyncSessionLocal() as db:
        report = StrategyReport(
            id=uuid.uuid4(),
            user_id=user_id,
            report_type="weekly_deep_dive",
            period_start=week_start,
            period_end=today,
            report_json=report_json,
            top_posts={"posts": report_json.get("top_posts", [])},
            benchmark_comparison=benchmark,
            goal_progress={"goals": report_json.get("goal_progress", [])},
            created_at=datetime.now(timezone.utc),
        )
        db.add(report)
        await db.commit()
    return {"report_id": str(report.id)}


async def _iter_active_users() -> list[User]:
    async with AsyncSessionLocal() as db:
        return (await db.execute(select(User).where(User.is_active.is_(True)))).scalars().all()


async def generate_daily() -> dict[str, Any]:
    per_user = {}
    for u in await _iter_active_users():
        try:
            per_user[str(u.id)] = await _generate_daily_for(u.id)
        except Exception as exc:
            logger.error("daily_report_user_failed", user_id=str(u.id), error=str(exc))
            per_user[str(u.id)] = {"error": str(exc)}
    return {"users": per_user}


async def generate_weekly() -> dict[str, Any]:
    per_user = {}
    for u in await _iter_active_users():
        try:
            per_user[str(u.id)] = await _generate_weekly_for(u.id)
        except Exception as exc:
            logger.error("weekly_report_user_failed", user_id=str(u.id), error=str(exc))
            per_user[str(u.id)] = {"error": str(exc)}
    return {"users": per_user}
