#!/usr/bin/env bash
# Obtain or renew a Let's Encrypt certificate via certbot (webroot).
# Prerequisites: DOMAIN_NAME + CERTBOT_EMAIL in .env, DNS A record → VM, nginx on :80.
#
# Usage (on the VM):
#   cd /opt/content-engine && ./scripts/obtain_letsencrypt.sh
set -euo pipefail

cd "$(dirname "$0")/.."

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
fi

: "${DOMAIN_NAME:?Set DOMAIN_NAME in .env}"
: "${CERTBOT_EMAIL:?Set CERTBOT_EMAIL in .env}"

COMPOSE="docker compose -f docker-compose.yml -f docker-compose.prod.yml"

echo "[certbot] requesting certificate for $DOMAIN_NAME"
$COMPOSE run --rm certbot certonly --webroot -w /var/www/certbot \
  -d "$DOMAIN_NAME" \
  --email "$CERTBOT_EMAIL" \
  --agree-tos --non-interactive --keep-until-expiring

echo "[certbot] installing certificate into nginx volume"
$COMPOSE run --rm -e TLS_MODE=letsencrypt tls-init

echo "[certbot] reloading nginx"
$COMPOSE exec nginx nginx -s reload

echo "[certbot] done — https://$DOMAIN_NAME"
