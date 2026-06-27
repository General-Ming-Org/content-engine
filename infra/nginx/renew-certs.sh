#!/bin/sh
# Certbot renewal loop — only renews when TLS_MODE=letsencrypt on disk.
set -euo pipefail

trap exit TERM

while :; do
  if [ -f /certs/.tls-mode ] && [ "$(cat /certs/.tls-mode)" = "letsencrypt" ] && [ -f /certs/.domain ]; then
    domain="$(cat /certs/.domain)"
    certbot renew --webroot -w /var/www/certbot --quiet
    cp "/etc/letsencrypt/live/$domain/fullchain.pem" /certs/fullchain.pem
    cp "/etc/letsencrypt/live/$domain/privkey.pem" /certs/privkey.pem
    chmod 644 /certs/fullchain.pem
    chmod 600 /certs/privkey.pem
  fi
  sleep 12h & wait $!
done
