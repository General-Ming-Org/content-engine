output "public_url" {
  description = "Browser-facing HTTPS URL — always use this, not the raw VM IP."
  value       = local.public_url
}

output "domain_name" {
  description = "FQDN updated in Cloud DNS on each VM boot."
  value       = var.domain_name
}

output "dns_managed_zone" {
  description = "Cloud DNS managed zone resource name."
  value       = local.managed_zone_name
}

output "app_dns_record" {
  description = "A record Terraform manages in Cloud DNS."
  value = local.dns_enabled ? {
    name  = var.domain_name
    type  = "A"
    ttl   = 60
    value = google_dns_record_set.app[0].rrdatas[0]
  } : null
}

output "dns_name_servers" {
  description = "Delegate your registrar to these NS records (once)."
  value = local.dns_enabled ? (
    var.dns_managed_zone != "" ? data.google_dns_managed_zone.existing[0].name_servers : google_dns_managed_zone.app[0].name_servers
  ) : []
}

output "ssh_hint" {
  description = "SSH into the VM via Google Cloud Console (Compute Engine → VM → SSH). Port 22 is IAP-only."
  value       = "Cloud Console → Compute Engine → content-engine (${var.zone}) → SSH"
}

output "dashboard_url" {
  description = "Dashboard URL once the stack is up (HTTPS via nginx)."
  value       = local.public_url
}

output "api_url" {
  description = "Backend API URL (HTTPS via nginx; /api routes to backend)."
  value       = "${local.public_url}/api"
}

output "knowledge_mcp_url" {
  description = "Knowledge MCP — uses ephemeral IP on :8002; resolve via dig +domain or gcloud instances describe."
  value       = "http://<ephemeral-ip>:8002 (IP changes on stop/start — use gcloud to look up)"
}

output "tls_mode" {
  description = "Active TLS mode: selfsigned (openssl) or letsencrypt (certbot)."
  value       = var.tls_mode
}

output "deployer_service_account" {
  description = "Service account email for GitHub Actions to impersonate."
  value       = google_service_account.deployer.email
}

output "workload_identity_provider" {
  description = "Set as GCP_WORKLOAD_IDENTITY_PROVIDER in GitHub Actions. Null when enable_github_wif is false."
  value       = var.enable_github_wif ? google_iam_workload_identity_pool_provider.github[0].name : null
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}
