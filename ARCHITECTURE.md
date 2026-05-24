# Architecture

This document describes how the Content Engine is wired together: the runtime topology, the data flow through one full pipeline cycle, the boundaries between services, the scheduled cadence, and the invariants that keep it safe to run autonomously.

For coding standards and conventions, see [CLAUDE.md](CLAUDE.md). For per-agent responsibilities, see [agents.md](agents.md). For external integration setup, see [SETUP.md](SETUP.md).

---

## 0. Tenancy model

Multi-user, single deployment. The operator runs one instance; users sign up with email/password and connect their own LinkedIn / Substack accounts.

| Resource | Scope | Notes |
|---|---|---|
| Anthropic / Voyage / OpenAI / Tavily API keys | Operator (env) | One key for all users |
| LinkedIn Developer App | Operator (env) | Shared OAuth client; each user OAuths through it |
| LinkedIn access / refresh tokens, person URN | Per-user (DB, encrypted) | Stored in `user_credentials.linkedin` |
| Substack email / password / publication URL | Per-user (DB, encrypted) | Stored in `user_credentials.substack` |
| SMTP outbound credentials | Operator (env) | One sender for all digest emails |
| SMTP recipient address | Per-user (DB) | Each user owns their "to" address |
| `research_topics` | **Shared** | One Tavily sweep populates the pool for everyone |
| `posts`, `articles`, `engagement_actions`, `metric_snapshots`, `strategy_reports`, `goals`, `notifications`, `user_settings` | Per-user (FK `user_id`) | Cascade-delete on user removal |
| Qdrant collections | Shared per `(kind, embedding_model_id)` | `kind=posts/articles` payloads carry `user_id` for filtering |
| Personal MCP tokens | Per-user | Issued via `/api/credentials/mcp-token`; hashed in DB |

Cost shape: each new user adds ~0 to the operator's research bill (shared pool) and ~3 LinkedIn posts + 1 Substack article worth of generation tokens per week.

---

## 1. High-level topology

```
┌─────────────────────────────────────────────────────────────────┐
│                     DASHBOARD (React + Vite)                    │
│  Dashboard · Calendar · Library · Research · Engagement         │
│  Analytics · Compose · Notifications · Settings                 │
└──────────────────────────────┬──────────────────────────────────┘
                               │  REST (src/lib/api.ts)
┌──────────────────────────────▼──────────────────────────────────┐
│                       FastAPI (backend/main.py)                  │
│   /api/research  /api/content  /api/publish  /api/engagement     │
│   /api/analytics /api/notifications  /api/scheduler  /api/settings │
└──┬──────┬──────┬──────┬──────┬──────┬──────┬──────────────────┬─┘
   ▼      ▼      ▼      ▼      ▼      ▼      ▼                  │
┌───────┐┌───────┐┌───────┐┌───────┐┌────────┐┌───────┐┌───────┐ │
│Resrch ││Contnt ││Publsh ││Engage ││Analytcs││Notif  ││Sched  │ │
└───┬───┘└───┬───┘└───┬───┘└───┬───┘└───┬────┘└───┬───┘└───┬───┘ │
    │       │       │       │       │       │       │     │
    └───────┴───────┴───┬───┴───────┴───────┴───────┘     │
                       │                                  │
                ┌──────▼──────┐         ┌─────────────────▼────┐
                │ PostgreSQL  │◄────────│ Celery Worker        │
                │ (state +    │         │ (executes service    │
                │  queue)     │         │  code via async)     │
                └─────────────┘         └──────────┬───────────┘
                       ▲                           │
                       │                ┌──────────▼───────────┐
                       └────────────────│ Celery Beat (RedBeat)│
                                        │ on Redis             │
                                        └──────────────────────┘

External: Claude API · Tavily · LinkedIn API · Substack (Playwright) · SMTP
```

Eight long-running containers (`docker-compose.yml`):

| Container | Process |
|---|---|
| `db` | Postgres 16 |
| `redis` | Redis 7 (broker + RedBeat scheduler store) |
| `qdrant` | Qdrant 1.12 vector DB (port 6333 REST, 6334 gRPC) |
| `tavily-mcp` | Tavily MCP server (port 8001) — search tool for Claude calls |
| `knowledge-mcp` | Custom MCP server (port 8002) — exposes the vector DB |
| `backend` | `uvicorn main:app` on port 8000 |
| `worker` | `celery -A services.scheduler.tasks worker --concurrency=4` |
| `beat` | `celery ... beat --scheduler redbeat.RedBeatScheduler` |
| `frontend` | Vite dev server on port 3000 |

