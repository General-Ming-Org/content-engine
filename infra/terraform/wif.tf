# Workload Identity Federation — GitHub Actions impersonates the deployer SA
# without a long-lived JSON key. This is the recommended pattern.
#
# After applying, add these GitHub Actions secrets:
#   GCP_WORKLOAD_IDENTITY_PROVIDER  → google_iam_workload_identity_pool_provider.github.name
#   GCP_DEPLOYER_SA                 → google_service_account.deployer.email

resource "google_iam_workload_identity_pool" "github" {
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "Federation pool for GitHub Actions CI/CD"

  depends_on = [google_project_service.required]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-provider"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.actor"      = "assertion.actor"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == \"${var.github_repo}\""

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_impersonate" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repo}"
}

output "workload_identity_provider" {
  description = "Set as GCP_WORKLOAD_IDENTITY_PROVIDER secret in GitHub."
  value       = google_iam_workload_identity_pool_provider.github.name
}
