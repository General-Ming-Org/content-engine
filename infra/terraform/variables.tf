variable "project_id" {
  description = "GCP project ID."
  type        = string
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
  description = "Compute Engine machine type. e2-small (~$15/mo) handles the stack comfortably."
  type        = string
  default     = "e2-small"
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

variable "allowed_ssh_cidrs" {
  description = "CIDRs allowed to SSH into the VM. Lock to your IP."
  type        = list(string)
  default     = ["0.0.0.0/0"]  # OVERRIDE in tfvars
}

variable "dashboard_allowed_cidrs" {
  description = "CIDRs allowed to hit the dashboard (port 3000 / 8000 / 8002)."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "domain_name" {
  description = "Optional custom domain. Leave empty to use the VM's external IP only."
  type        = string
  default     = ""
}

# ── Secrets — initial values for Secret Manager ───────────────────────────────
# In CI/CD you'll typically pass empty strings here and write values via gcloud
# secrets versions add. The initial seed is here so terraform apply works in one shot.

variable "anthropic_api_key"        { type = string; sensitive = true; default = "" }
variable "voyage_api_key"           { type = string; sensitive = true; default = "" }
variable "openai_api_key"           { type = string; sensitive = true; default = "" }
variable "cohere_api_key"           { type = string; sensitive = true; default = "" }
variable "tavily_api_key"           { type = string; sensitive = true; default = "" }
variable "serper_api_key"           { type = string; sensitive = true; default = "" }
variable "linkedin_client_id"       { type = string; sensitive = true; default = "" }
variable "linkedin_client_secret"   { type = string; sensitive = true; default = "" }
variable "linkedin_access_token"    { type = string; sensitive = true; default = "" }
variable "linkedin_refresh_token"   { type = string; sensitive = true; default = "" }
variable "linkedin_person_urn"      { type = string; sensitive = true; default = "" }
variable "substack_email"           { type = string; sensitive = true; default = "" }
variable "substack_password"        { type = string; sensitive = true; default = "" }
variable "smtp_host"                { type = string; default = "smtp.gmail.com" }
variable "smtp_port"                { type = number; default = 587 }
variable "smtp_username"            { type = string; sensitive = true; default = "" }
variable "smtp_password"            { type = string; sensitive = true; default = "" }
variable "smtp_from_address"        { type = string; default = "" }
variable "smtp_to_address"          { type = string; default = "" }
variable "qdrant_api_key"           { type = string; sensitive = true; default = "" }
variable "mcp_knowledge_token"      { type = string; sensitive = true; default = "" }
variable "dashboard_password"       { type = string; sensitive = true; default = "" }
variable "app_secret_key"           { type = string; sensitive = true; default = "" }
variable "postgres_password"        { type = string; sensitive = true; default = "" }
