# The single VM running the docker-compose stack.

resource "google_compute_instance" "engine" {
  name         = "content-engine"
  machine_type = var.vm_machine_type
  zone         = var.zone
  tags         = ["content-engine"]

  allow_stopping_for_update = true

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.vm_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"

    # Ephemeral external IP — A record in Cloud DNS (Terraform + boot-time sync).
    access_config {
      network_tier = "PREMIUM"
    }
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    enable-oslogin = "TRUE"
  }

  metadata_startup_script = templatefile("${path.module}/startup.sh", {
    project_id             = var.project_id
    region                 = var.region
    github_repo            = var.github_repo
    git_branch             = var.git_branch
    artifact_registry_host = "${var.region}-docker.pkg.dev"
    smtp_host              = var.smtp_host
    smtp_port              = var.smtp_port
    smtp_from_address      = var.smtp_from_address
    smtp_to_address        = var.smtp_to_address
    llm_provider           = var.llm_provider
    llm_model              = var.llm_model
    embedding_provider     = var.embedding_provider
    embedding_model        = var.embedding_model
    app_public_url         = local.public_url
    api_public_url         = local.public_url
    domain_name            = var.domain_name
    dns_managed_zone       = local.managed_zone_name
    certbot_email          = var.certbot_email
    tls_mode               = var.tls_mode
  })

  depends_on = [
    google_secret_manager_secret_version.initial,
    google_artifact_registry_repository.containers,
    google_project_iam_member.vm_secrets,
    google_project_iam_member.vm_artifact_reader,
    google_project_iam_member.vm_logging,
    google_project_iam_member.vm_monitoring,
    google_service_account_iam_member.terraform_operator_act_as_vm,
    google_dns_managed_zone_iam_member.vm_dns_editor,
  ]
}
