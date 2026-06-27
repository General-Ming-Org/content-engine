#!/bin/sh
# Materialize TLS certificates for nginx.
#
# TLS_MODE=selfsigned (default): openssl self-signed cert — browsers show a warning.
# TLS_MODE=letsencrypt: certbot webroot (requires DOMAIN_NAME, CERTBOT_EMAIL, DNS → VM).
#
# Certbot does not issue self-signed certs; use selfsigned mode for IP-only deployments.
set -euo pipefail

CERT_DIR=/certs
LE_DIR=/etc/letsencrypt/live
WEBROOT=/var/www/certbot

mkdir -p "$CERT_DIR" "$WEBROOT"

issue_self_signed() {
  cn="$1"
  echo "[tls] issuing self-signed certificate (CN=$cn)"
  openssl req -x509 -nodes -days 825 -newkey rsa:2048 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out "$CERT_DIR/fullchain.pem" \
    -subj "/CN=${cn}/O=Content Engine/C=US"
  echo selfsigned >"$CERT_DIR/.tls-mode"
}

install_le_certs() {
  domain="$1"
  src="$LE_DIR/$domain"
  if [ ! -f "$src/fullchain.pem" ]; then
    echo "[tls] expected Let's Encrypt files missing under $src" >&2
    exit 1
  fi
  cp "$src/fullchain.pem" "$CERT_DIR/fullchain.pem"
  cp "$src/privkey.pem" "$CERT_DIR/privkey.pem"
  echo letsencrypt >"$CERT_DIR/.tls-mode"
  echo "$domain" >"$CERT_DIR/.domain"
}

mode="${TLS_MODE:-selfsigned}"
domain="${DOMAIN_NAME:-}"
email="${CERTBOT_EMAIL:-}"

if [ "$mode" = "letsencrypt" ]; then
  if [ -z "$domain" ] || [ -z "$email" ]; then
    echo "[tls] letsencrypt mode requires DOMAIN_NAME and CERTBOT_EMAIL" >&2
    exit 1
  fi
  if [ -f "$LE_DIR/$domain/fullchain.pem" ]; then
    echo "[tls] reusing existing Let's Encrypt certificate for $domain"
    install_le_certs "$domain"
  else
    echo "[tls] no Let's Encrypt cert yet — issuing self-signed bootstrap certificate"
    echo "[tls] once nginx is up and DNS points here, run: ./scripts/obtain_letsencrypt.sh"
    issue_self_signed "$domain"
  fi
else
  if [ -f "$CERT_DIR/fullchain.pem" ] && [ -f "$CERT_DIR/privkey.pem" ]; then
    echo "[tls] existing certificate found in $CERT_DIR, skipping"
  else
    cn="${domain:-${VM_IP:-content-engine}}"
    issue_self_signed "$cn"
  fi
fi

chmod 644 "$CERT_DIR/fullchain.pem"
chmod 600 "$CERT_DIR/privkey.pem"
echo "[tls] certificate ready ($(cat "$CERT_DIR/.tls-mode"))"
