"""Substack publishing via Playwright browser automation.

FRAGILITY NOTE: This implementation depends on Substack's DOM structure.
Selectors may break when Substack updates their editor. See SETUP.md for
how to diagnose and update selectors.

Known brittle points:
- Login form selectors (class names can change with Substack deploys)
- Editor contenteditable area selector
- Publish button location and text
- 2FA: if enabled, the automation will time out at the 2FA step. See SETUP.md.
"""
import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from playwright.async_api import Browser, Page, async_playwright
from sqlalchemy import select, update

from database import AsyncSessionLocal
from models.content import Article
from services.credentials.store import get_substack_credential

logger = structlog.get_logger(__name__)

_browser: Browser | None = None


async def _get_browser() -> Browser:
    global _browser
    if _browser is None or not _browser.is_connected():
        playwright = await async_playwright().start()
        _browser = await playwright.chromium.launch(headless=True)
    return _browser


async def _login(page: Page, email: str, password: str) -> None:
    """Log in to Substack with email/password."""
    await page.goto("https://substack.com/sign-in", wait_until="networkidle")
    await page.fill('input[type="email"]', email)
    await page.click('button[type="submit"]')
    await page.wait_for_timeout(1000)
    try:
        await page.fill('input[type="password"]', password)
        await page.click('button[type="submit"]')
        await page.wait_for_load_state("networkidle", timeout=15000)
    except Exception as exc:
        logger.warning("substack_login_step_failed", error=str(exc))
        raise RuntimeError(
            "Substack login failed. If 2FA is enabled, disable it or complete it manually. "
            "See SETUP.md for instructions."
        ) from exc


async def publish_article(article_id: str) -> dict[str, Any]:
    """Publish a Substack article. Idempotent."""
    try:
        return await _publish_article_impl(article_id)
    except Exception as exc:
        from services.publishing.failures import mark_article_failed

        await mark_article_failed(article_id, str(exc))
        raise


async def _publish_article_impl(article_id: str) -> dict[str, Any]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Article).where(Article.id == uuid.UUID(article_id)))
        article = result.scalar_one_or_none()
        if not article:
            return {"error": f"Article {article_id} not found"}

        # Idempotency check
        if article.substack_url:
            logger.info("substack_article_already_published", article_id=article_id)
            return {"status": "already_published", "substack_url": article.substack_url}

        cred = await get_substack_credential(article.user_id)
        if not cred or not cred.get("email") or not cred.get("password"):
            raise RuntimeError(f"Substack credentials not configured for user {article.user_id}")

        pub_url = (cred.get("publication_url") or "").rstrip("/")
        if not pub_url:
            raise RuntimeError(f"Substack publication_url missing for user {article.user_id}")

        try:
            browser = await _get_browser()
            context = await browser.new_context()
            page = await context.new_page()

            await _login(page, cred["email"], cred["password"])

            # Navigate to new post editor
            await page.goto(f"{pub_url}/publish/new-post", wait_until="networkidle")
            await page.wait_for_timeout(2000)

            # Fill in title
            title_sel = 'div[data-testid="post-title"], div.post-title, h1[contenteditable]'
            await page.click(title_sel)
            await page.fill(title_sel, article.title)

            # Subtitle (optional — skip if field not found)
            try:
                sub_sel = 'div[data-testid="post-subtitle"], div.post-subtitle'
                if article.subtitle:
                    await page.fill(sub_sel, article.subtitle)
            except Exception:
                pass

            # Body — paste markdown. Substack accepts plain text; formatting is approximate.
            body_sel = 'div[contenteditable="true"].ProseMirror, div[contenteditable="true"]'
            await page.click(body_sel)
            # Use clipboard paste for reliable content insertion
            await page.evaluate(
                f"navigator.clipboard.writeText({repr(article.body_markdown)})"
            )
            await page.keyboard.press("Control+a")
            await page.keyboard.press("Control+v")
            await page.wait_for_timeout(1000)

            # Publish
            publish_btn_sel = 'button:has-text("Publish"), button:has-text("Continue")'
            await page.click(publish_btn_sel)
            await page.wait_for_timeout(1500)

            # Confirm publish in dialog if it appears
            try:
                confirm_sel = 'button:has-text("Publish now"), button:has-text("Publish post")'
                await page.click(confirm_sel, timeout=5000)
                await page.wait_for_load_state("networkidle", timeout=15000)
            except Exception:
                pass

            # Grab published URL
            substack_url = page.url
            if "publish" in substack_url or "new-post" in substack_url:
                # URL didn't change to a post URL — check for any redirect
                await page.wait_for_timeout(3000)
                substack_url = page.url

            await context.close()

        except Exception as exc:
            logger.error("substack_publish_failed", article_id=article_id, error=str(exc))
            raise

        await db.execute(
            update(Article)
            .where(Article.id == article.id)
            .values(
                status="published",
                published_at=datetime.now(timezone.utc),
                substack_url=substack_url,
            )
        )
        await db.commit()
        logger.info("substack_article_published", article_id=article_id, url=substack_url)

        from services.ai.ingestion import index_published_article

        await index_published_article(
            user_id=article.user_id,
            article_id=article.id,
            title=article.title,
            subtitle=article.subtitle or "",
            body_markdown=article.body_markdown,
            domain="software_eng",
            voice_style=article.voice_style,
            metadata={"substack_url": substack_url},
        )
        return {"status": "published", "substack_url": substack_url}