`worker`, `beat`, and `knowledge-mcp` share the backend image — only the entrypoint command differs. Playwright browsers are persisted in `playwright_data`. Qdrant data lives in `qdrant_data` so collections survive container restarts.

---

## 2. Data flow — one full pipeline cycle

The pipeline is driven by Celery Beat. Each scheduled task is a thin Celery wrapper that invokes async service code via a `_run()` helper that calls `loop.run_until_complete()`. Services never call each other directly — they hand off through Postgres rows.

```
[Beat 8 AM/6 PM]        [Beat 9 PM]            [Beat */5 min]         [Beat */4 hr]
       │                     │                       │                       │
       ▼                     ▼                       ▼                       ▼
┌────────────┐         ┌────────────┐         ┌────────────┐         ┌────────────┐
│  RESEARCH  │ ──────► │  GENERATE  │ ──────► │   QUEUE    │ ──────► │  ENGAGE    │
│            │ topics  │            │ posts   │   CHECK    │ posts   │            │
│ Tavily +   │ rows    │ Claude +   │ +       │            │ +       │ Reply to   │
│ Claude     │         │ prompts.py │ articles│ publish if │ articles│ comments   │
│ synthesis  │         │            │ rows    │ queued_at  │         │ on own     │
│ + scoring  │         │            │ status= │ + 1hr ≤    │         │ posts only │
│ + dedup    │         │            │ "queued"│ now()      │         │            │
└────────────┘         └────────────┘         └────────────┘         └────────────┘
       │                     │                       │                       │
       └─────────────────────┴───────────┬───────────┴───────────────────────┘
                                         ▼
                              ┌──────────────────────┐
                              │  PostgreSQL          │
                              │  research_topics     │
                              │  posts / articles    │
                              │  engagement_actions  │
                              │  metric_snapshots    │
                              │  strategy_reports    │
                              │  notifications       │
                              └──────────────────────┘
                                         ▲
                                         │ daily snapshot @ 11 PM ET
                                         │ daily summary  @ 8:30 PM ET
                                         │ weekly report  @ Sun 8 PM ET
                                         │
                              ┌──────────────────────┐
                              │  ANALYTICS           │
                              │  Collectors (LI+SS)  │
                              │  Benchmarks · Goals  │
                              │  Claude reports      │
                              └──────────────────────┘
```

### 2.1 Research → Generate

`services/research/searcher.py` rotates domain-specific Tavily queries across `ai_ml`, `software_eng`, `sre_infra`, `data_eng`. For each promising result, `deep_dive.py` fetches 2-4 source URLs concurrently (semaphore-bounded), extracts substantive text, and calls Claude with `RESEARCH_SYNTHESIS_PROMPT` from [`prompts.py`](backend/services/content/prompts.py). Output is a structured JSON with `summary`, `key_facts`, `why_it_matters`, `trade_offs`, `suggested_voice`, `confidence`.

`scorer.py` computes `0.25*recency + 0.25*signal + 0.25*uniqueness + 0.25*audience_fit`, dedupes against existing `new`/`assigned` topics via cosine similarity (threshold 0.85), and inserts with `status='new'`. Topics with Claude confidence < 5 are discarded.

The Content Creator picks up rows where `status='new'`, marks them `assigned` as it consumes them, and `used` once content is generated.

### 2.2 Generate → Queue

`services/content/calendar.py` decides pairing per topic: deep substantive topics → `paired` (LinkedIn teases, Substack delivers depth); lighter takes → `linkedin_only`; broad evergreen → `substack_only`.

`linkedin.py` and `substack.py` call Claude using prompts from [`prompts.py`](backend/services/content/prompts.py). Every generation prompt is injected with the `BANNED_PHRASES` blocklist. Generated content lands in `posts` / `articles` with `status='queued'` and `queued_at=now()`.

### 2.3 Queue → Publish

