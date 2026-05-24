# Terraform — Content Engine on GCP

Provisions a single Compute Engine VM that runs the docker-compose stack, with
secrets in Secret Manager and container images in Artifact Registry. Workload
Identity Federation is set up so GitHub Actions can deploy without service
account JSON keys.

Cost: roughly $15-20/month for an `e2-small` VM with a 30 GB disk. Secret Manager
and Artifact Registry are effectively free at this scale.

## First-time setup

```bash
# 1. Create a GCP project and set it as default
gcloud projects create content-engine-prod
gcloud config set project content-engine-prod
gcloud auth application-default login

# 2. Enable billing on the project (required for Compute Engine)
# Do this in the Cloud Console.

# 3. (Optional) Create a GCS bucket for terraform state
gsutil mb -l us-central1 gs://content-engine-tfstate
# Then uncomment the `backend "gcs"` block in main.tf and run `terraform init -migrate-state`.

# 4. Configure variables
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — at minimum set project_id, github_repo, allowed_ssh_cidrs,
# and generate the secret values listed at the bottom of the file.

# 5. Apply
terraform init
terraform plan
terraform apply
```

## After apply

The VM takes 2-3 minutes to finish its startup script. Watch progress:

```bash
gcloud compute ssh content-engine --zone us-central1-a --tunnel-through-iap \
  -- 'sudo tail -f /var/log/startup-script.log'
```

Once it's running:

- Dashboard:       `http://<vm_external_ip>:3000`
- API:             `http://<vm_external_ip>:8000`
- Knowledge MCP:   `http://<vm_external_ip>:8002`
- Health:          `http://<vm_external_ip>:8000/api/health`

## Rotating secrets

```bash
echo -n "new-value" | gcloud secrets versions add anthropic-api-key --data-file=-

# Then re-bootstrap the VM env file:
gcloud compute ssh content-engine --zone us-central1-a --tunnel-through-iap \
  -- 'sudo bash /var/lib/google/startup-script.sh && cd /opt/content-engine && docker compose up -d --force-recreate'
```

## GitHub Actions setup

After `terraform apply`, capture the outputs:

```bash
terraform output workload_identity_provider
terraform output deployer_service_account
```

Add them to GitHub Actions secrets:

- `GCP_PROJECT_ID` — your project ID
- `GCP_WORKLOAD_IDENTITY_PROVIDER` — the WIF provider output
- `GCP_DEPLOYER_SA` — the deployer service account email
- `GCP_REGION` — e.g. `us-central1`
- `GCP_VM_NAME` — `content-engine`
- `GCP_VM_ZONE` — your VM zone

The deploy workflow uses these to push images and SSH in.

## Tearing down

```bash
terraform destroy
```

Note: this wipes the VM. Postgres + Qdrant data on the VM disk goes with it.
Take backups first if there's anything important. See the "Backups" section in
the main SETUP.md.
