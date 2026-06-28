#!/bin/bash
# Authenticate Docker to Artifact Registry using the VM service account metadata token.
# OAuth tokens expire (~1h); run before every `docker compose pull` on the VM.
set -euo pipefail

REGISTRY_HOST="${1:?usage: vm_registry_login.sh REGISTRY_HOST (e.g. us-central1-docker.pkg.dev)}"

token=$(curl -sf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")

echo "$token" | docker login -u oauth2accesstoken --password-stdin "https://${REGISTRY_HOST}"
