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

# ── Authenticate Docker to Artifact Registry (metadata token — no gcloud SDK) ─
metadata_access_token() {
  curl -sf -H "Metadata-Flavor: Google" \
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
    | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])"
}

configure_docker_registry() {
  local token
  token=$(metadata_access_token)
  echo "$token" | docker login -u oauth2accesstoken --password-stdin "https://$REGISTRY_HOST"
}

configure_docker_registry

# ── Clone or update the repo ──────────────────────────────────────────────────
APP_DIR=/opt/content-engine
if [ ! -d "$APP_DIR" ]; then
  git clone --branch "$BRANCH" "https://github.com/$${REPO}.git" "$APP_DIR"
else
  git -C "$APP_DIR" fetch --depth=1 origin "$BRANCH"
  git -C "$APP_DIR" reset --hard "origin/$BRANCH"
fi

# ── Materialize .env from Secret Manager (REST API + metadata token) ──────────
fetch_secret() {
  local secret_name="$1"
  local token response
  token=$(metadata_access_token 2>/dev/null) || { echo ""; return; }
  response=$(curl -sf -H "Authorization: Bearer $token" \
    "https://secretmanager.googleapis.com/v1/projects/$PROJECT_ID/secrets/$secret_name/versions/latest:access" \
    2>/dev/null) || { echo ""; return; }
  python3 -c "import sys, json, base64; print(base64.b64decode(json.load(sys.stdin)['payload']['data']).decode(), end='')" <<< "$response"
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
LLM_PROVIDER=${llm_provider}
LLM_MODEL=${llm_model}
EMBEDDING_PROVIDER=${embedding_provider}
EMBEDDING_MODEL=${embedding_model}
VOYAGE_API_KEY=$(fetch_secret voyage-api-key)
OPENAI_API_KEY=$(fetch_secret openai-api-key)
COHERE_API_KEY=$(fetch_secret cohere-api-key)
TAVILY_API_KEY=$(fetch_secret tavily-api-key)
SERPER_API_KEY=$(fetch_secret serper-api-key)
SUBSTACK_EMAIL=$(fetch_secret substack-email)
SUBSTACK_PASSWORD=$(fetch_secret substack-password)
SMTP_HOST=${smtp_host}
SMTP_PORT=${smtp_port}
SMTP_USERNAME=$(fetch_secret smtp-username)
SMTP_PASSWORD=$(fetch_secret smtp-password)
SMTP_FROM_ADDRESS=${smtp_from_address}
SMTP_TO_ADDRESS=${smtp_to_address}
APP_PUBLIC_URL=${app_public_url}
API_PUBLIC_URL=${api_public_url}
DOMAIN_NAME=${domain_name}
DNS_MANAGED_ZONE=${dns_managed_zone}
CERTBOT_EMAIL=${certbot_email}
TLS_MODE=${tls_mode}
GCP_PROJECT_ID=$PROJECT_ID
MCP_KNOWLEDGE_TOKEN=$(fetch_secret mcp-knowledge-token)
ARTIFACT_REGISTRY_URL=$REGISTRY_HOST/$PROJECT_ID/content-engine
EOF
chmod 600 "$ENV_FILE"

# ── Ephemeral IP + Cloud DNS ───────────────────────────────────────────────────
EXTERNAL_IP=$(curl -sf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip")
echo "[startup] ephemeral external IP: $EXTERNAL_IP"
if grep -q '^VM_IP=' "$ENV_FILE"; then
  sed -i "s/^VM_IP=.*/VM_IP=$EXTERNAL_IP/" "$ENV_FILE"
else
  echo "VM_IP=$EXTERNAL_IP" >> "$ENV_FILE"
fi

if [ -n "${dns_managed_zone}" ] && [ -n "${domain_name}" ]; then
  echo "[startup] updating Cloud DNS A record"
  DNS_MANAGED_ZONE="${dns_managed_zone}" \
  DOMAIN_NAME="${domain_name}" \
  GCP_PROJECT_ID="$PROJECT_ID" \
  EXTERNAL_IP="$EXTERNAL_IP" \
  python3 "$APP_DIR/scripts/update_cloud_dns.py" || echo "[startup] cloud dns update failed — continuing"
fi

# Re-run DNS update on every boot (startup script only runs on first boot / metadata change).
cp "$APP_DIR/infra/terraform/systemd/content-engine-dns.service" /etc/systemd/system/content-engine-dns.service
systemctl daemon-reload
systemctl enable content-engine-dns.service
systemctl start content-engine-dns.service || true

# ── Start the stack ───────────────────────────────────────────────────────────
cd "$APP_DIR"
COMPOSE_FILES="-f docker-compose.yml"
if docker compose -f docker-compose.yml -f docker-compose.prod.yml pull 2>/dev/null; then
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.prod.yml"
else
  echo "[startup] registry images not found — building locally with bootstrap overlay"
  COMPOSE_FILES="$COMPOSE_FILES -f docker-compose.bootstrap.yml"
  docker compose $COMPOSE_FILES build
fi
docker compose $COMPOSE_FILES up -d
docker compose $COMPOSE_FILES exec -T backend alembic -c migrations/alembic.ini upgrade head || true

echo "[startup] $(date) — done"
