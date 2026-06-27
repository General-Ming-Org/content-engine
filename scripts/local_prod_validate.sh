#!/usr/bin/env bash
# Validate production stack locally before touching GCP.
# Usage: ./scripts/local_prod_validate.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export ARTIFACT_REGISTRY_URL="${ARTIFACT_REGISTRY_URL:-us-central1-docker.pkg.dev/example-project/content-engine}"

echo "[validate] docker compose overlays..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml config -q
docker compose -f docker-compose.yml -f docker-compose.bootstrap.yml config -q

echo "[validate] frontend production image..."
docker build -t content-engine-frontend:test ./frontend

echo "[validate] nginx config syntax..."
docker run --rm -v "$ROOT/infra/nginx/nginx.conf:/etc/nginx/conf.d/default.conf:ro" nginx:1.27-alpine nginx -t

echo "[validate] all local production checks passed"
