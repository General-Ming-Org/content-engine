# Content Engine

Autonomous technical content creation, publishing, and analytics. Multiple users sign up via email/password, connect their own LinkedIn / Substack accounts, and the engine generates and publishes on their behalf — all running on Celery once configured.

**Multi-user, single deployment.** The operator hosts one instance and pays for shared AI / search / embedding API calls. Each user owns their own posting accounts and recipient email address.

---

## What it does

For every active user:
- **Researches** trending content across four domains via a shared cross-user research pool (Tavily + Claude synthesis), twice daily. Each user only sees topics matching their configured domains.
- **Generates** 3 LinkedIn posts/week + 1 Substack article/week, per user. Decides per topic whether to pair them, ship LinkedIn-only, or ship Substack-only.
- **Queues for 1 hour** before auto-publishing. Each user can edit, cancel, reschedule, or approve-now their own queued items.
- **Replies** to comments on each user's own published LinkedIn posts using their personal OAuth token. Reactive only — never proactive comments.
- **Tracks metrics** in append-only daily snapshots, scoped per-user. Per-user daily summaries and weekly deep-dive reports. Compares against LinkedIn benchmarks. Tracks goal progress.
- **Alerts** via dashboard + SMTP email — only for failures (publish errors, auth expiry, API outages). Sent to each user's configured recipient address.
- **Email digests**: per-user morning preview of what's queued today, evening recap of what shipped and how it's doing.

## Account model

- **Open signup with email/password.** First account created becomes admin.
- **Admins** can promote/demote others and disable accounts via the dashboard's Users page.
- **Per-user credentials** for LinkedIn (OAuth, full per-user flow) and Substack (email/password, encrypted at rest). The operator provides one LinkedIn Developer App; each user OAuths through it from Settings.
- **Operator pays for shared infrastructure**: Anthropic, Voyage/OpenAI/Cohere, Tavily, and outbound SMTP. Users configure their own recipient address for digests.
- **Personal MCP tokens** let each user query their own corpus from Claude Code / Claude Desktop. Issue from Settings → MCP Token; one-time display.

---

## Stack

| Layer | Technology |
|---|---|
| Backend | Python 3.12+ / FastAPI (async) |
| Frontend | React 18 + Vite + Tailwind (dark mode) |
| Database | PostgreSQL 16 / SQLAlchemy 2.0 async + Alembic |
| Vector DB | Qdrant — per-(kind, embedding-model) collections, semantic dedup + voice anchoring |
| Task queue | Celery 5 + Redis 7 + RedBeat scheduler |
| LLMs | Any provider via LiteLLM — Anthropic, OpenAI, Google Gemini, Mistral, Groq, DeepSeek, xAI, OpenRouter. Configure one explicit `LLM_PROVIDER` + `LLM_MODEL` pair in `.env`. |
| Embeddings | Voyage / OpenAI / Cohere via swappable provider abstraction |
| MCP | Tavily MCP (internal tool source) + custom Knowledge MCP (internal + external) |
| Search | Tavily (primary), Serper (fallback) |
| LinkedIn | Official UGC API via OAuth2 |
| Substack | Playwright browser automation |
| Email | aiosmtplib SMTP |
| Containers | Docker Compose |
| Deploy | Terraform → single GCP Compute Engine VM; GitHub Actions CI/CD |

Full dependency list: [`backend/requirements.txt`](backend/requirements.txt).

## Token economics

The engine is built to minimize spend:
- **Tier router across providers** — High-volume / structured tasks (research synthesis, dedup, comment replies) route to the cheapest tier; content generation to standard; weekly deep-dive to premium. Each tier is independently configurable — you can keep Anthropic across the board, or mix (e.g., Groq Llama for cheap-tier speed, Gemini Pro for premium analysis, Sonnet for content). See [`backend/services/ai/model_router.py`](backend/services/ai/model_router.py) and the catalogue in [`backend/services/ai/providers.py`](backend/services/ai/providers.py).
- **Prompt caching** — On Anthropic models, every system prompt is marked with `cache_control` for a 90% discount on cached prefix tokens. Other providers either auto-cache (OpenAI) or skip the feature gracefully.
- **Per-task / per-user overrides** — Users can override which model serves a specific task via Settings → AI Models. Useful when, say, you want LinkedIn posts to come out of GPT-5 but everything else from Claude.
- **Vector cache** — Before fetching sources for a new research topic, the engine queries Qdrant. If a recent topic is >85% similar, it reuses that synthesis instead of paying for sources + a fresh LLM call.
- **Voice anchoring via retrieval** — Generation calls pull prior posts on similar topics from Qdrant as few-shot examples, so prompts stay short while the engine compounds its own voice over time.

---

## Quick start

```bash
# 1. Copy and fill in secrets
cp .env.example .env
# Edit .env — see SETUP.md for how to obtain each key

# 2. Start the stack
docker compose up -d

# 3. Run migrations
docker compose exec backend alembic -c migrations/alembic.ini upgrade head

# 4. (Optional) Seed sample data
docker compose exec backend python ../scripts/seed_db.py

# 5. Open the dashboard
open http://localhost:3000
# API docs: http://localhost:8000/api/docs
# Health:   http://localhost:8000/api/health
```

The Docker Compose stack runs eight containers: `db` (Postgres), `redis`, `qdrant` (vector DB on `:6333`), `tavily-mcp` (search tool source on `:8001`), `knowledge-mcp` (custom MCP exposing the vector DB on `:8002`), `backend` (FastAPI on `:8000`), `worker` (Celery), `beat` (RedBeat scheduler), `frontend` (Vite on `:3000`). See [`docker-compose.yml`](docker-compose.yml).

