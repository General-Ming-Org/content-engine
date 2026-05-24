# Docker registry for backend + frontend images. CI pushes here.

resource "google_artifact_registry_repository" "containers" {
  location      = var.region
  repository_id = "content-engine"
  description   = "Content Engine container images"
  format        = "DOCKER"

  depends_on = [google_project_service.required]
}

output "artifact_registry_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.containers.repository_id}"
}
