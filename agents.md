# Content Engine — Agent Definitions

This document defines every autonomous agent in the system: what it owns, what it does, what it reads and writes, and how it coordinates with other agents.

All agents are implemented as Celery tasks that wrap async service functions. They communicate through the database — never through direct imports across service boundaries.

Every agent that calls Claude or computes embeddings goes through `services/ai/` (model router, claude_client, embeddings, vector_store). Direct SDK use is forbidden — see [CLAUDE.md](CLAUDE.md) pitfall #7.

The system is multi-user: most agents iterate over `users WHERE is_active = true` and execute per-user. Research is the one exception — it's a shared cross-user pool. See [ARCHITECTURE.md §0](ARCHITECTURE.md) for the full tenancy table.

---

## Agent: AI Infrastructure (shared)

**Service directory**: `backend/services/ai/`

**Responsibilities**:
- Resolve the single configured LLM from `LLM_PROVIDER` + `LLM_MODEL` via `model_router.pick_model`
- Wrap every LLM call with prompt caching where supported, token-usage logging, and retries (`llm_client.generate` / `generate_json`)
- Provide a swappable embedding provider abstraction (Voyage / OpenAI / Cohere)
- Manage Qdrant collections scoped by `(kind, embedding_model_id)` so changing models doesn't silently corrupt retrieval
- Re-embed the corpus into a new collection when the active embedding model changes (`reembed_corpus` Celery task, idempotent)
- Embed published posts and articles into the vector store on publish-success (called from publishing agents)

**Key files**:
- `model_router.py` — single configured provider/model resolver with missing-config notifications
- `llm_client.py` — LiteLLM wrapper; the single LLM entrypoint
- `embeddings.py` — `EmbeddingProvider` ABC and concrete implementations
- `vector_store.py` — Qdrant wrapper, kind constants (`KIND_RESEARCH`, `KIND_POSTS`, `KIND_ARTICLES`)
- `ingestion.py` — `index_published_post()` / `index_published_article()` helpers
- `reembed.py` — corpus re-embed logic
- `mcp_servers.py` — builds the `mcp_servers` list for Claude calls that want MCP tool access

**Reads from DB**: `user_settings`, `embedding_records`, `research_topics`, `posts`, `articles`
**Writes to DB**: `embedding_records` (provenance); Qdrant for the vectors themselves

**Hard constraints**:
- Every Claude call across the codebase routes through `claude_client.generate()` or `generate_json()`. No exceptions.
- Every embedding call goes through `get_active_embedder()`. No direct provider HTTP calls outside `embeddings.py`.
- Collection names always use `KIND_*` constants. Never raw string literals.
- The re-embed task is idempotent — it must remain safe to run multiple times.

**Schedule**: Reactive — runs when `user_settings.embedding_active` changes (enqueued by the settings router).

---

## Agent: Research Analyst

**Service directory**: `backend/services/research/`

**Responsibilities**:
- Query Tavily (primary) and Serper (fallback) search APIs with rotating domain-specific queries
- Fetch 2-4 source URLs per promising result and extract text content
- Call Claude API to synthesize raw source material into structured research notes
- Score topics with composite formula: `0.25*recency + 0.25*signal + 0.25*uniqueness + 0.25*audience_fit`
- Deduplicate against recent topics using n-gram cosine similarity (threshold: 0.85)
- Persist new topics with status `new`

**Key files**:
- `searcher.py` — search execution, domain query rotation, sweep orchestration
- `queries.py` — AI-heavy Tavily query lists and per-domain sweep counts (3:1:1:1)
- `deep_dive.py` — URL fetch, text extraction, Claude API synthesis call
- `scorer.py` — scoring formula, dedup logic, DB persistence
- `router.py` — API endpoints: list, trigger sweep, pin/archive

**Reads from DB**: `research_topics` (for deduplication)
**Writes to DB**: `research_topics` (inserts new topics)

