"""Provider/model capability detection for portable LiteLLM calls.

LiteLLM accepts many provider/model strings; this module centralizes the
parameter quirks we have observed so call sites stay provider-agnostic.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelCapabilities:
    """How to shape a chat completion request for a given model id."""

    uses_max_completion_tokens: bool
    omits_temperature: bool
    supports_json_mode: bool
    min_output_tokens: int


def _model_name(model_id: str) -> str:
    if "/" in model_id:
        return model_id.split("/", 1)[1].lower()
    return model_id.lower()


def get_capabilities(model_id: str) -> ModelCapabilities:
    """Infer request constraints from a LiteLLM provider-qualified model id."""
    name = _model_name(model_id)
    provider = model_id.split("/")[0].lower() if "/" in model_id else ""

    # OpenAI GPT-5 and o-series reasoning endpoints
    if provider == "openai" and (
        "gpt-5" in name
        or name.startswith("o1")
        or name.startswith("o3")
        or name.startswith("o4")
    ):
        return ModelCapabilities(
            uses_max_completion_tokens=True,
            omits_temperature=True,
            supports_json_mode=False,
            min_output_tokens=2048,
        )

    # DeepSeek reasoner / R1-style
    if "deepseek-reasoner" in name or name.endswith("-r1") or "reasoner" in name:
        return ModelCapabilities(
            uses_max_completion_tokens=False,
            omits_temperature=True,
            supports_json_mode=False,
            min_output_tokens=2048,
        )

    # Gemini 2.5+ often supports JSON mode; older flash models use standard params
    if provider in {"gemini", "google"}:
        return ModelCapabilities(
            uses_max_completion_tokens=False,
            omits_temperature=False,
            supports_json_mode="2.5" in name or "2.0" in name,
            min_output_tokens=1024,
        )

    # Anthropic, Mistral, Groq, xAI, OpenRouter-hosted chat models
    return ModelCapabilities(
        uses_max_completion_tokens=False,
        omits_temperature=False,
        supports_json_mode=provider == "openai",
        min_output_tokens=1024,
    )


def effective_max_tokens(model_id: str, requested: int) -> int:
    """Raise output budget for models that burn tokens on internal reasoning."""
    caps = get_capabilities(model_id)
    return max(requested, caps.min_output_tokens)


def provider_from_model_id(model_id: str) -> str:
    """Return the LiteLLM provider segment (e.g. openai, anthropic, gemini)."""
    if "/" not in model_id:
        return ""
    provider, _ = model_id.split("/", 1)
    aliases = {
        "google": "gemini",
        "vertex_ai": "vertex_ai",
    }
    return aliases.get(provider.lower(), provider.lower())


def normalize_provider_model(provider: str, model: str) -> tuple[str, str]:
    """Normalize env-style provider + bare model names to LiteLLM conventions."""
    p = provider.strip().strip("/").lower()
    m = model.strip().strip("/")

    alias_map = {
        "google": "gemini",
        "vertex": "vertex_ai",
    }
    p = alias_map.get(p, p)

    # Allow LLM_MODEL to already include provider prefix
    if "/" in m:
        parts = m.split("/", 1)
        if parts[0].lower() == p or not p:
            return (parts[0].lower(), parts[1])
        return (p, m)

    return (p, m)
