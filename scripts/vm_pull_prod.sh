#!/bin/bash
set -euo pipefail
REGISTRY_HOST="${1:-us-central1-docker.pkg.dev}"
token=$(curl -sf -H "Metadata-Flavor: Google" \
  "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token" \
  | python3 -c "import sys, json; print(json.load(sys.stdin)['access_token'])")
echo "$token" | sudo docker login -u oauth2accesstoken --password-stdin "https://${REGISTRY_HOST}"
cd /opt/content-engine
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml pull
sudo docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