The `queue-check` Celery task runs every 5 minutes ([`queue_manager.py:18`](backend/services/publishing/queue_manager.py:18)). It selects rows where `status='queued' AND queued_at <= now() - 1 hour` and calls `publish_post()` / `publish_article()`.

LinkedIn publish ([`linkedin_api.py`](backend/services/publishing/linkedin_api.py)) uses the official UGC API with OAuth2. Substack publish ([`substack_auto.py`](backend/services/publishing/substack_auto.py)) drives a Playwright browser session: login, paste markdown-converted content into the editor, publish.

Both writers set `linkedin_post_id` / `substack_url` and flip `status='published'`. Idempotency is enforced by checking those columns at the top of every publish call.

### 2.4 Engage

`services/engagement/replier.py` polls LinkedIn for new comments on the user's published posts (last 7 days). Each comment is run through `safety.py` first — political/inflammatory/spam/self-promo content is silently dropped, never replied to. Surviving comments get a Claude-generated reply that must add substance (insight, resource, clarification, or thoughtful follow-up question). Replies are spaced 3-8 minutes apart with jitter.

### 2.5 Analytics

`collectors.py` pulls fresh metrics from LinkedIn (impressions, likes, comments, shares, profile views, follower count, CTR) and Substack (subscribers, opens, open rate, click rate). Daily snapshots are **append-only** in `metric_snapshots` — never updated, never overwritten. This preserves the full history for trend analysis.

`benchmarks.py` maintains a hardcoded reference table of LinkedIn averages for tech content (sourced from published industry reports, updated quarterly). `goals.py` recomputes `current_value` and progress on every collection run.

`report_generator.py` produces three tiers:
- **Real-time dashboard**: latest `metric_snapshots` + live API queries
- **Daily summary** (8:30 PM ET): today's posts, comments, replies, deltas, failures
- **Weekly deep dive** (Sun 8 PM ET): top/bottom posts with Claude-written explanations, week-over-week trends, benchmark comparison, goal progress. Observations only — never prescriptive.

---

## 3. Service boundary rules

Services live in `backend/services/<domain>/`. Each domain has its own `router.py` (FastAPI APIRouter) and service modules.

**Hard rule**: no cross-service imports. `from services.analytics import ...` inside `services.content` is banned. The reason: keeping the boundary surfaced through Postgres rows and Celery tasks means any service can be paused, restarted, or replaced without breaking the others.

Communication channels between services:

| Channel | When to use |
|---|---|
| **Postgres rows** | Most cross-service handoffs. One service writes `status='new'`, another polls for it. |
| **Celery tasks** | When the producing service needs to enqueue work for another async pipeline step. Import is `from services.scheduler.tasks import ...` only, never the service module directly. |
| **`user_settings` table** | All runtime config (schedules, tones, SMTP details, posting times). Read by every service at task entry. |
| **HTTP** | Only the frontend → backend boundary. Internal services never talk over HTTP. |

`models/` holds SQLAlchemy ORM only — no business logic. `services/content/prompts.py` is the **single source of truth** for every Claude prompt; inline prompts anywhere else are a bug.

---

## 4. Scheduling

Defined in [`services/scheduler/orchestrator.py`](backend/services/scheduler/orchestrator.py). RedBeat persists the schedule to Redis so beat restarts don't double-fire missed tasks.

| Task | Cron (UTC) | ET equivalent |
|---|---|---|
| `research-sweep-morning` | `0 13 * * *` | 8 AM ET |
| `research-sweep-evening` | `0 23 * * *` | 6 PM ET |
| `content-generation` | `0 2 * * *` | 9 PM ET (prev day) |
| `queue-check` | `*/5 * * * *` | every 5 min |
| `engagement-sweep` | `0 */4 * * *` | every 4 hr |
| `metric-collection` | `0 4 * * *` | 11 PM ET |
| `daily-summary` | `30 1 * * *` | 8:30 PM ET |
| `morning-email` | `0 12 * * *` | 7 AM ET |
| `evening-email` | `0 2 * * *` | 9 PM ET |
| `weekly-report` | `0 1 * * 1` | Sun 8 PM ET |

Every task is also triggerable on demand: `POST /api/scheduler/trigger/{name}` or via `scripts/manual_trigger.py`.

---

## 5. Key invariants

These are the load-bearing properties of the system. Removing or weakening any of them changes the behavior contract.

### 5.0 Per-user data isolation

