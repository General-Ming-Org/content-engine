output "vm_external_ip" {
  description = "Static IP of the Content Engine VM."
  value       = google_compute_address.static.address
}

output "ssh_command" {
  description = "Convenience: SSH into the VM via IAP."
  value       = "gcloud compute ssh content-engine --zone ${var.zone} --tunnel-through-iap"
}

output "dashboard_url" {
  description = "Dashboard URL once the stack is up."
  value       = "http://${google_compute_address.static.address}:3000"
}

output "api_url" {
  description = "Backend API URL."
  value       = "http://${google_compute_address.static.address}:8000"
}

output "knowledge_mcp_url" {
  description = "External Knowledge MCP URL — pass to Claude Code or Claude Desktop."
  value       = "http://${google_compute_address.static.address}:8002"
}

output "deployer_service_account" {
  description = "Service account email for GitHub Actions to impersonate."
  value       = google_service_account.deployer.email
}

output "artifact_registry" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}
