# Content Engine — GCP infrastructure root module.
#
# Provisions a single Compute Engine VM that runs the docker-compose stack.
# Secrets live in Secret Manager and are fetched at boot. Container images
# are pulled from Artifact Registry. CI/CD pushes images on every commit to
# main and SSHes into the VM for `docker compose pull && up -d`.

terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.40"
    }
  }

  # Uncomment after creating the GCS bucket — see infra/terraform/README.md
  # backend "gcs" {
  #   bucket = "content-engine-tfstate"
  #   prefix = "terraform/state"
  # }
}

provider "google" {
  project     = var.project_id
  region      = var.region
  zone        = var.zone
  credentials = file(var.google_credentials_file)
}

data "google_project" "current" {
  project_id = var.project_id
}

# Required APIs — enabled idempotently
resource "google_project_service" "required" {
  for_each = toset([
    "compute.googleapis.com",
    "secretmanager.googleapis.com",
    "artifactregistry.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "sts.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "dns.googleapis.com",
  ])

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}
