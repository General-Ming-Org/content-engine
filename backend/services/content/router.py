"""Content routes — all per-user scoped."""
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from database import get_db
from models.content import Article, Post
from models.research import ResearchTopic
from models.user import User
from services.auth.deps import get_current_user

router = APIRouter()


# ── Calendar ──────────────────────────────────────────────────────────────────

@router.get("/calendar")
async def get_calendar(
    view: str = Query("week", pattern="^(week|month)$"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    posts = (await db.execute(
        select(Post).where(
            Post.user_id == user.id,
            Post.status.in_(["queued", "scheduled", "published", "failed"]),
        )
    )).scalars().all()
    articles = (await db.execute(
        select(Article).where(
            Article.user_id == user.id,
            Article.status.in_(["queued", "scheduled", "published", "failed"]),
        )
    )).scalars().all()
    return {
        "posts": [_post_to_dict(p) for p in posts],
        "articles": [_article_to_dict(a) for a in articles],
    }


# ── Posts ─────────────────────────────────────────────────────────────────────

@router.get("/posts")
async def list_posts(
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = select(Post).where(Post.user_id == user.id).order_by(Post.created_at.desc())
    if status:
        q = q.where(Post.status == status)
    q = q.offset(offset).limit(limit)
    posts = (await db.execute(q)).scalars().all()
    return {"posts": [_post_to_dict(p) for p in posts]}


@router.get("/posts/{post_id}")
async def get_post(
    post_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return _post_to_dict(await _get_or_404(db, Post, post_id, user.id))


@router.post("/posts")
async def create_post(
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    post = Post(
        user_id=user.id,
        content=payload["content"],
        hashtags=payload.get("hashtags", []),
        voice_style=payload.get("voice_style", "analytical"),
        status="draft",
        is_manual=True,
        scheduled_at=payload.get("scheduled_at"),
    )
    db.add(post)
    await db.flush()
    return _post_to_dict(post)


@router.put("/posts/{post_id}")
async def update_post(
    post_id: uuid.UUID,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_or_404(db, Post, post_id, user.id)  # ownership check
    allowed = {"content", "hashtags", "voice_style", "scheduled_at"}
    data = {k: v for k, v in payload.items() if k in allowed}
    await db.execute(update(Post).where(Post.id == post_id).values(**data))
    return _post_to_dict(await _get_or_404(db, Post, post_id, user.id))


@router.patch("/posts/{post_id}/cancel")
async def cancel_post(
    post_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_or_404(db, Post, post_id, user.id)
    await db.execute(update(Post).where(Post.id == post_id).values(status="cancelled"))
    return _post_to_dict(await _get_or_404(db, Post, post_id, user.id))


@router.patch("/posts/{post_id}/approve")
async def approve_post(
    post_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    from services.scheduler.tasks import publish_linkedin_post
    post = await _get_or_404(db, Post, post_id, user.id)
    task = publish_linkedin_post.delay(str(post.id))
    return {"status": "publishing", "task_id": task.id}


@router.patch("/posts/{post_id}/reschedule")
async def reschedule_post(
    post_id: uuid.UUID,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_or_404(db, Post, post_id, user.id)
    await db.execute(
        update(Post)
        .where(Post.id == post_id)
        .values(scheduled_at=payload["scheduled_at"], queued_at=None, status="scheduled")
    )
    return _post_to_dict(await _get_or_404(db, Post, post_id, user.id))


# ── Articles ──────────────────────────────────────────────────────────────────

@router.get("/articles")
async def list_articles(
    status: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    q = select(Article).where(Article.user_id == user.id).order_by(Article.created_at.desc())
    if status:
        q = q.where(Article.status == status)
    q = q.offset(offset).limit(limit)
    articles = (await db.execute(q)).scalars().all()
    return {"articles": [_article_to_dict(a) for a in articles]}


@router.get("/articles/{article_id}")
async def get_article(
    article_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return _article_to_dict(await _get_or_404(db, Article, article_id, user.id))


@router.post("/articles")
async def create_article(
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    article = Article(
        user_id=user.id,
        title=payload["title"],
        subtitle=payload.get("subtitle"),
        body_markdown=payload["body_markdown"],
        voice_style=payload.get("voice_style", "analytical"),
        status="draft",
        is_manual=True,
        scheduled_at=payload.get("scheduled_at"),
    )
    db.add(article)
    await db.flush()
    return _article_to_dict(article)


@router.put("/articles/{article_id}")
async def update_article(
    article_id: uuid.UUID,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_or_404(db, Article, article_id, user.id)
    allowed = {"title", "subtitle", "body_markdown", "voice_style", "scheduled_at"}
    data = {k: v for k, v in payload.items() if k in allowed}
    await db.execute(update(Article).where(Article.id == article_id).values(**data))
    return _article_to_dict(await _get_or_404(db, Article, article_id, user.id))


@router.patch("/articles/{article_id}/cancel")
async def cancel_article(
    article_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_or_404(db, Article, article_id, user.id)
    await db.execute(update(Article).where(Article.id == article_id).values(status="cancelled"))
    return _article_to_dict(await _get_or_404(db, Article, article_id, user.id))


@router.patch("/articles/{article_id}/approve")
async def approve_article(
    article_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    from services.scheduler.tasks import publish_substack_article
    article = await _get_or_404(db, Article, article_id, user.id)
    task = publish_substack_article.delay(str(article.id))
    return {"status": "publishing", "task_id": task.id}


@router.patch("/articles/{article_id}/reschedule")
async def reschedule_article(
    article_id: uuid.UUID,
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    await _get_or_404(db, Article, article_id, user.id)
    await db.execute(
        update(Article)
        .where(Article.id == article_id)
        .values(scheduled_at=payload["scheduled_at"], queued_at=None, status="scheduled")
    )
    return _article_to_dict(await _get_or_404(db, Article, article_id, user.id))


@router.get("/generate/status")
async def content_generation_status(
    task_id: str | None = Query(None),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Poll progress for an in-flight or recent content generation task."""
    from services.content.progress import get_progress

    progress = await get_progress(task_id)
    return {"active": progress is not None and progress.get("status") == "running", "progress": progress}


@router.post("/generate")
async def generate_content(
    payload: dict[str, Any],
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    """Generate content for a research topic, attributed to the calling user."""
    from services.content.progress import progress_start
    from services.scheduler.tasks import generate_content_for_topic

    topic_id = payload["research_topic_id"]
    topic = (
        await db.execute(
            select(ResearchTopic).where(
                ResearchTopic.id == uuid.UUID(topic_id),
                ResearchTopic.user_id == user.id,
            )
        )
    ).scalar_one_or_none()
    if not topic:
        raise HTTPException(404, "Research topic not found")

    task = generate_content_for_topic.delay(topic_id, str(user.id))
    if task.id:
        progress_start(task.id, topic_id=topic_id, topic_title=topic.title)
    return {"status": "triggered", "task_id": task.id}


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _get_or_404(db: AsyncSession, model: type, id: uuid.UUID, user_id: uuid.UUID):
    result = await db.execute(
        select(model).where(model.id == id, model.user_id == user_id)
    )
    obj = result.scalar_one_or_none()
    if not obj:
        raise HTTPException(404, f"{model.__name__} not found")
    return obj


def _post_to_dict(p: Post) -> dict[str, Any]:
    return {
        "id": str(p.id),
        "research_id": str(p.research_id) if p.research_id else None,
        "linked_article_id": str(p.linked_article_id) if p.linked_article_id else None,
        "content": p.content,
        "hashtags": p.hashtags,
        "voice_style": p.voice_style,
        "status": p.status,
        "queued_at": p.queued_at.isoformat() if p.queued_at else None,
        "scheduled_at": p.scheduled_at.isoformat() if p.scheduled_at else None,
        "published_at": p.published_at.isoformat() if p.published_at else None,
        "linkedin_post_id": p.linkedin_post_id,
        "metrics": p.metrics,
        "is_manual": p.is_manual,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _article_to_dict(a: Article) -> dict[str, Any]:
    return {
        "id": str(a.id),
        "research_id": str(a.research_id) if a.research_id else None,
        "linked_post_id": str(a.linked_post_id) if a.linked_post_id else None,
        "title": a.title,
        "subtitle": a.subtitle,
        "body_markdown": a.body_markdown,
        "voice_style": a.voice_style,
        "status": a.status,
        "queued_at": a.queued_at.isoformat() if a.queued_at else None,
        "scheduled_at": a.scheduled_at.isoformat() if a.scheduled_at else None,
        "published_at": a.published_at.isoformat() if a.published_at else None,
        "substack_url": a.substack_url,
        "metrics": a.metrics,
        "is_manual": a.is_manual,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
