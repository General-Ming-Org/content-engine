# Content Engine — CLAUDE.md

## Project Overview
Autonomous technical content creation, publishing, and analytics system. Multiple users sign up, each connects their own LinkedIn / Substack accounts, and the engine generates and publishes on their behalf. Research is a shared cross-user pool; published content (and the embeddings derived from it) is per-user.

**Multi-user, single deployment.** Operator runs one instance, pays for shared AI / search / embedding API calls. Each user owns their own posting accounts, recipient email address, and any per-user configuration.

---

## Tech Stack Reference

| Layer | Technology |
|---|---|
| Backend | Python 3.12+ / FastAPI (async throughout) |
| Frontend | React 18 + Vite + Tailwind CSS (dark mode) |
| Database | PostgreSQL 16 via SQLAlchemy 2.0 (async) + Alembic |
| Vector DB | Qdrant (separate container) — per-(kind, embedding-model) collections; per-user via payload |
| Task Queue | Celery 5 + Redis 7 + RedBeat scheduler |
| Auth | Email/password + bcrypt + JWT (HS256, 24h TTL, signed with APP_SECRET_KEY) |
| Cred encryption | Fernet, key derived from APP_SECRET_KEY — protects user-stored LinkedIn / Substack tokens |
| LLMs | Any provider via LiteLLM — Anthropic, OpenAI, Google Gemini, Mistral, Groq, DeepSeek, xAI, OpenRouter; tier router in `services/ai/`; operator-paid |
| Embeddings | Voyage / OpenAI / Cohere via swappable provider abstraction; operator-paid |
| MCP | Tavily MCP (internal) + custom Knowledge MCP (internal + external, per-user bearer tokens) |
| Search | Tavily (primary), Serper (fallback) — operator-paid |
| LinkedIn | Official UGC API; per-user Developer App + OAuth tokens in DB |
| Substack | Playwright browser automation; per-user creds in DB (encrypted) |
| Email | aiosmtplib SMTP; operator-paid outbound, per-user recipient address |
| Containers | Docker + Docker Compose |
| Deploy | Terraform → single GCP Compute Engine VM, GitHub Actions CI/CD |

---

## Directory Structure Rules

```
backend/
  models/         — SQLAlchemy ORM models only. No business logic.
  services/       — One directory per service domain.
    ai/           — Model router, Claude client, embedding providers, vector store.
                    All Claude calls go through services.ai.claude_client.generate().
                    All embedding calls go through services.ai.embeddings.get_active_embedder().
    <domain>/
      router.py   — FastAPI APIRouter only. Thin — delegates to service modules.
      *.py        — Service logic.
  services/content/prompts.py  — SINGLE source of truth for ALL Claude prompts.
  mcp_servers/    — Custom MCP servers (knowledge MCP). Run as separate containers.
  migrations/     — Alembic only. Never hand-edit generated migrations.
  tests/          — pytest tests. One file per service domain.

frontend/src/
  pages/          — One file per route. Page components only.
  components/     — Shared UI components.
  lib/api.ts      — ALL API calls go through here. No fetch() calls in pages.

infra/terraform/  — GCP infrastructure: VM, Artifact Registry, Secret Manager, WIF.
.github/workflows/— CI (tests + tf validate) and Deploy (build → push → SSH up).
```

**Never** import between service directories directly (e.g., `from services.analytics import ...` in `services.content`). All cross-service communication goes through: the database, Celery tasks, or HTTP.

---

## Python Coding Standards

### Type hints
- All function signatures must have complete type hints.
- Use `X | None` syntax (Python 3.10+), not `Optional[X]`.
- Return types required on all public functions.

### Async
- All I/O is async. Never use blocking calls (`requests`, `time.sleep`, synchronous DB queries) in async functions.
- Use `asyncio.gather()` for concurrent I/O.
- Celery tasks are sync wrappers: they call `asyncio.get_event_loop().run_until_complete(coro)`.

### Pydantic / Schemas
- All API request/response bodies use Pydantic models or typed dicts.
- Validate at system boundaries (user input, external API responses). Trust internal DB data.

### Error handling
- External API calls: `try/except` with structlog logging. Never swallow exceptions silently.
- Celery tasks: `max_retries=3`, exponential backoff (60s, 120s, 240s).
- After all retries exhausted: write to `notifications` table + send SMTP alert.

