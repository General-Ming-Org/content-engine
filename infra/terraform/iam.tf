# Service account the VM runs as. Has read access to Secret Manager and
# Artifact Registry — nothing else.

resource "google_service_account" "vm" {
  account_id   = "content-engine-vm"
  display_name = "Content Engine VM"

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "vm_secrets" {
  project = var.project_id
  role    = "roles/secretmanager.secretAccessor"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_artifact_reader" {
  project = var.project_id
  role    = "roles/artifactregistry.reader"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

# Terraform operator must be able to attach the VM SA when creating the instance.
resource "google_service_account_iam_member" "terraform_operator_act_as_vm" {
  service_account_id = google_service_account.vm.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${var.terraform_operator_email}"
}

# Separate service account for CI/CD. Used by GitHub Actions via Workload Identity Federation.
resource "google_service_account" "deployer" {
  account_id   = "content-engine-deployer"
  display_name = "Content Engine CI/CD Deployer"

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "deployer_artifact_writer" {
  project = var.project_id
  role    = "roles/artifactregistry.writer"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_project_iam_member" "deployer_compute_admin" {
  project = var.project_id
  role    = "roles/compute.instanceAdmin.v1"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_project_iam_member" "deployer_iap" {
  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_project_iam_member" "terraform_operator_iap" {
  project = var.project_id
  role    = "roles/iap.tunnelResourceAccessor"
  member  = "serviceAccount:${var.terraform_operator_email}"
}

resource "google_project_iam_member" "deployer_os_login" {
  project = var.project_id
  role    = "roles/compute.osAdminLogin"
  member  = "serviceAccount:${google_service_account.deployer.email}"
}

resource "google_project_iam_member" "terraform_operator_os_login" {
  project = var.project_id
  role    = "roles/compute.osAdminLogin"
  member  = "serviceAccount:${var.terraform_operator_email}"
}

resource "google_project_iam_member" "terraform_operator_dns" {
  project = var.project_id
  role    = "roles/dns.admin"
  member  = "serviceAccount:${var.terraform_operator_email}"
}

resource "google_service_account_iam_member" "deployer_act_as_vm" {
  service_account_id = google_service_account.vm.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deployer.email}"
}
