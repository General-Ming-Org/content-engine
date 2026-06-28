#!/bin/bash
set -euo pipefail
cd /opt/content-engine

if [ ! -f .env ]; then
  echo "missing .env — re-run startup script or terraform apply" >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
source .env
set +a

REGISTRY="${ARTIFACT_REGISTRY_URL:-us-central1-docker.pkg.dev/portfolio-424503/content-engine}"
REGISTRY_HOST="${REGISTRY%%/*}"

echo "[repair] authenticating to Artifact Registry..."
bash scripts/vm_registry_login.sh "$REGISTRY_HOST"

echo "[repair] building backend + frontend locally..."
docker compose -f docker-compose.yml -f docker-compose.bootstrap.yml build backend frontend

echo "[repair] tagging for prod compose..."
docker tag content-engine-backend "${REGISTRY}/backend:latest"
docker tag content-engine-frontend "${REGISTRY}/frontend:latest"

echo "[repair] starting production stack..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build tls-init
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d

echo "[repair] migrations..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml exec -T backend alembic -c migrations/alembic.ini upgrade head || true

echo "[repair] dns sync..."
if [ -f scripts/update_cloud_dns.py ] && [ -n "${DNS_MANAGED_ZONE:-}" ]; then
  python3 scripts/update_cloud_dns.py || true
fi

docker compose -f docker-compose.yml -f docker-compose.prod.yml ps