### Import order
1. stdlib
2. third-party
3. local (`from config import ...`, `from models import ...`, `from services import ...`)

### Logging
- Use `structlog` everywhere. Pass structured key-value pairs, never f-string messages.
- `logger.info("event_name", key=value, ...)` — event name in snake_case.

### Comments
- Default: none. Add a comment only when the WHY is non-obvious (hidden constraint, workaround, invariant).
- Never document WHAT the code does — names do that.

---

## TypeScript / React Coding Standards

### Components
- Functional components only. No class components.
- Props typed inline or with interface — no implicit `any`.
- TypeScript strict mode is on. Fix errors, don't cast with `as`.

### Styling
- Tailwind only. No inline styles. No CSS modules. No styled-components.
- Dark mode via `dark:` prefix. Default is dark (set on `<html>` element).
- Design language: Linear/Vercel aesthetic — minimal, dense, no gratuitous spacing.

### API calls
- **All** fetch calls go through `src/lib/api.ts`. Never call `fetch()` directly in a component.
- Use `@tanstack/react-query` for all server state: `useQuery` for reads, `useMutation` for writes.

### State
- Server state: react-query. Local UI state: `useState`. No Redux, no Zustand.

---

## Key Architecture Decisions

### Why multi-user with operator-paid keys
Each user signs up and connects their own LinkedIn / Substack accounts; the engine generates and posts on their behalf. AI / search / embedding API calls are operator-paid (shared env keys) — users don't bring their own keys. This makes signup zero-friction and lets the operator absorb the (small) shared cost. Research is a shared cross-user pool (one Tavily sweep serves everyone, filtered per-user by domain prefs); published content is per-user (filtered by `user_id` payload in Qdrant).

### Why every API route depends on `get_current_user`
Single exception: `/api/auth/*` (signup/login). Every other route resolves the caller's user from the JWT and scopes queries by `Model.user_id == user.id`. The LinkedIn OAuth callback is also auth-less because it's hit by the LinkedIn redirect — it uses a signed `state` parameter to recover which user just authed.

### Why per-user credentials are encrypted at rest
LinkedIn refresh tokens and Substack passwords sit in `user_credentials.secret_payload` as Fernet ciphertext. The key derives from `APP_SECRET_KEY` via SHA-256 → urlsafe base64. Rotating `APP_SECRET_KEY` invalidates all stored creds AND all active JWTs simultaneously — that's intentional. There's no separate KMS for a single-deployment system.

### Why the first signup becomes admin
Pragma. Someone has to be admin to manage users. Open signup is the lowest-friction model for a small shared deployment; gating it behind invite codes adds bootstrap complexity we don't need. If you outgrow this, switch the signup endpoint to admin-only and have admins create accounts.

### Why every LLM call goes through `services.ai.llm_client`
Never instantiate `AsyncAnthropic` / `openai.AsyncOpenAI` / `google.genai` clients directly. The wrapped client:
1. Resolves the task to a provider-qualified model ID via `model_router.pick_model(task)` (e.g., `"anthropic/claude-sonnet-4-6"`, `"openai/gpt-5-mini"`, `"gemini/gemini-2.5-flash"`).
2. Routes the call through LiteLLM so the same code path works for any supported provider.
3. Conditionally applies provider-specific features — `cache_control` on Anthropic for prompt caching, `mcp_servers` on Anthropic for MCP tool use. Other providers ignore these gracefully.
4. Logs structured token usage per task for cost attribution.

Direct SDK use bypasses all four. When adding a new AI-powered task, call `generate()` / `generate_json()` with a descriptive task name for logging — never branch on provider at the call site.

