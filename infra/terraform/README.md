# Terraform — Content Engine on GCP

Provisions a single Compute Engine VM that runs the docker-compose stack, with
secrets in Secret Manager, container images in Artifact Registry, and **Cloud DNS**
for ingress (no paid static IP). Workload Identity Federation lets GitHub Actions
deploy without service account JSON keys.

Cost: roughly $15–20/month for an `e2-small` VM with a 30 GB disk. Cloud DNS is
~$0.20/mo per zone + negligible query cost. No static IP fee.

## First-time setup

### 1. GCP project (Cloud Console)

1. Create a project at [console.cloud.google.com](https://console.cloud.google.com/).
2. Enable **billing** on the project.
3. Note the **project ID**.

### 2. Terraform service account

1. **IAM & Admin → Service Accounts → Create** (`terraform-deployer`)
2. **Keys → Add key → JSON** → save as `gcp-sa.json` in the repo root (gitignored).
3. Grant roles: **Service Account Admin**, **Editor**, **Workload Identity Pool Admin** (if using WIF).
4. Set `terraform_operator_email` in `terraform.tfvars` to the key's `client_email`.

### 3. Configure variables

```bash
cp terraform.tfvars.example terraform.tfvars
```

Required:

- `domain_name` — e.g. `contentengine.generalming.com`
- `dns_zone_dns_name` — zone apex, e.g. `generalming.com` (or `dns_managed_zone` for an existing zone)

### 4. Apply

```bash
cd infra/terraform
terraform init
terraform plan
terraform apply
```

### 5. Delegate DNS (once)

```bash
terraform output dns_name_servers
```

At your domain registrar, set the **NS records** for `generalming.com` to the
Cloud DNS nameservers (or create a subdomain delegation if you prefer).

The VM updates the **A record** for `domain_name` automatically on every boot.

## After apply

Watch startup: **Compute Engine → content-engine → SSH** → `sudo tail -f /var/log/startup-script.log`

| URL | Value |
|-----|--------|
| Dashboard | `terraform output public_url` |
| API health | `<public_url>/api/health` |
| Knowledge MCP | ephemeral IP port 8002 — `gcloud compute instances describe content-engine --format='get(networkInterfaces[0].accessConfigs[0].natIP)'` |

**Never bookmark the raw VM IP** — it changes on stop/start. Always use `domain_name`.

### Stop / start behaviour

| Action | Ephemeral IP | Cloud DNS A record |
|--------|----------------|-------------------|
| Stop → Start | May change | Updated on boot via `content-engine-dns.service` |
| `terraform apply` (recreate VM) | New IP | Updated on first boot |

## GitHub Actions secrets

- `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_VM_NAME`, `GCP_VM_ZONE`
- `GCP_WORKLOAD_IDENTITY_PROVIDER`, `GCP_DEPLOYER_SA`
- **`GCP_PUBLIC_HOST`** — your `domain_name` (required)
- `GCP_TLS_TRUSTED` — `true` after Let's Encrypt is active

Deploy refreshes Cloud DNS after each release.

## Rotating secrets

1. Update `terraform.tfvars` → `terraform apply`
2. SSH in and re-run startup or `docker compose ... up -d --force-recreate`

## Tearing down

```bash
terraform destroy
```

Removes the VM and Cloud DNS zone (if Terraform created it). Delegate NS records
at your registrar when you're done.
