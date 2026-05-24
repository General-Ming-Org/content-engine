"""1-hour auto-publish queue processor.

Items leave the queue when:
  - Published successfully
  - Marked ``failed`` (no automatic retries)
  - Cancelled by the user

Failed items are NOT retried every 5 minutes — that caused email/notification spam
on restart when LinkedIn/Substack credentials were missing.
"""
from datetime import datetime, timedelta, timezone
from typing import Any

import structlog
from sqlalchemy import select

from database import AsyncSessionLocal
from models.content import Article, Post
from services.publishing.failures import handle_publish_exception
from services.publishing.linkedin_api import publish_post
from services.publishing.substack_auto import publish_article

logger = structlog.get_logger(__name__)

QUEUE_DELAY_MINUTES = 60


async def process_queue() -> dict[str, Any]:
    """Publish content where queued_at + 1 hour has elapsed and status is still ``queued``."""
    cutoff = datetime.now(timezone.utc) - timedelta(minutes=QUEUE_DELAY_MINUTES)
    published = {"posts": 0, "articles": 0, "errors": []}

    async with AsyncSessionLocal() as db:
        posts_result = await db.execute(
            select(Post).where(Post.status == "queued", Post.queued_at <= cutoff)
        )
        posts = posts_result.scalars().all()

        articles_result = await db.execute(
            select(Article).where(Article.status == "queued", Article.queued_at <= cutoff)
        )
        articles = articles_result.scalars().all()

    for post in posts:
        try:
            result = await publish_post(str(post.id))
            if result.get("status") in ("published", "already_published"):
                published["posts"] += 1
                logger.info("queue_post_published", post_id=str(post.id))
        except Exception as exc:
            err = str(exc)
            logger.error("queue_post_failed", post_id=str(post.id), error=err)
            published["errors"].append({"type": "post", "id": str(post.id), "error": err})
            await handle_publish_exception(
                platform="linkedin",
                item_id=post.id,
                error=exc,
                notify=True,
            )

    for article in articles:
        try:
            result = await publish_article(str(article.id))
            if result.get("status") in ("published", "already_published"):
                published["articles"] += 1
                logger.info("queue_article_published", article_id=str(article.id))
        except Exception as exc:
            err = str(exc)
            logger.error("queue_article_failed", article_id=str(article.id), error=err)
            published["errors"].append({"type": "article", "id": str(article.id), "error": err})
            await handle_publish_exception(
                platform="substack",
                item_id=article.id,
                error=exc,
                notify=True,
            )

    return published
