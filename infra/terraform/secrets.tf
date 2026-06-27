# Secret Manager — one secret per credential.
#
# All values are set in terraform.tfvars and applied with `terraform apply`.
# Empty strings are skipped (Secret Manager rejects empty payloads).
# To rotate: update tfvars and apply again (creates a new secret version).

locals {
  secret_keys = toset([
    "anthropic-api-key",
    "voyage-api-key",
    "openai-api-key",
    "cohere-api-key",
    "tavily-api-key",
    "serper-api-key",
    "linkedin-client-id",
    "linkedin-client-secret",
    "linkedin-access-token",
    "linkedin-refresh-token",
    "linkedin-person-urn",
    "substack-email",
    "substack-password",
    "smtp-username",
    "smtp-password",
    "qdrant-api-key",
    "mcp-knowledge-token",
    "dashboard-password",
    "app-secret-key",
    "postgres-password",
  ])

  secrets = {
    "anthropic-api-key"      = var.anthropic_api_key
    "voyage-api-key"         = var.voyage_api_key
    "openai-api-key"         = var.openai_api_key
    "cohere-api-key"         = var.cohere_api_key
    "tavily-api-key"         = var.tavily_api_key
    "serper-api-key"         = var.serper_api_key
    "linkedin-client-id"     = var.linkedin_client_id
    "linkedin-client-secret" = var.linkedin_client_secret
    "linkedin-access-token"  = var.linkedin_access_token
    "linkedin-refresh-token" = var.linkedin_refresh_token
    "linkedin-person-urn"    = var.linkedin_person_urn
    "substack-email"         = var.substack_email
    "substack-password"      = var.substack_password
    "smtp-username"          = var.smtp_username
    "smtp-password"          = var.smtp_password
    "qdrant-api-key"         = var.qdrant_api_key
    "mcp-knowledge-token"    = var.mcp_knowledge_token
    "dashboard-password"     = var.dashboard_password
    "app-secret-key"         = var.app_secret_key
    "postgres-password"      = var.postgres_password
  }

  # Secret Manager rejects empty payloads — only seed non-empty tfvars values.
  seeded_secret_keys = toset(concat(
    var.anthropic_api_key != "" ? ["anthropic-api-key"] : [],
    var.voyage_api_key != "" ? ["voyage-api-key"] : [],
    var.openai_api_key != "" ? ["openai-api-key"] : [],
    var.cohere_api_key != "" ? ["cohere-api-key"] : [],
    var.tavily_api_key != "" ? ["tavily-api-key"] : [],
    var.serper_api_key != "" ? ["serper-api-key"] : [],
    var.linkedin_client_id != "" ? ["linkedin-client-id"] : [],
    var.linkedin_client_secret != "" ? ["linkedin-client-secret"] : [],
    var.linkedin_access_token != "" ? ["linkedin-access-token"] : [],
    var.linkedin_refresh_token != "" ? ["linkedin-refresh-token"] : [],
    var.linkedin_person_urn != "" ? ["linkedin-person-urn"] : [],
    var.substack_email != "" ? ["substack-email"] : [],
    var.substack_password != "" ? ["substack-password"] : [],
    var.smtp_username != "" ? ["smtp-username"] : [],
    var.smtp_password != "" ? ["smtp-password"] : [],
    var.qdrant_api_key != "" ? ["qdrant-api-key"] : [],
    var.mcp_knowledge_token != "" ? ["mcp-knowledge-token"] : [],
    var.dashboard_password != "" ? ["dashboard-password"] : [],
    var.app_secret_key != "" ? ["app-secret-key"] : [],
    var.postgres_password != "" ? ["postgres-password"] : [],
  ))
}

resource "google_secret_manager_secret" "secrets" {
  for_each  = local.secret_keys
  secret_id = each.key

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret_version" "initial" {
  # Instance keys are public secret IDs, not secret values — nonsensitive() is safe here.
  for_each    = nonsensitive(local.seeded_secret_keys)
  secret      = google_secret_manager_secret.secrets[each.key].id
  secret_data = local.secrets[each.key]

  depends_on = [google_secret_manager_secret.secrets]
}