Every model except `research_topics` is scoped by `user_id`. Every API route (except `/api/auth/*` and the LinkedIn OAuth callback) depends on `get_current_user` and filters queries by `Model.user_id == user.id`. Forgetting that filter in a new endpoint is a cross-tenant data leak — it's not a "best practice," it's a correctness invariant.

The vector store reinforces this at the index layer: `KIND_POSTS` and `KIND_ARTICLES` collections store `user_id` in each point's payload, and `search_posts` / `search_articles` always pass `filter_payload={"user_id": str(user_id)}`. Even a buggy query can't return another user's vectors.

### 5.1 The 1-hour queue is the only human-in-the-loop seam

Content moves to `status='queued'` with `queued_at=now()` at the moment of generation. The queue checker only publishes when `queued_at + 1 hour <= now()`. During that hour the user can edit, cancel, reschedule, or approve-now from the dashboard. After the hour, it ships without further confirmation.

This is the entire override mechanism. There is no nightly review step, no morning approval batch — just the one-hour window per item.

### 5.2 Publish is idempotent

Every publish path checks `linkedin_post_id` (posts) or `substack_url` (articles) before calling the external API. If set, the function returns `{"status": "already_published"}` and exits. This makes retries safe and prevents double-posting from Celery's at-least-once delivery.

### 5.3 Engagement is reactive-only

The system replies to comments **on its own published posts**. It never originates a comment on someone else's content. This is a scope boundary, not a configuration — it's enforced by `replier.py` only ever querying the comments endpoint scoped to the user's `linkedin_post_id` list.

### 5.4 Prompts are centralized

[`backend/services/content/prompts.py`](backend/services/content/prompts.py) is the only place Claude system prompts live. Every generation function imports from there. This makes the `BANNED_PHRASES` blocklist actually audit-able and prompt changes a single-file diff.

### 5.5 Analytics is observational, not prescriptive

Reports describe what happened and how it compares to benchmarks. They never auto-adjust the posting schedule, voice mix, or topic weighting. The human reads the weekly deep-dive and updates `user_settings` themselves if anything needs to change.

### 5.6 Metric snapshots are append-only

`metric_snapshots` rows are inserted daily and never updated. Trend math depends on the full history; an `UPDATE` would silently corrupt week-over-week deltas.

### 5.7 Tests never hit real external APIs

Tests use SQLite in-memory and mock every external call — Claude, Tavily, LinkedIn, Substack, SMTP. There is no "integration test against live LinkedIn" mode.

---

## 6. Failure modes & resilience

### Celery task retries

All tasks declare `max_retries=3` with exponential backoff (60s, 120s, 240s). After all retries are exhausted, the failure is logged to the `notifications` table with `type='error'` and an SMTP alert is sent.

### LinkedIn circuit breaker

If a LinkedIn API call returns 429, the breaker is opened by writing `linkedin_circuit_open_until = now() + 1 hour` to `user_settings`. Every subsequent LinkedIn call checks this key and returns early. This prevents cascading rate-limit failures and reduces the risk of account-level penalties.

### Token expiry

LinkedIn access tokens last 60 days. The refresh flow lives in [`linkedin_api.py`](backend/services/publishing/linkedin_api.py). A 401 from any LinkedIn call triggers a refresh attempt before retrying. If the refresh fails, a notification + email is dispatched and the breaker is opened.

### Substack session loss

Playwright sessions are stored in the `playwright_data` volume. If login fails (Substack UI change, 2FA prompt, password rotation), the article is saved as `status='draft'` instead of published, and an error notification fires. Brittle selectors are documented inline in `substack_auto.py`.

### Search API outage

If Tavily returns errors, `searcher.py` falls back to Serper. If both fail, the research sweep logs a warning and exits cleanly — the missed sweep is not retried; the next scheduled sweep handles it.

### Health check

`GET /api/health` reports the status of Postgres, Redis, LinkedIn auth presence, Substack credentials, SMTP config, Tavily reachability, and Anthropic config. Returns `degraded` (with a per-service breakdown) rather than `error` so the dashboard stays functional during partial outages.

---

## 7. Data model

Schema lives in [`backend/models/`](backend/models/). Migrations in [`backend/migrations/versions/`](backend/migrations/versions/).

