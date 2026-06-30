#!/usr/bin/env bash
# Install or refresh the Google Cloud Ops Agent on the Content Engine VM.
# Run as root on the VM: sudo bash scripts/install_ops_agent.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG_SRC="$ROOT/infra/ops-agent/config.yaml"
CONFIG_DST="/etc/google-cloud-ops-agent/config.yaml"

if [[ "${EUID:-$(id -u)}" -ne 0 ]]; then
  echo "Run as root: sudo bash $0" >&2
  exit 1
fi

if [[ ! -f "$CONFIG_SRC" ]]; then
  echo "Missing config: $CONFIG_SRC" >&2
  exit 1
fi

if ! command -v curl >/dev/null; then
  apt-get update -y
  apt-get install -y curl
fi

if ! dpkg -s google-cloud-ops-agent >/dev/null 2>&1; then
  echo "[ops-agent] installing Google Cloud Ops Agent"
  curl -sSO https://dl.google.com/cloudagents/add-google-cloud-ops-agent-repo.sh
  bash add-google-cloud-ops-agent-repo.sh --also-install
  rm -f add-google-cloud-ops-agent-repo.sh
fi

echo "[ops-agent] installing config → $CONFIG_DST"
install -m 0644 "$CONFIG_SRC" "$CONFIG_DST"
systemctl enable --now google-cloud-ops-agent
systemctl restart google-cloud-ops-agent
systemctl --no-pager --full status google-cloud-ops-agent || true

echo "[ops-agent] done — view logs in Cloud Logging and metrics in Cloud Monitoring"