(`services.ai.claude_client` is a deprecated shim that re-exports from `llm_client`. Don't introduce new imports from it.)

### Why embeddings go through `services.ai.embeddings.get_active_embedder()`
Provider abstraction lets you swap Voyage / OpenAI / Cohere without touching call sites. Each provider declares its `model_id` and `dimensions`, which the vector store uses to scope Qdrant collections. Changing the active model auto-enqueues `reembed_corpus` so the new collection gets populated without losing the old one mid-flight.

### Why Qdrant collections are scoped per (kind, embedding_model_id)
A vector DB silently breaks if you change the embedding model — old vectors are in a different space than new queries. Scoping by model means switching providers creates a new collection alongside the old one. The re-embed task migrates everything over; until then queries against the new collection just return empty (a self-evident signal something is mid-migration).

### Why prompts are centralized in `prompts.py`
All Claude system prompts live in `backend/services/content/prompts.py`. This is non-negotiable. Scattered inline prompts are impossible to maintain, audit for banned phrases, or compare across versions. Any AI-powered feature adds its prompt there.

### Why two MCP servers
**Tavily MCP** (internal): containerized so Claude can call live web search as a tool during generation. The backend's deterministic research pipeline still calls Tavily directly — MCP is for ad-hoc context Claude decides it needs.

**Knowledge MCP** (internal + external): exposes the engine's accumulated corpus (research, posts, articles) via Qdrant. Internally, generation calls pass it via `mcp_servers=[...]` so Claude can pull voice-consistency examples on demand. Externally, the user points Claude Code / Desktop at the public URL with a bearer token to query their own corpus interactively.

### Why publishing is idempotent
Before any publish call, we check if `linkedin_post_id` (posts) or `substack_url` (articles) is already set. If it is, we return early. This prevents double-posting from retries. Never remove this check.

### Why engagement is reactive-only
The system only replies to comments on its own published posts. No proactive commenting on others' content. This is a hard scope boundary, not a preference.

### Why the 1-hour queue exists
Content is generated autonomously but not published instantly. The 1-hour window gives the user a chance to review, edit, or cancel before it goes live. Items in `queued` status with `queued_at + 1hr <= now()` get auto-published by the queue checker task. Items the user manually approves via the dashboard skip the remaining wait.

### Why DB-mediated cross-service communication
Services don't import from each other. They share state through the database and communicate via Celery tasks. This keeps service boundaries clean and makes it possible to run services independently.

### Why circuit breaker on LinkedIn
LinkedIn will rate-limit aggressively. If we hit a 429, we open a circuit breaker in `user_settings` that pauses all LinkedIn API calls for 1 hour. This prevents cascading failures and avoids account bans.

### Why Playwright for Substack
Substack has no official API. Playwright automation is fragile but necessary. All brittle selectors are documented in `substack_auto.py` and `SETUP.md`. When Substack updates their UI, update selectors there.

---

## Commands

### Local development (Docker)
```bash
# Start everything
docker compose up -d

# View logs
docker compose logs -f backend
docker compose logs -f worker

# Run migrations
docker compose exec backend alembic -c migrations/alembic.ini upgrade head

# Seed sample data
docker compose exec backend python ../scripts/seed_db.py

# Run tests
docker compose exec backend pytest tests/ -v

# Access API docs
open http://localhost:8000/api/docs
```

### Without Docker (dev)
```bash
# Backend
cd backend
pip install -r requirements.txt
alembic -c migrations/alembic.ini upgrade head
uvicorn main:app --reload

# Worker
celery -A services.scheduler.tasks worker --loglevel=info

# Beat scheduler
celery -A services.scheduler.tasks beat --loglevel=info --scheduler redbeat.RedBeatScheduler

# Frontend
cd frontend
npm install
npm run dev
```

### Manual task triggers
```bash
# From project root
python scripts/manual_trigger.py research
python scripts/manual_trigger.py generate
python scripts/manual_trigger.py queue
python scripts/manual_trigger.py metrics
python scripts/manual_trigger.py weekly-report
```

---

## Common Pitfalls

1. **Circular import via models**: `models/content.py` has a circular FK between `Post` and `Article`. The FK from `articles.linked_post_id → posts.id` is added in the migration _after_ both tables are created. The ORM handles this via `relationship()` with explicit `foreign_keys=`. Don't try to add this FK in the model `__init__` order.

2. **Celery task imports**: Celery tasks import service modules at call time (inside the function body), not at module load time. This prevents circular imports and allows the worker to start cleanly before services are fully initialized.

3. **Async in Celery**: Celery tasks are synchronous. Wrap async calls with `asyncio.get_event_loop().run_until_complete()` via the `_run()` helper in `tasks.py`. Never use `asyncio.run()` in a Celery task — it creates a new event loop and breaks on some platforms.

4. **Playwright in Docker**: The worker container installs Playwright browsers. First startup is slow (~2 min). If Substack automation fails, check that `SUBSTACK_EMAIL` and `SUBSTACK_PASSWORD` are set, and that the account doesn't use Google/Apple SSO (must have a direct password).

5. **LinkedIn token expiry**: Access tokens expire in 60 days. The refresh flow is in `linkedin_api.py`. When a publish fails with 401, the token needs refreshing. See SETUP.md for the OAuth re-auth procedure.

6. **SQLite in tests**: Tests use SQLite (in-memory) via aiosqlite. Some PostgreSQL-specific features (JSONB, ARRAY, UUID) may behave differently. Don't add tests that rely on PostgreSQL-specific operators.

7. **Don't instantiate provider SDKs directly**: Every LLM call goes through `services.ai.generate()` / `generate_json()` (or `services.ai.llm_client.*`). Direct use of `AsyncAnthropic`, `openai.AsyncOpenAI`, `google.genai`, etc. bypasses the model router, prompt caching, MCP gating, and token logging. The catalogue in `services/ai/providers.py` is the canonical list of supported models; off-catalogue strings are allowed for advanced users but log a warning at override time.

8. **Don't write inline embedding calls**: Same pattern — go through `services.ai.embeddings.get_active_embedder()`. Direct HTTP calls to Voyage/OpenAI/Cohere bypass the provider abstraction and break the re-embed flow when the active model changes.

9. **Vector store kinds are an enum, not strings**: Use the constants `KIND_RESEARCH`, `KIND_POSTS`, `KIND_ARTICLES`, `KIND_SOURCES` from `services.ai.vector_store`. String literals at call sites get out of sync with the validation set inside the module.

10. **Embedding model change triggers re-embed**: When `user_settings.embedding_active` changes, the settings router enqueues `reembed_corpus` automatically. Don't manually call re-embed unless you've cleared a collection or are recovering from a partial migration — `reembed_corpus` is idempotent but pulls the whole corpus each invocation.

11. **Terraform state in GCS**: After first apply, switch to the GCS backend (`backend "gcs" {...}` in `main.tf`) so state isn't local-only. Local state will silently desync if more than one person runs `terraform apply`.

12. **Don't query models without `user_id` scoping**: Every route that touches `posts`, `articles`, `engagement_actions`, `metric_snapshots`, `strategy_reports`, `goals`, `notifications`, or `user_settings` MUST filter by `user_id == current_user.id`. Forgetting this is a cross-tenant data leak. ResearchTopic is the only model with no user scoping — it's a shared pool.

13. **LinkedIn OAuth state is signed**: When generating the OAuth URL, encode the calling user's UUID into `state` via `itsdangerous.URLSafeSerializer` (salt `"linkedin-oauth"`). The callback decodes and validates this — don't accept unsigned states.

14. **Per-user circuit breakers**: LinkedIn rate limits are tracked per user (`user_settings(user_id, key='circuit_breaker')`). Don't share the breaker across users — one user hitting 429 shouldn't pause everyone.

15. **Knowledge MCP requires per-user bearer token**: External Claude clients (Claude Code / Desktop) authenticate with a personal token issued via `POST /api/credentials/mcp-token`. The MCP middleware hashes (SHA-256) the incoming token, looks up the owning user, and scopes all `search_posts` / `search_articles` queries to that user via Qdrant payload filter. `search_research` and `list_recent_topics` query the shared pool — still authenticated, but not user-scoped.

---

## Definition of Done

A task is complete when:
- [ ] Code has type hints on all public functions
- [ ] No `any` in TypeScript without a comment explaining why
- [ ] External API calls have try/except with structlog logging
- [ ] New Celery tasks have `max_retries=3` and exponential backoff
- [ ] New Claude prompts are added to `prompts.py`, not inline
- [ ] Tests cover the happy path and at least one failure mode
- [ ] No banned phrases from `BANNED_PHRASES` list appear in prompt templates
- [ ] Published routes are added to `main.py` router registration
- [ ] Health check in `GET /api/health` covers any new dependency
