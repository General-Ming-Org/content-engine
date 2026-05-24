"""Sync configured provider API keys into LiteLLM's environment conventions."""
from __future__ import annotations

import os

import structlog

from config import get_settings
from services.ai.model_capabilities import provider_from_model_id

logger = structlog.get_logger(__name__)

# LiteLLM env var names per provider prefix
_PROVIDER_ENV: dict[str, tuple[str, str]] = {
    "anthropic": ("ANTHROPIC_API_KEY", "anthropic_api_key"),
    "openai": ("OPENAI_API_KEY", "openai_api_key"),
    "gemini": ("GEMINI_API_KEY", "gemini_api_key"),
    "mistral": ("MISTRAL_API_KEY", "mistral_api_key"),
    "groq": ("GROQ_API_KEY", "groq_api_key"),
    "deepseek": ("DEEPSEEK_API_KEY", "deepseek_api_key"),
    "xai": ("XAI_API_KEY", "xai_api_key"),
    "openrouter": ("OPENROUTER_API_KEY", "openrouter_api_key"),
}


def sync_provider_env_keys() -> None:
    """Push Settings values into os.environ so LiteLLM can authenticate."""
    settings = get_settings()
    for _provider, (env_name, attr) in _PROVIDER_ENV.items():
        value = getattr(settings, attr, "") or ""
        if value:
            os.environ[env_name] = value


def api_key_for_model(model_id: str) -> str | None:
    """Return an explicit api_key for acompletion when configured."""
    settings = get_settings()
    provider = provider_from_model_id(model_id)
    if not provider:
        return None
    entry = _PROVIDER_ENV.get(provider)
    if not entry:
        return None
    _, attr = entry
    key = getattr(settings, attr, "") or ""
    return key or None


def missing_key_message(model_id: str) -> str | None:
    """Human-readable hint when the provider key for this model is absent."""
    settings = get_settings()
    provider = provider_from_model_id(model_id)
    entry = _PROVIDER_ENV.get(provider)
    if not entry:
        return None
    env_name, attr = entry
    if getattr(settings, attr, ""):
        return None
    return (
        f"No API key configured for provider '{provider}' ({env_name} in .env). "
        f"Set {env_name} to match LLM_PROVIDER={settings.llm_provider.strip()}."
    )
