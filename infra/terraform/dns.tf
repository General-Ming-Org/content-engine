# Cloud DNS — Terraform owns the A record; the VM re-syncs it on boot when the
# ephemeral external IP changes without a terraform apply.

check "dns_zone_configured" {
  assert {
    condition     = var.dns_managed_zone != "" || var.dns_zone_dns_name != ""
    error_message = "Set dns_managed_zone (existing zone) or dns_zone_dns_name (create new zone)."
  }
}

locals {
  dns_zone_fqdn = var.dns_zone_dns_name != "" ? "${trim(var.dns_zone_dns_name, ".")}." : ""

  managed_zone_name = var.dns_managed_zone != "" ? var.dns_managed_zone : (
    length(google_dns_managed_zone.app) > 0 ? google_dns_managed_zone.app[0].name : ""
  )

  dns_enabled = var.domain_name != "" && local.managed_zone_name != ""
}

resource "google_dns_managed_zone" "app" {
  count = var.dns_managed_zone == "" && var.dns_zone_dns_name != "" ? 1 : 0

  name          = "content-engine-dns"
  dns_name      = local.dns_zone_fqdn
  description   = "Content Engine — A record managed by Terraform + VM boot sync."
  force_destroy = true

  depends_on = [
    google_project_service.required,
    google_project_iam_member.terraform_operator_dns,
  ]
}

data "google_dns_managed_zone" "existing" {
  count = var.dns_managed_zone != "" ? 1 : 0
  name  = var.dns_managed_zone
}

resource "google_dns_record_set" "app" {
  count = local.dns_enabled ? 1 : 0

  managed_zone = local.managed_zone_name
  name         = "${trim(var.domain_name, ".")}."
  type         = "A"
  ttl          = 60
  rrdatas      = [google_compute_instance.engine.network_interface[0].access_config[0].nat_ip]

  depends_on = [google_compute_instance.engine]
}

resource "google_dns_managed_zone_iam_member" "vm_dns_editor" {
  count = local.dns_enabled ? 1 : 0

  project      = var.project_id
  managed_zone = local.managed_zone_name
  role         = "roles/dns.admin"
  member       = "serviceAccount:${google_service_account.vm.email}"

  depends_on = [
    google_project_iam_member.terraform_operator_dns,
  ]
}
