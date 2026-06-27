#!/usr/bin/env python3
"""Upsert a Cloud DNS A record to the VM's current ephemeral external IP.

Reads configuration from environment:
  GCP_PROJECT_ID / PROJECT_ID
  DNS_MANAGED_ZONE
  DOMAIN_NAME
  EXTERNAL_IP (optional — fetched from GCE metadata when unset)
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

METADATA_IP_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/network-interfaces/0/access-configs/0/external-ip"
)
METADATA_TOKEN_URL = (
    "http://metadata.google.internal/computeMetadata/v1/"
    "instance/service-accounts/default/token"
)
DNS_API = "https://dns.googleapis.com/dns/v1/projects/{project}/managedZones/{zone}/changes"
DNS_TTL = 60


def _metadata_get(url: str) -> str:
    req = urllib.request.Request(url, headers={"Metadata-Flavor": "Google"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        return resp.read().decode().strip()


def _access_token() -> str:
    raw = _metadata_get(METADATA_TOKEN_URL)
    return json.loads(raw)["access_token"]


def _external_ip() -> str:
    env_ip = os.environ.get("EXTERNAL_IP", "").strip()
    if env_ip:
        return env_ip
    return _metadata_get(METADATA_IP_URL)


def _fqdn(name: str) -> str:
    name = name.strip().rstrip(".")
    return f"{name}."


def _api_request(
    method: str,
    url: str,
    token: str,
    body: dict | None = None,
) -> dict:
    data = None if body is None else json.dumps(body).encode()
    headers = {"Authorization": f"Bearer {token}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode())


def _list_record(project: str, zone: str, fqdn: str, token: str) -> dict | None:
    url = (
        f"https://dns.googleapis.com/dns/v1/projects/{project}/managedZones/{zone}"
        f"/rrsets/{urllib.parse.quote(fqdn, safe='')}/A"
    )
    try:
        return _api_request("GET", url, token)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def upsert_a_record(project: str, zone: str, domain: str, ip: str) -> None:
    token = _access_token()
    fqdn = _fqdn(domain)
    new_rrset = {
        "kind": "dns#resourceRecordSet",
        "name": fqdn,
        "type": "A",
        "ttl": DNS_TTL,
        "rrdatas": [ip],
    }

    existing = _list_record(project, zone, fqdn, token)
    if existing and existing.get("rrdatas") == [ip]:
        print(f"[dns] {fqdn} already points to {ip}")
        return

    change: dict = {"additions": [new_rrset]}
    if existing:
        change["deletions"] = [existing]

    url = DNS_API.format(project=project, zone=zone)
    result = _api_request("POST", url, token, change)
    print(f"[dns] updated {fqdn} → {ip} (change id={result.get('id')})")


def main() -> int:
    project = os.environ.get("GCP_PROJECT_ID") or os.environ.get("PROJECT_ID", "")
    zone = os.environ.get("DNS_MANAGED_ZONE", "")
    domain = os.environ.get("DOMAIN_NAME", "")

    if not project or not zone or not domain:
        print("[dns] skip: GCP_PROJECT_ID, DNS_MANAGED_ZONE, and DOMAIN_NAME are required", file=sys.stderr)
        return 1

    ip = _external_ip()
    if not ip:
        print("[dns] could not resolve external IP", file=sys.stderr)
        return 1

    upsert_a_record(project, zone, domain, ip)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
