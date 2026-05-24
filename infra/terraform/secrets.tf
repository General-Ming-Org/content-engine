# Secret Manager — one secret per credential.
#
# Initial values come from terraform variables. To rotate, write a new version
# via gcloud:  gcloud secrets versions add anthropic-api-key --data-file=-
# The VM startup script always reads the latest version.

locals {
  secrets = {
    "anthropic-api-key"        = var.anthropic_api_key
    "voyage-api-key"           = var.voyage_api_key
    "openai-api-key"           = var.openai_api_key
    "cohere-api-key"           = var.cohere_api_key
    "tavily-api-key"           = var.tavily_api_key
    "serper-api-key"           = var.serper_api_key
    "linkedin-client-id"       = var.linkedin_client_id
    "linkedin-client-secret"   = var.linkedin_client_secret
    "linkedin-access-token"    = var.linkedin_access_token
    "linkedin-refresh-token"   = var.linkedin_refresh_token
    "linkedin-person-urn"      = var.linkedin_person_urn
    "substack-email"           = var.substack_email
    "substack-password"        = var.substack_password
    "smtp-username"            = var.smtp_username
    "smtp-password"            = var.smtp_password
    "qdrant-api-key"           = var.qdrant_api_key
    "mcp-knowledge-token"      = var.mcp_knowledge_token
    "dashboard-password"       = var.dashboard_password
    "app-secret-key"           = var.app_secret_key
    "postgres-password"        = var.postgres_password
  }
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = local.secrets
  secret_id = each.key

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "initial" {
  for_each = {
    for k, v in local.secrets : k => v
    if v != ""
  }
  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = each.value
}