| Table | Scope | Purpose |
|---|---|---|
| `users` | global | Account list with email, password_hash, role (admin/user), is_active |
| `user_credentials` | per-user | Encrypted LinkedIn / Substack / SMTP-to / MCP-token blobs |
| `research_topics` | **shared** | Synthesized topics with sources + score + domain + status (cross-user pool) |
| `posts` | per-user | LinkedIn posts (FK → `users`, `research_topics`, optional FK → `articles`) |
| `articles` | per-user | Substack articles (FK → `users`, `research_topics`, optional FK → `posts`) |
| `engagement_actions` | per-user | Comments seen on the user's own posts + replies sent |
| `metric_snapshots` | per-user | Append-only daily metric history (LinkedIn + Substack) |
| `strategy_reports` | per-user | Daily summaries and weekly deep-dives (JSONB body) |
| `goals` | per-user | User-defined targets with current value + status |
| `notifications` | per-user | Dashboard alerts (errors only); `emailed` flag tracks SMTP send |
| `user_settings` | per-user | Key/value JSONB: posting schedule, tones, domains, breaker state |
| `embedding_records` | per-user (nullable for research) | Provenance for Qdrant vectors — `user_id` is NULL for KIND_RESEARCH (shared) |

### Circular FK between Post and Article

`posts.linked_article_id → articles.id` and `articles.linked_post_id → posts.id` form a cycle. The migration creates both tables first, then adds the FK on `articles` afterward. The ORM resolves the cycle with explicit `foreign_keys=` on both `relationship()` declarations. See the "Common Pitfalls" section in [CLAUDE.md](CLAUDE.md) before touching these models.

---

## 7a. Auth & credentials (`services/auth/`, `services/credentials/`)

### Auth flow

1. **Signup** (`POST /api/auth/signup`) — email + password + optional name. First account auto-promoted to admin. Password is bcrypt-hashed. Returns a JWT (HS256, 24h TTL).
2. **Login** (`POST /api/auth/login`) — verifies bcrypt hash, updates `last_login_at`, returns JWT.
3. **Subsequent requests** — frontend stores the JWT in `localStorage` and attaches `Authorization: Bearer <token>` via `src/lib/api.ts`. The backend's `get_current_user` dependency decodes the token, loads the User row, and rejects if missing/disabled.

### Credential storage

User-provided credentials (LinkedIn refresh tokens, Substack passwords) live in `user_credentials.secret_payload` as Fernet ciphertext. The Fernet key is derived from `APP_SECRET_KEY`:

```python
key = base64.urlsafe_b64encode(hashlib.sha256(APP_SECRET_KEY.encode()).digest())
```

This means rotating `APP_SECRET_KEY` invalidates all stored credentials and all active JWTs simultaneously. That's by design — there's no separate KMS for a single-deployment system. After rotation, users log in again and re-enter their LinkedIn / Substack creds.

Non-sensitive context (LinkedIn person URN, Substack publication URL) lives plaintext in `user_credentials.metadata_payload`.

### LinkedIn OAuth — Authlib + per-user Developer App credentials

Each user saves Client ID / Secret in Settings (`user_credentials.linkedin_app`, encrypted). OAuth uses **Authlib** [`linkedin_oauth.py`](backend/services/publishing/linkedin_oauth.py) (`AsyncOAuth2Client`):

1. `create_authorization_url()` — Authlib builds the authorize URL; `state` is a signed `user_id` (itsdangerous). Redirect URI defaults to `{APP_PUBLIC_URL}/api/publish/linkedin/callback` (Vite proxies `/api` in dev).
2. User authorizes on LinkedIn; LinkedIn redirects to the callback with `code` + `state`.
3. `exchange_authorization_code()` + OpenID userinfo — tokens and person URN saved to `user_credentials.linkedin`; browser redirected to Settings.

The callback router is mounted **without** `require_verified_user` — LinkedIn redirects an unauthenticated browser. The signed `state` is the only authentication.

### Personal MCP tokens

External Claude clients (Claude Code / Desktop) need to authenticate to the Knowledge MCP. Each user generates a personal token via `POST /api/credentials/mcp-token` — returned once, then we store only the SHA-256 hash. The Knowledge MCP middleware hashes each incoming bearer token and looks up the owning user.

---

## 8. AI infrastructure layer (`services/ai/`)

