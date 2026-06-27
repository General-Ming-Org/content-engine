# Workload Identity Federation — GitHub Actions impersonates the deployer SA
# without a long-lived JSON key. Set enable_github_wif = true once the operator
# SA has roles/iam.workloadIdentityPoolAdmin (or Editor + that role).
#
# After applying, add these GitHub Actions secrets:
#   GCP_WORKLOAD_IDENTITY_PROVIDER  → workload_identity_provider output
#   GCP_DEPLOYER_SA                 → deployer_service_account output

resource "google_iam_workload_identity_pool" "github" {
  count = var.enable_github_wif ? 1 : 0

  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"
  description               = "Federation pool for GitHub Actions CI/CD"

  depends_on = [
    google_project_service.required,
    google_service_account.deployer,
  ]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  count = var.enable_github_wif ? 1 : 0

  workload_identity_pool_id          = google_iam_workload_identity_pool.github[0].workload_identity_pool_id
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
  count = var.enable_github_wif ? 1 : 0

  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github[0].name}/attribute.repository/${var.github_repo}"
}
