from functools import lru_cache
from typing import Literal  # noqa: F401  retained for downstream callers

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # App
    app_env: Literal["development", "production"] = "development"
    # Signs JWTs AND derives the Fernet key for encrypting user_credentials at rest.
    # Rotating this invalidates all logins and stored credentials.
    app_secret_key: str = "insecure-dev-key-change-in-production"
    log_level: str = "INFO"
    # Public URL of the web app (dashboard links in emails). Example: http://localhost:3000
    app_public_url: str = ""
    # Public URL of this API (for /api/brand/* — Gravatar, BIMI). Example: http://localhost:8000
    api_public_url: str = ""

    # Database
    database_url: str = "postgresql://content_engine:devpassword@localhost:5432/content_engine"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # AI — single explicit model selection.
    # Example: LLM_PROVIDER=anthropic, LLM_MODEL=claude-sonnet-4-6
    # LiteLLM receives this as "<provider>/<model>".
    llm_provider: str = ""
    llm_model: str = ""
    # Only takes effect when the resolved model's provider supports it (Anthropic today).
    anthropic_prompt_caching: bool = True

    # Provider API keys — only the ones whose models are actually used need to be set.
    # LiteLLM reads these by environment-variable convention.
    anthropic_api_key: str = ""
    openai_api_key: str = ""          # Also used by embeddings if EMBEDDING_PROVIDER=openai
    gemini_api_key: str = ""           # Google Gemini
    mistral_api_key: str = ""
    groq_api_key: str = ""
    deepseek_api_key: str = ""
    xai_api_key: str = ""              # xAI Grok
    openrouter_api_key: str = ""       # Aggregator — gives access to nearly any model

    # Embeddings — required (no defaults). Resolved by services.ai.embeddings.get_active_embedder();
    # missing provider/model/key raises EmbeddingConfigurationError at first use.
    # Valid providers: voyage, openai, cohere. Valid model IDs per provider live in
    # services/ai/embeddings.py (_PROVIDER_REGISTRY → each class's _MODELS dict).
    embedding_provider: str = ""
    embedding_model: str = ""
    voyage_api_key: str = ""
    cohere_api_key: str = ""
    # openai_api_key declared above in the LLM section — reused here for OpenAI embeddings

    # Vector DB (Qdrant)
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    vector_similarity_threshold: float = 0.85  # dedup + cache-hit threshold

    # MCP servers — internal tool sources for the backend's Claude calls
    mcp_tavily_url: str = "http://tavily-mcp:8001"
    mcp_knowledge_url: str = "http://knowledge-mcp:8002"
    mcp_knowledge_token: str = ""  # bearer token for external Claude clients

    # Search (kept for direct fallback when MCP is unavailable)
    tavily_api_key: str = ""
    serper_api_key: str = ""

    # Research sweep volume — 4 domains × per_domain, capped by max_topics (LLM cost control)
    research_sweep_per_domain: int = 3
    research_sweep_max_topics: int = 10

    # LinkedIn — optional legacy fallback. Users normally save Client ID / Secret
    # in Settings (encrypted in user_credentials). Env vars apply when unset per user.
    linkedin_client_id: str = ""
    linkedin_client_secret: str = ""
    # OAuth callback base override. If empty, uses APP_PUBLIC_URL (recommended for local dev:
    # http://localhost:3000/api/publish/linkedin/callback via Vite proxy).
    linkedin_redirect_uri: str = ""

    # Substack — no operator-level config. Each user's email/password/publication_url
    # is stored in user_credentials (encrypted via APP_SECRET_KEY).

    # SMTP — operator's outbound mail credentials. Each user owns their own
    # recipient ("to") address via user_credentials.
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_address: str = ""

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def async_database_url(self) -> str:
        """Convert postgresql:// to postgresql+asyncpg:// for async driver."""
        return self.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)


@lru_cache
def get_settings() -> Settings:
    return Settings()
