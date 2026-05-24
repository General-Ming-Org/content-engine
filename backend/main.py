import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
import redis.asyncio as aioredis
import structlog
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import check_db_connection
from log_config import configure_logging
from services.auth.deps import require_verified_user

settings = get_settings()
configure_logging(level=settings.log_level, is_production=settings.is_production)

logger = structlog.get_logger(__name__)

_redis_client: aioredis.Redis | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _redis_client
    from services.ai.api_keys import sync_provider_env_keys

    sync_provider_env_keys()
    logger.info("Starting content-engine API", env=settings.app_env)
    _redis_client = aioredis.from_url(settings.redis_url, decode_responses=True)
    yield
    if _redis_client:
        await _redis_client.aclose()
    logger.info("Content-engine API shut down")


app = FastAPI(
    title="Content Engine API",
    version="0.1.0",
    description="Autonomous technical content creation, publishing, and analytics system",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    logger.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=round(duration_ms, 2),
    )
    return response


@app.get("/api/health", tags=["System"])
async def health_check() -> dict:
    """Reports live status of all critical dependencies and the configured AI providers.

    Each service entry follows {"status": "ok|degraded|not_configured|...", ...} so the
    UI and operators can spot a missing/misconfigured dependency without guessing.
    Never raises — even when a provider is unset, this endpoint returns 200 with detail.
    """
    settings = get_settings()  # re-resolve in case env changed since module load
    status: dict[str, dict[str, str]] = {}
    overall = "ok"

    def degrade() -> None:
        nonlocal overall
        if overall == "ok":
            overall = "degraded"

    # PostgreSQL
    db_ok = await check_db_connection()
    status["postgres"] = {"status": "ok"} if db_ok else {"status": "error"}
    if not db_ok:
        degrade()

    # Redis
    try:
        if _redis_client:
            await _redis_client.ping()
            status["redis"] = {"status": "ok"}
        else:
            status["redis"] = {"status": "not_initialized"}
            degrade()
    except Exception as exc:
        status["redis"] = {"status": "error", "detail": str(exc)}
        degrade()

    # LinkedIn Developer App — per-user in DB; env is optional legacy fallback.
    status["linkedin_app"] = {
        "status": "env_fallback"
        if settings.linkedin_client_id and settings.linkedin_client_secret
        else "per_user_settings"
    }

    # SMTP outbound (operator-level)
    status["smtp"] = {
        "status": "configured"
        if (settings.smtp_host and settings.smtp_username and settings.smtp_password)
        else "not_configured"
    }

    # Tavily API (lightweight ping)
    if settings.tavily_api_key:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                resp = await client.get(
                    "https://api.tavily.com/",
                    headers={"Authorization": f"Bearer {settings.tavily_api_key}"},
                )
            if resp.status_code < 500:
                status["tavily"] = {"status": "ok"}
            else:
                status["tavily"] = {"status": "error", "detail": f"HTTP {resp.status_code}"}
                degrade()
        except Exception as exc:
            status["tavily"] = {"status": "unreachable", "detail": type(exc).__name__}
            degrade()
    else:
        status["tavily"] = {"status": "not_configured"}

    # LLM provider — report on whichever provider/model is configured, not hardcoded.
    status["llm"] = _llm_health(settings)
    if status["llm"]["status"] != "ok":
        degrade()

    # Embedding provider — same shape; uses services.ai.embeddings for the canonical check.
    from services.ai.embeddings import embedding_health

    status["embeddings"] = embedding_health()
    if status["embeddings"]["status"] != "ok":
        degrade()

    return {
        "status": overall,
        "services": status,
        "version": "0.1.0",
    }


def _llm_health(settings) -> dict[str, str]:
    """Report whether the configured LLM provider/model has its key set."""
    from services.ai.api_keys import _PROVIDER_ENV

    provider = (settings.llm_provider or "").strip().lower()
    model = (settings.llm_model or "").strip()

    if not provider or not model:
        return {
            "status": "not_configured",
            "detail": "LLM_PROVIDER and LLM_MODEL must be set in .env",
        }
    if provider not in _PROVIDER_ENV:
        return {
            "status": "invalid_provider",
            "provider": provider,
            "detail": f"Valid options: {sorted(_PROVIDER_ENV)}",
        }
    env_name, attr = _PROVIDER_ENV[provider]
    if not (getattr(settings, attr, "") or ""):
        return {"status": "missing_key", "provider": provider, "model": model, "detail": f"{env_name} not set"}
    return {"status": "ok", "provider": provider, "model": model}


# Public brand assets (email logos, Gravatar/BIMI icon) — no auth required
_brand_dir = Path(__file__).resolve().parent / "static" / "email"
if _brand_dir.is_dir():
    from fastapi.staticfiles import StaticFiles

    app.mount("/api/brand", StaticFiles(directory=_brand_dir), name="brand")

# Register service routers
from services.ai.router import router as ai_router
from services.analytics.router import router as analytics_router
from services.auth.router import router as auth_router
from services.content.router import router as content_router
from services.credentials.router import router as credentials_router
from services.engagement.router import router as engagement_router
from services.notifications.router import router as notifications_router
from services.publishing.router import oauth_router as linkedin_oauth_router
from services.publishing.router import router as publishing_router
from services.research.router import router as research_router
from services.scheduler.router import router as scheduler_router
from services.settings_router import router as settings_router
from services.users.router import router as users_router

# Public endpoints — no auth required
app.include_router(auth_router, prefix="/api/auth", tags=["Auth"])

# Authenticated app endpoints — every route below requires a verified email.
verified_required = [Depends(require_verified_user)]
app.include_router(users_router, prefix="/api/users", tags=["Users"], dependencies=verified_required)
app.include_router(credentials_router, prefix="/api/credentials", tags=["Credentials"], dependencies=verified_required)
app.include_router(research_router, prefix="/api/research", tags=["Research"], dependencies=verified_required)
app.include_router(content_router, prefix="/api/content", tags=["Content"], dependencies=verified_required)
# LinkedIn OAuth callback — public (browser redirect, no JWT); must match API_PUBLIC_URL.
app.include_router(linkedin_oauth_router, prefix="/api/publish", tags=["Publishing"])
app.include_router(publishing_router, prefix="/api/publish", tags=["Publishing"], dependencies=verified_required)
app.include_router(engagement_router, prefix="/api/engagement", tags=["Engagement"], dependencies=verified_required)
app.include_router(analytics_router, prefix="/api/analytics", tags=["Analytics"], dependencies=verified_required)
app.include_router(notifications_router, prefix="/api/notifications", tags=["Notifications"], dependencies=verified_required)
app.include_router(scheduler_router, prefix="/api/scheduler", tags=["Scheduler"], dependencies=verified_required)
app.include_router(settings_router, prefix="/api/settings", tags=["Settings"], dependencies=verified_required)
app.include_router(ai_router, prefix="/api/ai/models", tags=["AI"], dependencies=verified_required)