**Hard constraints**:
- AI-heavy sweep weighting: 3 Tavily searches for `ai_ml`, 1 each for `software_eng`, `sre_infra`, and `data_eng` per sweep (queries in `services/research/queries.py`). Content generation still respects per-user domain prefs.
- Topics with confidence < 5 from Claude synthesis are discarded before storing
- All Claude synthesis prompts come from `prompts.py` — no inline prompts
- Claude calls go through `services.ai.claude_client.generate_json("research_synthesis", ...)` — routed to Haiku tier
- Max 3 concurrent source fetches per topic during deep-dive (`deep_dive.py`)
- Dedup is semantic (Qdrant vector search) with n-gram fallback when Qdrant is unreachable
- Before deep-diving, `deep_dive.check_cache()` queries `KIND_RESEARCH` — if a recent topic is >85% similar, the synthesis is reused and Tavily / Claude calls are skipped entirely
- After storing a new topic, embed it into Qdrant and write an `embedding_records` row

**Schedule**: Twice daily (8 AM ET, 6 PM ET). Also triggerable manually.

**Output to next stage**: Sets topic `status = "new"` — the Content Generation agent picks these up.

---

## Agent: Content Creator

**Service directory**: `backend/services/content/`

**Responsibilities**:
- Select top unassigned research topics (ranked by relevance_score), balanced across domains
- Decide content strategy per topic: `paired` | `linkedin_only` | `substack_only` (via Claude API)
- Generate LinkedIn posts: 1,200-1,800 chars, hook-first, with 3-5 hashtags, ≤2 emojis
- Generate Substack articles: 1,500-3,000 words, markdown, code blocks where relevant
- Link paired posts and articles via `linked_article_id` / `linked_post_id`
- Set status to `queued` with `queued_at = now()`
- Mark source research topic as `assigned`

**Key files**:
- `prompts.py` — ALL system prompts (research synthesis, LinkedIn, Substack, pairing, engagement, analytics)
- `linkedin.py` — LinkedIn post generation, quality validation, banned phrase detection
- `substack.py` — Article generation, quality validation
- `calendar.py` — Pairing decision, domain-balanced topic selection, scheduling slot calculation
- `router.py` — API endpoints: CRUD for posts/articles, generate-for-topic, calendar

**Reads from DB**: `research_topics` (status=new), `user_settings` (posting_schedule, tone_preferences), `posts`/`articles` (for scheduling conflict detection)
**Writes to DB**: `posts`, `articles`, updates `research_topics.status = "assigned"`

**Hard constraints**:
- Every Claude call uses a prompt from `prompts.py`. Zero inline prompts.
- Claude calls go through `services.ai.claude_client.generate("linkedin_post", ...)` / `generate_json("substack_article", ...)` — routed to Sonnet tier by default
- Before generation, `_retrieve_voice_examples()` pulls up to 3 prior posts (or 2 prior articles) on the same domain from Qdrant and injects them as voice anchors in the user prompt. The engine's voice compounds over time without prompt bloat.
- Quality validation runs on every generated post and article. Violations are logged but do not block saving — they create warnings.
- No 3 consecutive posts in the same domain
- Max 3 new posts per content generation run (prevents spam)
- Banned phrases list is enforced in validation AND injected into every prompt

**Schedule**: 9 PM ET daily. Also triggerable manually per-topic.

**Output to next stage**: Posts/articles with `status = "queued"` — the Publishing agent picks these up.

---

## Agent: Publisher

**Service directory**: `backend/services/publishing/`

**Responsibilities**:
- Monitor the 1-hour queue: publish any item where `queued_at + 60min <= now()` and `status = "queued"`
- Publish LinkedIn posts via official LinkedIn UGC API (OAuth2)
- Publish Substack articles via Playwright browser automation
- Implement idempotency: check `linkedin_post_id` / `substack_url` before publishing
- Manage LinkedIn OAuth2 token lifecycle (exchange code, detect expiry)
- Implement circuit breaker: on 429 from LinkedIn, pause all LinkedIn calls for 1 hour via `user_settings`
- Update post/article status to `published` or `failed`

**Key files**:
- `linkedin_api.py` — OAuth2, token management, post publishing, metrics fetch, circuit breaker
- `substack_auto.py` — Playwright login, editor interaction, publish flow
- `queue_manager.py` — 1-hour queue processor
- `router.py` — API endpoints: publish-now, OAuth callback

**Reads from DB**: `posts` (status=queued), `articles` (status=queued), `user_settings` (circuit_breaker)
**Writes to DB**: Updates `posts.status`, `posts.linkedin_post_id`, `posts.published_at`; same for `articles`

