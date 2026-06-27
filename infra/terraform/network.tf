# Default VPC is fine — we only need firewall rules.
# Ingress is allow-list only: ports in allowed_ingress_ports are open to the
# internet; everything else (including public SSH) is denied by default.
# The VM uses an ephemeral external IP — reach it via Cloud DNS (domain_name).

resource "google_compute_firewall" "app" {
  name    = "content-engine-allow-app"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = var.allowed_ingress_ports
  }

  source_ranges = ["0.0.0.0/0"]
  target_tags   = ["content-engine"]
}

# SSH is not exposed publicly. Admin + CI access via IAP tunnel only.
resource "google_compute_firewall" "ssh_iap" {
  name    = "content-engine-allow-ssh-iap"
  network = "default"

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }

  source_ranges = ["35.235.240.0/20"]
  target_tags   = ["content-engine"]
}
