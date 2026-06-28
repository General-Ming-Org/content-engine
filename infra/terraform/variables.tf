variable "project_id" {
  description = "GCP project ID."
  type        = string
}

variable "google_credentials_file" {
  description = "Path to a GCP service account JSON key file (relative to infra/terraform/ or absolute)."
  type        = string
  sensitive   = true
}

variable "terraform_operator_email" {
  description = "Email of the service account in google_credentials_file (client_email from the JSON). Granted actAs on the VM SA."
  type        = string
}

variable "enable_github_wif" {
  description = "Create Workload Identity Federation for GitHub Actions. Requires iam.workloadIdentityPools.create on the operator SA."
  type        = bool
  default     = false
}

variable "region" {
  description = "GCP region — used for Artifact Registry and managed resources."
  type        = string
  default     = "us-central1"
}

variable "zone" {
  description = "GCP zone for the VM. Pick something in your region."
  type        = string
  default     = "us-central1-a"
}

variable "vm_machine_type" {
  description = "Compute Engine machine type. Use e2-standard-2 (8 GB) when the VM builds Docker images locally; e2-medium (4 GB) is enough if CI pushes pre-built images."
  type        = string
  default     = "e2-standard-2"
}

variable "vm_disk_size_gb" {
  description = "Root disk size. 30GB headroom for Postgres + Qdrant + image cache."
  type        = number
  default     = 30
}

variable "github_repo" {
  description = "GitHub repo to clone on the VM (owner/repo)."
  type        = string
}

variable "git_branch" {
  description = "Branch to deploy from."
  type        = string
  default     = "main"
}

variable "allowed_ingress_ports" {
  description = "TCP ports open to the internet (0.0.0.0/0). All other ingress is denied. SSH uses IAP, not this list."
  type        = list(string)
  default     = ["80", "443", "3000", "8000", "8002"]
}

variable "domain_name" {
  description = "FQDN for the app (e.g. contentengine.example.com). Cloud DNS A record is updated on each VM boot."
  type        = string
}

variable "dns_zone_dns_name" {
  description = "Cloud DNS zone apex (e.g. generalming.com). domain_name must be a record in this zone. Ignored when dns_managed_zone is set."
  type        = string
  default     = ""
}

variable "dns_managed_zone" {
  description = "Use an existing Cloud DNS managed zone by GCP resource name. If empty, creates content-engine-dns from dns_zone_dns_name."
  type        = string
  default     = ""
}

variable "certbot_email" {
  description = "Email for Let's Encrypt / certbot expiry notices. Required when tls_mode=letsencrypt."
  type        = string
  default     = ""
}

variable "tls_mode" {
  description = "TLS certificate source: selfsigned (openssl, default) or letsencrypt (certbot; needs domain_name + DNS)."
  type        = string
  default     = "selfsigned"

  validation {
    condition     = contains(["selfsigned", "letsencrypt"], var.tls_mode)
    error_message = "tls_mode must be selfsigned or letsencrypt."
  }
}

# ── Secrets — set in terraform.tfvars, applied via `terraform apply` ───────────

variable "anthropic_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "voyage_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "openai_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "cohere_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "tavily_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "serper_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "substack_email" {
  type      = string
  sensitive = true
  default   = ""
}

variable "substack_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "smtp_host" {
  type    = string
  default = "smtp.gmail.com"
}

variable "smtp_port" {
  type    = number
  default = 587
}

variable "smtp_username" {
  type      = string
  sensitive = true
  default   = ""
}

variable "smtp_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "smtp_from_address" {
  type    = string
  default = ""
}

variable "smtp_to_address" {
  type    = string
  default = ""
}

variable "qdrant_api_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "mcp_knowledge_token" {
  type      = string
  sensitive = true
  default   = ""
}

variable "dashboard_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "app_secret_key" {
  type      = string
  sensitive = true
  default   = ""
}

variable "postgres_password" {
  type      = string
  sensitive = true
  default   = ""
}

variable "llm_provider" {
  description = "LiteLLM provider for all LLM calls (e.g. openai, anthropic)."
  type        = string
  default     = "openai"
}

variable "llm_model" {
  description = "Model ID for the configured LLM provider (e.g. gpt-4o-mini)."
  type        = string
  default     = "gpt-4o-mini"
}

variable "embedding_provider" {
  description = "Embedding provider (voyage, openai, or cohere)."
  type        = string
  default     = "openai"
}

variable "embedding_model" {
  description = "Embedding model ID for the configured provider."
  type        = string
  default     = "text-embedding-3-small"
}