Every Claude call and every embedding call goes through this layer. Direct SDK use is forbidden.

### 8.1 Model router

`pick_model(task)` resolves the single operator-configured model from `LLM_PROVIDER` and `LLM_MODEL` into a **provider-qualified model ID** like `"anthropic/claude-sonnet-4-6"`, `"openai/gpt-5-mini"`, or `"gemini/gemini-2.5-flash"`.

There are no model tiers and no per-task model overrides. If either `LLM_PROVIDER` or `LLM_MODEL` is missing, the call logs an error, creates an admin notification, and raises a configuration error.

### 8.2 LLM client

`generate()` / `generate_json()` (in `services/ai/llm_client.py`) wrap `litellm.acompletion`. LiteLLM gives us a single normalized interface for every provider — Anthropic, OpenAI, Google Gemini, Mistral, Groq, DeepSeek, xAI, OpenRouter, and ~100 others.

On every call:
1. `pick_model(task)` resolves the model ID.
2. If the model's provider supports prompt caching (Anthropic today) AND `ANTHROPIC_PROMPT_CACHING=true`, the system prompt is wrapped with `cache_control: {type: "ephemeral"}`. Other providers see plain string content and skip the feature.
3. If `mcp_servers=[...]` is passed AND the provider supports MCP (Anthropic today), the param is attached with the appropriate beta header. On other providers, the MCP servers are silently dropped with a debug log — generation still works, just without tool access.
4. Token usage is logged structured (`llm_call task=... model=... input=... output=... cache_read=...`) for cost attribution.

`generate_json()` parses the response and retries once with `temperature=0` if the first response isn't valid JSON. We deliberately don't pass `response_format={"type":"json_object"}` — support varies across providers, and a prompt-level instruction + parse retry is portable.

### 8.2.1 Why LiteLLM and not hand-rolled adapters

We need to support ~5+ LLM providers. Writing and maintaining N adapters multiplies code that's already commodity. LiteLLM is the standard pragmatic choice: one library, one response shape (OpenAI-style), pass-through of provider-specific kwargs when needed, and continuous coverage of new model releases. The only place we still talk to a provider SDK directly is the Anthropic-specific `cache_control` and `mcp_servers` parameters — and even those go through LiteLLM, which routes them appropriately.

The catalogue (`services/ai/providers.py`) is only a UI hint list. Any LiteLLM-compatible provider/model pair can be used through env configuration.

### 8.3 Embedding provider abstraction

`EmbeddingProvider` is an ABC; concrete implementations live in `embeddings.py` — `VoyageEmbedder`, `OpenAIEmbedder`, `CohereEmbedder`. Each declares its `model_id` and `dimensions`. `get_active_embedder()` resolves the active provider+model from settings and caches the instance.

`invalidate_embedder_cache()` is called from the settings router when the user changes the active model — necessary because the cache is keyed on `(provider, model)` and a settings update needs to force re-resolution.

### 8.4 Vector store (Qdrant)

`VectorStore` is a process-wide singleton wrapper around `AsyncQdrantClient`. Collections are named `{kind}__{model_id_safe}` — e.g., `research__voyage_3`, `posts__text_embedding_3_small`. The model ID is part of the collection name so that switching providers doesn't silently mix vectors from different embedding spaces.

Four kinds: `research`, `posts`, `articles`, `sources`. New kinds get added to `_VALID_KINDS` in `vector_store.py` — string literals at call sites are rejected.

`ensure_collection()` creates the collection lazily on first upsert per kind. `upsert_batch()` is the bulk path used by re-embed jobs. `search()` accepts an optional `filter_payload` for domain-scoped queries (e.g. find posts in `ai_ml` only).

### 8.5 Re-embed flow

When `user_settings.embedding_active` changes:

1. `settings_router._handle_side_effects()` calls `invalidate_embedder_cache()` and enqueues `reembed_corpus.delay()`.
2. The Celery task `reembed_corpus` runs `services.ai.reembed.reembed_corpus()`.
3. For each kind (`research`, `posts`, `articles`), the task:
   - Loads all canonical rows from Postgres.
   - Subtracts rows that already have an `EmbeddingRecord` for the active model.
   - Batches the remainder (32 at a time), embeds them, upserts into the new Qdrant collection, and records provenance in `embedding_records`.
