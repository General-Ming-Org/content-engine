# Content Engine — Setup Guide

Complete walkthrough for getting the system running locally and deploying to GCP. The setup is split into **operator setup** (done once by whoever runs the deployment) and **per-user setup** (done by each user after signing up).

---

## Operator prerequisites

- Docker Desktop (Mac/Windows) or Docker Engine + Docker Compose (Linux)
- An Anthropic account for the shared API key: [console.anthropic.com](https://console.anthropic.com)
- A Tavily account: [tavily.com](https://tavily.com)
- An embedding provider account (Voyage / OpenAI / Cohere)
- Each user creates their own LinkedIn Developer App (configured in Settings)
- SMTP credentials for outbound mail (Gmail App Password / AWS SES / etc.)

## What each user provides themselves

- Their own LinkedIn Developer App + account (configured in Settings)
- Their own Substack account with email+password login (not Google/Apple SSO)
- An email address to receive their digest emails

---

## 1. Clone and Initial Configuration

```bash
git clone <your-repo-url> content-engine
cd content-engine
cp .env.example .env
```

Edit `.env` and fill in values as you complete each integration below.

---

## 2. Anthropic API Key

1. Go to [console.anthropic.com](https://console.anthropic.com)
2. Click **API Keys** → **Create Key**
3. Copy the key → set `ANTHROPIC_API_KEY=sk-ant-...` in `.env`
4. The system uses `claude-sonnet-4-20250514` by default (`ANTHROPIC_MODEL` in config)

---

## 3. Tavily API Key (Primary Search)

1. Sign up at [tavily.com](https://tavily.com)
2. Go to your dashboard → copy the API key
3. Set `TAVILY_API_KEY=tvly-...` in `.env`
4. Free tier: 1,000 searches/month. With 2 sweeps/day × ~8 queries = ~480/month — fits the free tier.
5. The same key is used by the Tavily MCP container (see section 4) — no separate setup.

**Optional: Serper fallback**
1. Sign up at [serper.dev](https://serper.dev)
2. Copy key → set `SERPER_API_KEY=` in `.env`
3. Used automatically if Tavily fails or returns no results.

---

## 4. Embedding Provider (Vector DB)

The engine stores research and published content as embeddings in Qdrant so it can dedup semantically, cache prior research, and use prior posts as voice anchors. Pick one provider:

**Voyage AI** (recommended, Anthropic-endorsed):
1. Sign up at [voyageai.com](https://www.voyageai.com)
2. Copy API key → set `VOYAGE_API_KEY=` in `.env`
3. Leave `EMBEDDING_PROVIDER=voyage` and `EMBEDDING_MODEL=voyage-3`

**OpenAI** (cheapest):
1. Get a key from [platform.openai.com](https://platform.openai.com/api-keys)
2. Set `OPENAI_API_KEY=`
3. Set `EMBEDDING_PROVIDER=openai` and `EMBEDDING_MODEL=text-embedding-3-small`

**Cohere**:
1. Get a key from [dashboard.cohere.com](https://dashboard.cohere.com/api-keys)
2. Set `COHERE_API_KEY=`
3. Set `EMBEDDING_PROVIDER=cohere` and `EMBEDDING_MODEL=embed-english-v3.0`

You can switch later via the Settings page in the dashboard — the system auto-enqueues a `reembed_corpus` Celery task that migrates everything into a new collection without losing the old one mid-flight.

Qdrant itself runs in docker-compose — no signup needed. Optionally set `QDRANT_API_KEY` if you'll expose Qdrant publicly (you shouldn't; the firewall blocks port 6333 by default in the Terraform setup).

---

## 5. MCP Servers

Two MCP servers run as docker-compose containers; both are reachable from the backend over the docker network.

- **Tavily MCP** (`tavily-mcp:8001`) — uses the `TAVILY_API_KEY` from section 3. No additional setup.
- **Knowledge MCP** (`knowledge-mcp:8002`) — custom server that exposes the vector DB.

For the **Knowledge MCP**, generate a bearer token if you want to query it from Claude Code or Claude Desktop externally:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

Set the result as `MCP_KNOWLEDGE_TOKEN` in `.env`. Internal docker-network requests bypass auth; external requests must include `Authorization: Bearer <token>`.

To use it from Claude Code, add to your MCP config:

```json
{
  "mcpServers": {
    "content-engine": {
      "url": "http://<vm-ip>:8002",
      "headers": { "Authorization": "Bearer <your-token>" }
    }
  }
}
```

Then ask Claude things like *"what have I written about Kubernetes operators?"* — it'll call `search_articles` / `search_posts` and return ranked excerpts from your own corpus.

---

## 6. LinkedIn Developer App (per user, in the web app)

LinkedIn requires an approved Developer App to post via API. **Each user configures their own app in Settings → LinkedIn** — follow the numbered steps in the UI (create app, copy redirect URL, paste Client ID / Secret, then connect account). Credentials are encrypted in the database; you do not need `LINKEDIN_CLIENT_ID` / `LINKEDIN_CLIENT_SECRET` in `.env` unless you want a legacy server-wide fallback.

The sections below mirror the in-app guide for reference.

### Step 1: Create the app
1. Go to [linkedin.com/developers/apps](https://www.linkedin.com/developers/apps)
2. Click **Create App**
3. Fill in: App name (e.g. "Content Engine"), Company page (you need a LinkedIn Company Page — create one if needed), Privacy policy URL (can be a placeholder for personal use), App logo
4. Click **Create App**

### Step 2: Add products
1. In your app, go to the **Products** tab
2. Request access to:
   - **Share on LinkedIn** — required for posting (`w_member_social` scope)
   - **Sign In with LinkedIn using OpenID Connect** — required for `r_member_social` and profile access
3. Both are typically auto-approved for personal developer accounts

### Step 3: Configure redirect URL and public API URL
1. Go to **Auth** tab in your LinkedIn app
2. Under **OAuth 2.0 settings**, add redirect URL (exact match required):
   ```
   http://localhost:3000/api/publish/linkedin/callback
   ```
3. Copy **Client ID** and **Client Secret** → paste them in **Settings → LinkedIn → Step 2** in the web app

**Docker Compose note:** The frontend proxies API calls to the internal hostname `http://backend:8000`. LinkedIn OAuth must use a **browser-reachable** callback URL, not that internal host. Set in `.env`:

```env
APP_PUBLIC_URL=http://localhost:3000
API_PUBLIC_URL=http://localhost:8000
```

`docker-compose.yml` sets `APP_PUBLIC_URL=http://localhost:3000` by default. The redirect URL registered in LinkedIn must equal `{APP_PUBLIC_URL}/api/publish/linkedin/callback` (the Vite dev server proxies `/api` to the backend). Do **not** register bare `http://localhost` — LinkedIn will show “Bummer, something went wrong”.

If you see *"The redirect_uri does not match the registered value"* and the authorize URL contains `redirect_uri=http://backend:8000/...`, restart the backend after setting `API_PUBLIC_URL` and try **Connect LinkedIn** again from Settings.

### Step 4: Connect from the dashboard
1. Start the stack: `docker compose up -d`
2. Sign in at http://localhost:3000
3. Open **Settings → LinkedIn**, save Client ID and Secret, then click **Connect LinkedIn**
4. Authorize on LinkedIn; you are redirected back to Settings with a success message

Tokens are stored per user in `user_credentials` (encrypted). No manual token copy into `.env` is required.

### Step 5: Production
Register your production callback in the LinkedIn app, e.g. `https://api.yourdomain.com/api/publish/linkedin/callback`, and set:

```env
APP_PUBLIC_URL=https://app.yourdomain.com
API_PUBLIC_URL=https://api.yourdomain.com
```

---

## 7. Substack (per-user)

Each user enters their own Substack credentials from the dashboard's Settings page after signing up. The values are Fernet-encrypted at rest using `APP_SECRET_KEY` as the derivation seed.

**User requirements**:
- Substack account using **email + password login** — not Google/Apple SSO. If you use SSO, set a direct password in Substack account settings first.
- 2FA: if enabled, automation will fail at the 2FA step. See troubleshooting below.

The Playwright login flow lives in `backend/services/publishing/substack_auto.py`. Selectors are documented inline and may break when Substack updates their editor.

### Legacy: Substack Playwright Automation (technical reference)

Substack has no official API. The system uses Playwright to automate the browser.

### Requirements
- Your Substack account must use **email + password login** — not Google/Apple SSO
- If you use Google/Apple SSO: in your Substack settings, go to **Account → Password** and set a direct password
- 2FA: if enabled on your Substack account, the automation cannot complete the login and will fail

### Configuration
```env
SUBSTACK_EMAIL=your@email.com
SUBSTACK_PASSWORD=your_substack_password
SUBSTACK_PUBLICATION_URL=https://yourname.substack.com
```

### Known brittle points
The Playwright automation in `backend/services/publishing/substack_auto.py` uses CSS selectors that may break when Substack updates their frontend. If Substack publishing starts failing:

1. Check the error log for the specific step that failed
2. Open `substack_auto.py` — brittle selectors are commented with their purpose
3. Open a browser, log in to Substack, inspect the current HTML, and update the selector
4. Common selectors to check: title field, subtitle field, body editor, publish button, confirm dialog

---

## 8. SMTP Email

The system sends morning/evening digest emails and immediate error alerts.

### Gmail (recommended for personal use)
1. Enable 2FA on your Google account: [myaccount.google.com/security](https://myaccount.google.com/security)
2. Generate an App Password: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
   - Select "Mail" and "Other (custom name)" → enter "Content Engine"
   - Copy the 16-character password
3. Set in `.env`:
   ```env
   SMTP_HOST=smtp.gmail.com
   SMTP_PORT=587
   SMTP_USERNAME=your@gmail.com
   SMTP_PASSWORD=xxxx xxxx xxxx xxxx   # the App Password
   SMTP_FROM_ADDRESS=your@gmail.com
   SMTP_TO_ADDRESS=your@gmail.com      # where to receive emails
   ```

### AWS SES
```env
SMTP_HOST=email-smtp.us-east-1.amazonaws.com
SMTP_PORT=587
SMTP_USERNAME=<SMTP username from SES>
SMTP_PASSWORD=<SMTP password from SES>
```

### Test your SMTP configuration
From the Settings page in the dashboard, click "Send test morning email" to verify delivery.

---

## 9. Running Locally + First Account

After Docker Compose is up, open the dashboard and create the first account:

```bash
docker compose up -d
docker compose exec backend alembic -c migrations/alembic.ini upgrade head
open http://localhost:3000
```

The first signup automatically becomes the admin. Additional signups are regular users by default — admins can promote/demote from the Users page.

### Per-user onboarding (every new user)

After signing up:

1. **Settings → Connect LinkedIn** — clicks through the operator's LinkedIn Developer App OAuth flow; tokens land encrypted in the DB.
2. **Settings → Substack** — enter email, password, publication URL.
3. **Settings → Email digest** — enter the address you want morning/evening digests delivered to.
4. **Settings → MCP token** (optional) — issue a personal token so you can query your own corpus from Claude Code / Claude Desktop.

The 1-hour queue starts working as soon as the user has LinkedIn connected. No additional config needed.

```bash
# Build and start all services
docker compose up -d

# Wait ~30 seconds for PostgreSQL to initialize, then run migrations
docker compose exec backend alembic -c migrations/alembic.ini upgrade head

# Seed sample data (optional — creates 3 research topics + 2 goals)
docker compose exec backend python ../scripts/seed_db.py

# Generate a secret key for the app
python -c "import secrets; print(secrets.token_hex(32))"
# → set APP_SECRET_KEY in .env

# Set your dashboard password
# DASHBOARD_PASSWORD=your_secure_password in .env

# Check health
curl http://localhost:8000/api/health
```

**Access points**:
- Dashboard: [http://localhost:3000](http://localhost:3000)
- API docs: [http://localhost:8000/api/docs](http://localhost:8000/api/docs)
- Celery tasks: visible in logs (`docker compose logs -f worker`)

### First run walkthrough
1. Open the dashboard at `http://localhost:3000`
2. Go to **Settings** → verify all API statuses show "configured"
3. Go to **Research** → click "Run Research Sweep" — this triggers the first research sweep
4. Wait ~2-3 minutes (check `docker compose logs -f worker`)
5. Refresh Research page — topics should appear ranked by relevance score
6. Click a topic → "Generate Content" to manually generate a post
7. Go to **Calendar** or **Dashboard** — the generated post will be in the 1-hour queue
8. Approve it immediately or wait for auto-publish

---

## 10. Deploying to GCP

Production target: a single Compute Engine VM running the same docker-compose stack used in dev. ~$15-20/month at `e2-small`. Terraform provisions everything; GitHub Actions handles deploys.

### Prerequisites
- GCP project with billing enabled
- `gcloud` CLI installed locally and authenticated (`gcloud auth application-default login`)
- Terraform >= 1.6
- A GitHub repo for this codebase (the Workload Identity Federation setup binds to it)

### One-time setup

```bash
# Create or select a GCP project
gcloud projects create content-engine-prod
gcloud config set project content-engine-prod

# Configure Terraform inputs
cd infra/terraform
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars:
#   - project_id, github_repo (owner/repo), git_branch
#   - allowed_ssh_cidrs, dashboard_allowed_cidrs (lock to your IP)
#   - Generate and paste all secret values listed at the bottom

# Apply
terraform init
terraform plan
terraform apply
```

### Watch the VM bootstrap

The VM startup script takes 2-3 minutes (Docker install, image pulls, compose up):

```bash
gcloud compute ssh content-engine --zone us-central1-a --tunnel-through-iap \
  -- 'sudo tail -f /var/log/startup-script.log'
```

When you see `[startup] done` at the bottom, the stack is up.

### Connect GitHub Actions

After `terraform apply`, capture the WIF outputs:

```bash
terraform output workload_identity_provider
terraform output deployer_service_account
terraform output vm_external_ip
```

In your GitHub repo settings → Secrets and variables → Actions, add:

| Secret | Value |
|---|---|
| `GCP_PROJECT_ID` | Your project ID |
| `GCP_REGION` | e.g. `us-central1` |
| `GCP_VM_NAME` | `content-engine` |
| `GCP_VM_ZONE` | Your VM zone, e.g. `us-central1-a` |
| `GCP_VM_IP` | The external IP from `terraform output` |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | The WIF provider full resource name |
| `GCP_DEPLOYER_SA` | The deployer service account email |

Push to `main` to trigger the first deploy:

```bash
git push origin main
```

Watch the workflow in GitHub Actions. It builds backend + frontend images, pushes to Artifact Registry, SSHes into the VM, pulls the new images, restarts the stack, runs migrations, and smoke-tests `/api/health`.

### Rotating secrets

The VM reads secrets fresh from Secret Manager on every boot. To rotate any credential:

```bash
echo -n "new-value" | gcloud secrets versions add anthropic-api-key --data-file=-

# Re-materialize .env on the VM and bounce the affected services
gcloud compute ssh content-engine --zone us-central1-a --tunnel-through-iap \
  -- 'sudo bash /var/lib/google/startup-script.sh'
```

### Optional: SSL with a custom domain

For HTTPS, point a domain at the static IP and run Caddy as a reverse proxy. Add a `caddy` service to `docker-compose.prod.yml` (port 80/443 → backend:8000 and frontend:3000). Open firewall ports 80/443 in `network.tf`.

### Tearing down

```bash
terraform destroy
```

This wipes the VM (including all Postgres + Qdrant data on the disk). Take backups first if needed.

---

## 11. Troubleshooting

### "LinkedIn circuit breaker open"
LinkedIn rate-limited the API. The circuit is auto-restored after 1 hour. You can reset it manually:
```bash
docker compose exec backend python -c "
import asyncio, sys; sys.path.insert(0, '.')
from database import AsyncSessionLocal
from models.settings import UserSetting
from sqlalchemy import update
async def reset():
    async with AsyncSessionLocal() as db:
        await db.execute(update(UserSetting).where(UserSetting.key == 'circuit_breaker').values(value={'linkedin_paused_until': None, 'pause_duration_minutes': 60}))
        await db.commit()
asyncio.run(reset())
"
```

### Substack automation failing
1. Check `docker compose logs -f worker` for the specific error
2. If "selector not found": Substack updated their UI — update selectors in `substack_auto.py`
3. If "login timeout": check credentials and 2FA status in your Substack account settings
4. If Playwright browser isn't installed: `docker compose exec worker playwright install chromium --with-deps`

### Database connection errors
```bash
docker compose ps   # Check postgres is running
docker compose logs db  # Check for initialization errors
docker compose restart db backend worker
```

### Celery tasks not running
```bash
docker compose ps   # Verify worker and beat are running
docker compose logs worker
docker compose logs beat
docker compose restart worker beat
```

### Migrations needed after update
```bash
docker compose exec backend alembic -c migrations/alembic.ini upgrade head
docker compose restart backend worker
```