**Hard constraints**:
- ALWAYS check `linkedin_post_id` / `substack_url` before publishing. If set, return early. Never double-post.
- Circuit breaker must be checked before every LinkedIn API call.
- On publish failure after all retries: set status=`failed`, create error notification.
- On publish success, call `services.ai.ingestion.index_published_post()` / `index_published_article()` — this is what feeds the engine's voice corpus over time. Errors in indexing must NOT block the publish-success response.
- Playwright selectors for Substack are documented in `substack_auto.py`. When Substack updates their UI, update selectors there and in `SETUP.md`.
- Never store plaintext LinkedIn/Substack credentials in the database. Credentials come from environment only.

**Schedule**: Queue check every 5 minutes. Also triggerable per-item from the dashboard.

---

## Agent: Engagement Manager

**Service directory**: `backend/services/engagement/`

**Responsibilities**:
- Poll LinkedIn API for new comments on published posts (last 7 days)
- Run each comment through `safety.py` filters before generating a reply
- Generate a reply via Claude API that adds genuine value (follow-up insight, resource, clarification, question)
- Post the reply with a randomized 3-8 minute delay between replies (rate limiting)
- Log all actions (including skipped) to `engagement_actions`

**Key files**:
- `replier.py` — comment polling, reply generation, reply posting, rate limiting
- `safety.py` — comment filters (political, spam, inflammatory), reply validation (anti-patterns, length)
- `router.py` — API endpoints: engagement log, trigger sweep

**Reads from DB**: `posts` (status=published, last 7 days), `engagement_actions` (dedup already-replied comments)
**Writes to DB**: `engagement_actions`

**Hard constraints**:
- Scope is STRICTLY reactive: replies to comments on my own posts only. Zero proactive commenting.
- Safety filter runs BEFORE reply generation. If `should_skip_comment()` returns True, skip. Do not generate a reply.
- Reply anti-patterns ("Great point!", "Thanks for sharing!", etc.) are validated after generation. If `validate_reply()` returns False, discard and do not post.
- Randomized delay (180-480 seconds) between posting replies. Never reply to multiple comments in rapid succession.
- Replies must be 2-5 sentences, 10-150 words.

**Schedule**: Every 4 hours. Also triggerable manually.

---

## Agent: Analytics Strategist

**Service directory**: `backend/services/analytics/`

**Responsibilities**:
- Collect daily metric snapshots from LinkedIn API and Substack
- Update `current_value` on all active goals; auto-mark goals as `achieved` or `missed`
- Generate daily summary reports (evening, via Claude API) and store in `strategy_reports`
- Generate weekly deep-dive reports (Sunday evening, via Claude API)
- Provide benchmark comparisons via `benchmarks.py`
- Calculate goal progress and projected completion dates

**Key files**:
- `collectors.py` — LinkedIn API metrics pull, Substack scrape, goal progress update
- `benchmarks.py` — Hardcoded LinkedIn/Substack benchmark reference data (update quarterly)
- `goals.py` — Progress calculation utilities
- `report_generator.py` — Daily and weekly report generation via Claude API
- `router.py` — API endpoints: metrics, benchmarks, reports, goals CRUD

**Reads from DB**: `posts` (metrics), `articles` (metrics), `metric_snapshots`, `goals`, `engagement_actions`
**Writes to DB**: `metric_snapshots` (append-only, never overwrite), `strategy_reports`, updates `goals.current_value`/`goals.status`

**Hard constraints**:
- Metric snapshots are APPEND-ONLY. Never update or delete a snapshot row.
- Reports are OBSERVATIONAL only — they surface patterns, not prescriptions. The user decides strategy changes.
- Benchmark values in `benchmarks.py` are hardcoded from published industry reports. Document the source. Update quarterly.
- Goal status auto-transitions: `current_value >= target_value → achieved`; `target_date < today AND current_value < target_value → missed`.

**Schedule**: Metric collection 11 PM ET daily. Daily report 8:30 PM ET. Weekly report Sunday 8 PM ET.

---

## Agent: Notification Service

**Service directory**: `backend/services/notifications/`

**Responsibilities**:
- Write error notifications to `notifications` table when any agent fails
- Write system notifications for events (daily summary ready, etc.)
- Send immediate SMTP alert emails for errors
- Send morning preview email (queued content for today + this week)
- Send evening recap email (published today + metrics + failures)