4. Until the task completes, the old collection is still there — queries against the new collection just return fewer results during the migration window.

The job is idempotent: running it twice does nothing the second time.

### 8.6 Where the AI layer touches the rest of the system

| Service | What it uses |
|---|---|
| `research/deep_dive.py` | `generate_json("research_synthesis", ...)` and `check_cache()` against `KIND_RESEARCH` before re-fetching sources |
| `research/scorer.py` | Semantic dedup via `vector_store.search()` (replaces n-gram heuristic; falls back to n-gram if Qdrant is unreachable) |
| `content/linkedin.py` | `generate()` for posts; `_retrieve_voice_examples()` pulls prior posts from `KIND_POSTS` as anchoring context |
| `content/substack.py` | `generate_json()` for articles; voice examples from `KIND_ARTICLES` |
| `publishing/linkedin_api.py`, `substack_auto.py` | Call `index_published_post()` / `index_published_article()` on success — the engine's accumulated voice corpus grows automatically |
| `engagement/replier.py` | `generate("comment_reply", ...)` |
| `analytics/report_generator.py` | `generate("weekly_deep_dive", ...)` — the only call that hits Opus tier by default |

---

## 9. MCP servers

The system runs two MCP servers as containers. Both are reachable from the backend over the docker network; the Knowledge MCP is also exposed publicly with bearer-token auth.

### 9.1 Tavily MCP (internal)

`mcp/tavily:latest` image, port 8001. Exposes Tavily search as MCP tools. The backend passes its URL to `claude_client.generate()` via `mcp_servers=[{"type": "url", "url": ..., "name": "tavily-search"}]` when a generation task can benefit from live web search.

This is **complementary** to the direct Tavily calls in `services/research/searcher.py` — the research sweep stays deterministic (we want predictable daily output), but Claude can pull additional context during generation if it judges that helpful.

### 9.2 Knowledge MCP (internal + external)

Custom server in `backend/mcp_servers/knowledge/server.py`, port 8002. Same backend image; different entrypoint command.

Exposes five tools:

- `search_research(query, limit, domain?)` — semantic search over prior research topics
- `search_posts(query, limit, domain?)` — search published LinkedIn posts
- `search_articles(query, limit, domain?)` — search published Substack articles
- `get_research_topic(topic_id)` — full topic with sources + synthesis
- `list_recent_topics(limit, domain?)` — recent additions

**Internal use**: generation calls pass the URL via `mcp_servers=[...]` so Claude can pull voice-consistency examples on demand without the backend pre-computing them.

**External use**: point Claude Code / Claude Desktop at `http://<vm_ip>:8002` with `Authorization: Bearer $MCP_KNOWLEDGE_TOKEN`. The user can then ask their daily Claude tool "what have I written about Rust async runtimes?" and get back ranked excerpts from their own corpus.

### 9.3 Auth model

Internal docker-network requests go to `http://knowledge-mcp:8002` without auth. External requests must include the bearer token configured in `MCP_KNOWLEDGE_TOKEN`. The token is stored in Secret Manager on GCP and rotates independently of other credentials.

---

## 10. GCP deployment (`infra/terraform/`)

The production target is a single Compute Engine VM running the same docker-compose stack used in dev. ~$15-20/month at `e2-small`.

### 10.1 What Terraform provisions

| Resource | Purpose |
|---|---|
| `google_compute_instance.engine` | The VM running docker-compose |
| `google_compute_address.static` | Static external IP |
| `google_compute_firewall.{ssh,dashboard}` | Lock SSH and dashboard ports to allowed CIDRs |
| `google_artifact_registry_repository.containers` | Docker registry for `backend` and `frontend` images |
| `google_secret_manager_secret.*` | One secret per credential (~20 secrets) |
| `google_service_account.vm` | The VM's identity; has `secretAccessor` + `artifactregistry.reader` |
| `google_service_account.deployer` | GitHub Actions impersonates this for deploys |
| `google_iam_workload_identity_pool.github` + provider | Federation so Actions doesn't need a JSON key |

### 10.2 Cold-boot flow

VM startup (`startup.sh`):

