# Default VPC is fine — we only need firewall rules.

resource "google_compute_firewall" "ssh" {
  name    = "content-engine-allow-ssh"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = var.allowed_ssh_cidrs
  target_tags   = ["content-engine"]
}

resource "google_compute_firewall" "dashboard" {
  name    = "content-engine-allow-dashboard"
  network = "default"

  allow {
    protocol = "tcp"
    # 3000: frontend, 8000: backend API, 8002: knowledge MCP (external clients)
    ports = ["80", "443", "3000", "8000", "8002"]
  }

  source_ranges = var.dashboard_allowed_cidrs
  target_tags   = ["content-engine"]
}

resource "google_compute_address" "static" {
  name   = "content-engine-static-ip"
  region = var.region
}