**Key files**:
- `notifier.py` — `create_error_notification()`, `create_system_notification()`
- `alerts.py` — Immediate error email via SMTP
- `email_digest.py` — Morning/evening digest construction and delivery; `send_email()` helper
- `router.py` — API endpoints: list notifications, mark read, unread count

**Reads from DB**: `posts`, `articles`, `engagement_actions`, `notifications`
**Writes to DB**: `notifications`

**Hard constraints**:
- Error alerts send SMTP email immediately (same call stack as `create_error_notification`).
- System notifications do NOT send email — they're informational dashboard updates only.
- If SMTP is not configured (`smtp_username` empty), log a warning and skip — never throw.
- Morning email: queued items in 1-hour window + scheduled this week.
- Evening email: published today + reply count + failures.

**Schedule**: Morning 7 AM ET, evening 9 PM ET. Error alerts are immediate.

---

## Agent: Scheduler / Orchestrator

**Service directory**: `backend/services/scheduler/`

**Responsibilities**:
- Define Celery Beat schedule for all tasks (via `orchestrator.py`)
- Provide thin Celery task wrappers that call async service functions (`tasks.py`)
- Expose manual trigger endpoints for every task (`router.py`)
- Handle task failure: after `max_retries=3` with exponential backoff, call `_notify_error()`

**Key files**:
- `orchestrator.py` — BEAT_SCHEDULE dict, `get_task_statuses()` for dashboard
- `tasks.py` — All Celery tasks. Thin wrappers only — delegate immediately to service functions.
- `router.py` — `POST /api/scheduler/trigger/{task_name}`

**Hard constraints**:
- Tasks are thin wrappers. No business logic in `tasks.py`.
- All tasks use `bind=True, max_retries=3`.
- Retry delays: 60s, 120s, 240s (exponential: `60 * 2^retries`).
- After all retries fail, call `_notify_error(title, message)`.
- Celery app is configured with `task_acks_late=True` and `task_reject_on_worker_lost=True` to prevent lost tasks.

**Schedule**: Beat runs continuously. Queue check every 5 minutes.

---

## Inter-Agent Coordination

### Pipeline flow
```
Research Analyst → (new topics in DB)
    → Content Creator → (queued posts/articles in DB)
        → Publisher → (published, linkedin_post_id/substack_url set)
            → Analytics Strategist → (metric_snapshots, reports)
            → Engagement Manager → (engagement_actions)
                → Notification Service → (notifications, emails)
```

### Feedback loops
- Content Creator reads `user_settings.tone_preferences` for voice guidance
- Analytics Strategist updates `goals.current_value` after each metric collection
- Circuit breaker in `user_settings` is checked by Publisher before every LinkedIn call
- All agents that fail call `create_error_notification()` which triggers Notification Service

### Manual overrides (dashboard)
- User can cancel any queued/scheduled item → sets `status = "cancelled"`, queue manager skips it
- User can approve any queued item → triggers immediate publish task
- User can reschedule → updates `scheduled_at`, resets `queued_at = None`, sets `status = "scheduled"`
- User can trigger any agent task manually via Settings page or API

### DB-mediated, not direct
Services communicate through shared DB tables. The `status` column on `posts` and `articles` is the handoff mechanism:
- `new` → Research Analyst output / manual draft input
- `queued` → Content Creator output, awaiting 1-hour window
- `scheduled` → Manually rescheduled, not in queue yet
- `published` → Publisher output
- `failed` → Publisher failed after all retries
- `cancelled` → User cancelled during queue window

---

## Adding a New Agent

1. Create `backend/services/<agent_name>/` directory with `__init__.py`, `router.py`, and service files.
2. Add API routes in `router.py`. Register the router in `backend/main.py`.
3. If the agent makes Claude API calls, add its prompts to `backend/services/content/prompts.py`.
4. If the agent runs on a schedule, add a Celery task in `tasks.py` (thin wrapper) and add it to `BEAT_SCHEDULE` in `orchestrator.py`.
5. Add the task name to `TASK_MAP` in `scheduler/router.py` for manual triggering.
6. Add a frontend page if the agent produces user-visible output.
7. Add tests in `backend/tests/test_<agent_name>.py`. Mock all external APIs.
8. Update this `agents.md` with the new agent definition.
9. Update `CLAUDE.md` if the new agent introduces new architecture patterns.
