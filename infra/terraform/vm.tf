# The single VM running the docker-compose stack.

resource "google_compute_instance" "engine" {
  name         = "content-engine"
  machine_type = var.vm_machine_type
  zone         = var.zone
  tags         = ["content-engine"]

  boot_disk {
    initialize_params {
      image = "debian-cloud/debian-12"
      size  = var.vm_disk_size_gb
      type  = "pd-balanced"
    }
  }

  network_interface {
    network = "default"

    access_config {
      nat_ip = google_compute_address.static.address
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
    project_id              = var.project_id
    region                  = var.region
    github_repo             = var.github_repo
    git_branch              = var.git_branch
    artifact_registry_host  = "${var.region}-docker.pkg.dev"
  })

  # Make sure secrets and registry are in place before the VM tries to pull
  depends_on = [
    google_secret_manager_secret_version.initial,
    google_artifact_registry_repository.containers,
    google_project_iam_member.vm_secrets,
    google_project_iam_member.vm_artifact_reader,
  ]

  # Don't re-create the VM when the startup script changes — re-run it via SSH instead.
  lifecycle {
    ignore_changes = [metadata_startup_script]
  }
}
