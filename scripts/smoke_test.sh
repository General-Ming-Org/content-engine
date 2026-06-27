#!/usr/bin/env bash
# Post-deployment smoke tests. Used by deploy.yml and runnable manually:
#   SMOKE_INSECURE=1 ./scripts/smoke_test.sh https://35.232.183.81 https://35.232.183.81
set -euo pipefail

API_URL="${1:-http://localhost:8000}"
FRONTEND_URL="${2:-http://localhost:3000}"
MCP_URL="${3:-http://localhost:8002}"
MAX_ATTEMPTS="${SMOKE_MAX_ATTEMPTS:-30}"
SLEEP_SECS="${SMOKE_SLEEP_SECS:-5}"

CURL_OPTS=(--connect-timeout 5 --max-time 15)
if [ "${SMOKE_INSECURE:-}" = "1" ]; then
  CURL_OPTS+=(-k)
fi

log() { echo "[smoke] $*"; }

wait_for_http() {
  local name="$1" url="$2" accept_codes="${3:-200}"
  local attempt=1
  while [ "$attempt" -le "$MAX_ATTEMPTS" ]; do
    local code
    code=$(curl -sS "${CURL_OPTS[@]}" -o /dev/null -w "%{http_code}" "$url" || echo "000")
    if echo "$accept_codes" | grep -qw "$code"; then
      log "$name reachable ($url → HTTP $code)"
      return 0
    fi
    log "$name attempt $attempt/$MAX_ATTEMPTS failed (HTTP $code), retrying in ${SLEEP_SECS}s..."
    sleep "$SLEEP_SECS"
    attempt=$((attempt + 1))
  done
  log "$name never became reachable at $url"
  return 1
}

check_api_health() {
  local body
  body=$(curl -fsS "${CURL_OPTS[@]}" "${API_URL}/api/health")
  python3 -c "
import json, sys
data = json.loads(sys.stdin.read())
assert 'status' in data, 'missing top-level status'
assert 'services' in data, 'missing services'
for svc in ('postgres', 'redis'):
    assert svc in data['services'], f'missing {svc} in health'
    assert 'status' in data['services'][svc], f'missing {svc}.status'
if data['services']['postgres']['status'] != 'ok':
    raise SystemExit(f\"postgres not ok: {data['services']['postgres']}\")
if data['services']['redis']['status'] != 'ok':
    raise SystemExit(f\"redis not ok: {data['services']['redis']}\")
print(f\"health ok (overall={data['status']})\")
" <<< "$body"
}

check_frontend() {
  local body
  body=$(curl -fsS "${CURL_OPTS[@]}" "$FRONTEND_URL/")
  if ! echo "$body" | grep -qi '<html'; then
    echo "frontend response missing <html>"
    return 1
  fi
  log "frontend serves HTML"
}

check_mcp() {
  local code
  code=$(curl -sS "${CURL_OPTS[@]}" -o /dev/null -w "%{http_code}" "$MCP_URL/" || echo "000")
  if [ "$code" = "000" ]; then
    log "knowledge MCP not reachable at $MCP_URL (non-fatal)"
    return 0
  fi
  log "knowledge MCP port open ($MCP_URL → HTTP $code)"
}

log "API=$API_URL FRONTEND=$FRONTEND_URL MCP=$MCP_URL"
wait_for_http "API" "${API_URL}/api/health"
check_api_health
wait_for_http "frontend" "$FRONTEND_URL/" "200 304"
check_frontend
check_mcp
log "all smoke checks passed"