## Deploying to GCP

Production deploy is a single Compute Engine VM running the same docker-compose stack. Terraform provisions the VM, Artifact Registry, Secret Manager, and Workload Identity Federation for GitHub Actions:

```bash
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Fill in project_id, github_repo, allowed CIDRs, and generated secret values

terraform init
terraform apply
```

Cost: ~$15-20/month for `e2-small`. See [`infra/terraform/README.md`](infra/terraform/README.md) for the full walkthrough including WIF setup for GitHub Actions secrets.

CI/CD runs on every push to `main`:
- [`.github/workflows/ci.yml`](.github/workflows/ci.yml) — tests + frontend build + terraform validate
- [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) — build images → push to Artifact Registry → SSH into the VM → `docker compose pull && up -d` → migrate → smoke-test `/api/health`

---

## Manual triggers

Every scheduled task is also triggerable on demand — from the dashboard, a `POST /api/scheduler/trigger/{name}`, or the CLI:

```bash
python scripts/manual_trigger.py research
python scripts/manual_trigger.py generate
python scripts/manual_trigger.py queue
python scripts/manual_trigger.py metrics
python scripts/manual_trigger.py weekly-report
```

---

## Tests

```bash
docker compose exec backend pytest tests/ -v
```

Tests use SQLite (aiosqlite) in-memory — all external APIs (Claude, Tavily, LinkedIn, Substack, SMTP) are mocked. See [`backend/tests/`](backend/tests/).

---

## Project layout

```
content-engine/
├── backend/
│   ├── main.py                       FastAPI entry + router registration
│   ├── config.py                     pydantic-settings, env loading
│   ├── database.py                   Async engine + session
│   ├── models/                       SQLAlchemy ORM (no business logic)
│   ├── services/
│   │   ├── ai/                       ← Model router, Claude client, embeddings, vector store
│   │   │   ├── model_router.py       Task → tier (Haiku/Sonnet/Opus) mapping
│   │   │   ├── claude_client.py      Wrapped AsyncAnthropic with prompt caching
│   │   │   ├── embeddings.py         Voyage / OpenAI / Cohere provider abstraction
│   │   │   ├── vector_store.py       Qdrant wrapper, per-model collection scoping
│   │   │   ├── ingestion.py          Embed published content into the vector store
│   │   │   ├── reembed.py            Idempotent corpus re-embed on model change
│   │   │   └── mcp_servers.py        Build mcp_servers list for Claude API calls
│   │   ├── research/                 Tavily search + Claude synthesis + dedup
│   │   ├── content/                  LinkedIn + Substack generation
│   │   │   └── prompts.py            ← SINGLE source of truth for all Claude prompts
│   │   ├── publishing/               LinkedIn API + Substack Playwright + 1hr queue
│   │   ├── engagement/               Reply to comments on own posts (safety-gated)
│   │   ├── analytics/                Metric collection + benchmarks + goals + reports
│   │   ├── notifications/            Dashboard alerts + SMTP digests
│   │   └── scheduler/                Celery beat schedule + task wrappers
│   ├── mcp_servers/
│   │   └── knowledge/server.py       Custom MCP server (internal + external)
│   ├── migrations/                   Alembic
│   └── tests/                        pytest (one file per service domain)
├── frontend/
│   └── src/
│       ├── pages/                    One file per route (9 pages)
│       ├── components/
│       └── lib/api.ts                ALL fetch() calls live here
├── infra/terraform/                  GCP VM provisioning + Secret Manager + WIF
├── .github/workflows/                CI (ci.yml) + Deploy (deploy.yml)
├── scripts/                          seed_db.py, manual_trigger.py
├── docker-compose.yml                Dev stack
├── docker-compose.prod.yml           VM overrides (Artifact Registry images)
├── .env.example
├── CLAUDE.md                         Coding standards + pitfalls (for contributors)
├── ARCHITECTURE.md                   System design + data flow + invariants
├── agents.md                         Autonomous agent definitions
└── SETUP.md                          Step-by-step external integration setup
```

---

## Documentation

- **[ARCHITECTURE.md](ARCHITECTURE.md)** — system design, data flow, service boundaries, key invariants, failure modes
- **[CLAUDE.md](CLAUDE.md)** — coding standards, common pitfalls, definition of done
- **[agents.md](agents.md)** — what each autonomous agent owns, reads, writes, and how they coordinate
- **[SETUP.md](SETUP.md)** — how to obtain every secret in `.env.example` (LinkedIn OAuth, Tavily key, SMTP, Substack credentials, etc.)

---

## Hard scope boundaries

These are not preferences — they're design constraints. Don't relax them without a deliberate decision.

- **Small shared deployment, not SaaS.** Designed for a handful of users (you + friends/team), not paid customers. No billing, no quotas, no row-level pricing.
- **LinkedIn + Substack only.** No Twitter/X, Medium, dev.to, Mastodon.
- **Reactive engagement only.** The system replies to comments on each user's own posts. It never proactively comments on others' content.
- **Analytics inform, don't act.** The system reports trends and benchmark gaps. It never auto-adjusts the posting strategy. Each user reads their own weekly deep-dive and decides.
- **Idempotent publish.** Every publish call short-circuits if `linkedin_post_id` or `substack_url` is already set.
- **Centralized prompts.** Every Claude prompt lives in [`backend/services/content/prompts.py`](backend/services/content/prompts.py). No inline prompts anywhere.
- **Per-user data isolation.** Every model except `research_topics` is scoped by `user_id`. Forgetting that filter in a query is a cross-tenant data leak.
- **Operator pays for shared services.** No bring-your-own-keys. If a user wants their own Anthropic budget, that's a different deployment.