1. Install Docker + Compose plugin if not present.
2. `gcloud auth configure-docker` for Artifact Registry.
3. Clone the repo to `/opt/content-engine` (or `git fetch && reset --hard origin/main` if already cloned).
4. Build `.env` by reading every secret from Secret Manager via `gcloud secrets versions access latest`.
5. `docker compose -f docker-compose.yml -f docker-compose.prod.yml pull && up -d`.
6. `alembic upgrade head`.

The startup script is idempotent — safe to re-run after a reboot or manual SSH.

### 10.3 CI/CD flow

`.github/workflows/deploy.yml` on push to `main`:

1. Authenticate to GCP via WIF (no JSON key).
2. `docker buildx build --push` backend and frontend images, tagged with the commit SHA and `:latest`.
3. SSH into the VM via IAP tunnel.
4. `git fetch && reset --hard`, `docker compose pull && up -d`, `alembic upgrade head`.
5. Poll `/api/health` for up to 50 seconds — fail the deploy if it never returns OK.

`.github/workflows/ci.yml` runs on every PR:

- Backend pytest with SQLite in-memory and mocked external APIs.
- Frontend `tsc --noEmit` + `npm run build`.
- `terraform validate` + `terraform fmt -check`.

---

## 11. Why these choices

| Decision | Reason |
|---|---|
| Celery + Beat over cron jobs | Need retries, dead-letter via notifications, dynamic schedule from `user_settings`, and a worker pool. |
| RedBeat over the default scheduler | Stores schedule in Redis instead of a local file — survives `beat` container restarts without re-firing missed tasks. |
| Async everywhere in the backend | All external IO (Claude, Tavily, LinkedIn, SMTP) is network-bound; async lets one request fan out to several calls without thread overhead. |
| Postgres for queue state, not Redis | The 1-hour queue is also editable from the dashboard. Putting it in Postgres means one source of truth — the same row the user edits is the one the queue checker reads. |
| Centralized prompts | Auditing AI output requires a single place to read all prompts. Inline prompts make banned-phrase enforcement impossible. |
| Model tier router instead of one model | A 3 LinkedIn post / week pace means the cheap-task volume (research synthesis, dedup, comment replies) dwarfs the creative work. Routing Haiku (or GPT-5 nano, or Gemini Flash Lite) for the high-volume tier is a 5-10x cost reduction without measurable quality loss on those tasks. |
| Multi-provider via LiteLLM, not Anthropic-only | Different providers win at different things. Groq is ~10x faster on Llama. Gemini is competitive on cost for high-volume tasks. DeepSeek R1 is strong on reasoning at a fraction of premium-tier cost. Forcing everything onto one provider gives up wins for no real benefit. LiteLLM removes the adapter cost so we can switch freely. |
| Prompt caching on system prompts | The content generation system prompts are 1500-2500 tokens and identical across all calls of the same task. 90% discount on cached tokens makes generation effectively cost-of-output. |
| Qdrant over pgvector | Better filtering / payload queries / batch upsert performance. Separate container is a cost we already accept for Redis. The day we want to do hybrid search or quantized vectors, we don't have to migrate. |
| Per-(kind, model) collections | A vector DB silently breaks if you change the embedding model — old vectors and new queries live in different spaces. Scoping by model means we can re-embed in the background while the old collection stays queryable. |
| Knowledge MCP for both internal and external | Same server serves the backend's Claude calls (voice anchoring) and the user's Claude Code (interactive query). One implementation, two consumers, no duplication. |
| Single VM on GCP, not Cloud Run / GKE | Docker-compose stack maps directly onto a VM; Cloud Run requires splitting Celery worker / beat / Playwright across multiple service types. Cost difference is ~3-5x at this scale ($15/mo vs $50-80/mo) with no operational benefit for a single-user system. |
| Workload Identity Federation, not JSON keys | GitHub Actions secrets shouldn't include long-lived GCP keys. WIF gives Actions the right to impersonate the deployer SA only when the OIDC token's `repository` matches. |
| Single-user, no auth complexity | Dashboard password is the only credential. No multi-user means no row-level scoping, no role logic, no token cookies. |
| Tailwind only, no component library | The dashboard is the daily interface — visual consistency comes from constraints, not from importing a library that we'd then customize. |
| SQLite in tests | Fast in-memory, no fixture setup. Trade-off: tests can't rely on Postgres-only features (JSONB operators, ARRAY behavior). |
