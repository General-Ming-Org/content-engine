#!/bin/bash
# VM bootstrap. Runs on first boot and on every reboot (idempotent).
#
# Responsibilities:
#   1. Install Docker + Docker Compose
#   2. Authenticate to Artifact Registry
#   3. Clone the repo (or pull latest)
#   4. Materialize .env from Secret Manager
#   5. `docker compose up -d`
#
# CI/CD does NOT use this script — it just SSHes in and runs `docker compose pull && up -d`.
# This script handles cold-boot only.

set -euo pipefail
exec > >(tee -a /var/log/startup-script.log) 2>&1
echo "[startup] $(date) — beginning bootstrap"

PROJECT_ID="${project_id}"
REGION="${region}"
REPO="${github_repo}"
BRANCH="${git_branch}"
REGISTRY_HOST="${artifact_registry_host}"

# ── Install Docker ────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null; then
  echo "[startup] installing docker"
  apt-get update -y
  apt-get install -y ca-certificates curl gnupg git
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  chmod a+r /etc/apt/keyrings/docker.gpg
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -y
  apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
  systemctl enable --now docker
fi

# ── Authenticate Docker to Artifact Registry ──────────────────────────────────
gcloud auth configure-docker "$REGISTRY_HOST" --quiet

# ── Clone or update the repo ──────────────────────────────────────────────────
APP_DIR=/opt/content-engine
if [ ! -d "$APP_DIR" ]; then
  git clone --branch "$BRANCH" "https://github.com/$${REPO}.git" "$APP_DIR"
else
  git -C "$APP_DIR" fetch --depth=1 origin "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
fi

# ── Materialize .env from Secret Manager ──────────────────────────────────────
fetch_secret() {
  local secret_name="$1"
  gcloud secrets versions access latest --secret="$secret_name" 2>/dev/null || echo ""
}

ENV_FILE="$APP_DIR/.env"
cat > "$ENV_FILE" <<EOF
APP_ENV=production
APP_SECRET_KEY=$(fetch_secret app-secret-key)
DASHBOARD_PASSWORD=$(fetch_secret dashboard-password)
POSTGRES_USER=content_engine
POSTGRES_PASSWORD=$(fetch_secret postgres-password)
POSTGRES_DB=content_engine
DATABASE_URL=postgresql://content_engine:$(fetch_secret postgres-password)@db:5432/content_engine
REDIS_URL=redis://redis:6379/0
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=$(fetch_secret qdrant-api-key)
ANTHROPIC_API_KEY=$(fetch_secret anthropic-api-key)
VOYAGE_API_KEY=$(fetch_secret voyage-api-key)
OPENAI_API_KEY=$(fetch_secret openai-api-key)
COHERE_API_KEY=$(fetch_secret cohere-api-key)
TAVILY_API_KEY=$(fetch_secret tavily-api-key)
SERPER_API_KEY=$(fetch_secret serper-api-key)
LINKEDIN_CLIENT_ID=$(fetch_secret linkedin-client-id)
LINKEDIN_CLIENT_SECRET=$(fetch_secret linkedin-client-secret)
LINKEDIN_ACCESS_TOKEN=$(fetch_secret linkedin-access-token)
LINKEDIN_REFRESH_TOKEN=$(fetch_secret linkedin-refresh-token)
LINKEDIN_PERSON_URN=$(fetch_secret linkedin-person-urn)
SUBSTACK_EMAIL=$(fetch_secret substack-email)
SUBSTACK_PASSWORD=$(fetch_secret substack-password)
SMTP_HOST=${smtp_host:-smtp.gmail.com}
SMTP_PORT=${smtp_port:-587}
SMTP_USERNAME=$(fetch_secret smtp-username)
SMTP_PASSWORD=$(fetch_secret smtp-password)
SMTP_FROM_ADDRESS=${smtp_from_address:-}
SMTP_TO_ADDRESS=${smtp_to_address:-}
MCP_KNOWLEDGE_TOKEN=$(fetch_secret mcp-knowledge-token)
ARTIFACT_REGISTRY_URL=$REGISTRY_HOST/$PROJECT_ID/content-engine
EOF
chmod 600 "$ENV_FILE"

# ── Start the stack ───────────────────────────────────────────────────────────
cd "$APP_DIR"
docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
docker compose exec -T backend alembic -c migrations/alembic.ini upgrade head || true

echo "[startup] $(date) — done"
