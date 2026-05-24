"""
Multi-provider model registry.

A model ID in this codebase is a LiteLLM-compatible provider-qualified string:
    "anthropic/claude-sonnet-4-6"
    "openai/gpt-5-mini"
    "gemini/gemini-2.5-flash"
    "mistral/mistral-large-latest"
    "groq/llama-3.3-70b-versatile"
    "deepseek/deepseek-chat"
    "xai/grok-4"
    "openrouter/<vendor>/<model>"   (any model in the OpenRouter catalogue)

The CATALOG below is only a UI hint list. The operator may use any
LiteLLM-compatible provider/model pair via LLM_PROVIDER and LLM_MODEL.
"""
from enum import Enum


class Provider(str, Enum):
    ANTHROPIC = "anthropic"
    OPENAI = "openai"
    GOOGLE = "gemini"          # LiteLLM prefix is "gemini/", not "google/"
    MISTRAL = "mistral"
    GROQ = "groq"
    DEEPSEEK = "deepseek"
    XAI = "xai"
    OPENROUTER = "openrouter"


class ModelInfo:
    __slots__ = ("id", "label", "provider", "supports_caching", "supports_mcp")

    def __init__(
        self,
        id: str,
        label: str,
        provider: Provider,
        supports_caching: bool = False,
        supports_mcp: bool = False,
    ) -> None:
        self.id = id
        self.label = label
        self.provider = provider
        self.supports_caching = supports_caching
        self.supports_mcp = supports_mcp

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "label": self.label,
            "provider": self.provider.value,
            "supports_caching": self.supports_caching,
            "supports_mcp": self.supports_mcp,
        }


# Curated default catalogue. Add new models here as providers ship them.
CATALOG: list[ModelInfo] = [
    # Anthropic — native prompt caching and MCP support
    ModelInfo("anthropic/claude-opus-4-7", "Claude Opus 4.7", Provider.ANTHROPIC, True, True),
    ModelInfo("anthropic/claude-sonnet-4-6", "Claude Sonnet 4.6", Provider.ANTHROPIC, True, True),
    ModelInfo("anthropic/claude-haiku-4-5-20251001", "Claude Haiku 4.5", Provider.ANTHROPIC, True, True),

    # OpenAI
    ModelInfo("openai/gpt-5", "GPT-5", Provider.OPENAI),
    ModelInfo("openai/gpt-5-mini", "GPT-5 mini", Provider.OPENAI),
    ModelInfo("openai/gpt-5-nano", "GPT-5 nano", Provider.OPENAI),
    ModelInfo("openai/gpt-4o", "GPT-4o", Provider.OPENAI),
    ModelInfo("openai/gpt-4o-mini", "GPT-4o mini", Provider.OPENAI),

    # Google Gemini
    ModelInfo("gemini/gemini-2.5-pro", "Gemini 2.5 Pro", Provider.GOOGLE),
    ModelInfo("gemini/gemini-2.5-flash", "Gemini 2.5 Flash", Provider.GOOGLE),
    ModelInfo("gemini/gemini-2.5-flash-lite", "Gemini 2.5 Flash Lite", Provider.GOOGLE),

    # Mistral
    ModelInfo("mistral/mistral-large-latest", "Mistral Large", Provider.MISTRAL),
    ModelInfo("mistral/mistral-small-latest", "Mistral Small", Provider.MISTRAL),

    # Groq — same models as others but ~10x faster inference
    ModelInfo("groq/llama-3.3-70b-versatile", "Llama 3.3 70B (Groq)", Provider.GROQ),
    ModelInfo("groq/llama-3.1-8b-instant", "Llama 3.1 8B (Groq)", Provider.GROQ),

    # DeepSeek — strong reasoning, cheap
    ModelInfo("deepseek/deepseek-chat", "DeepSeek V3", Provider.DEEPSEEK),
    ModelInfo("deepseek/deepseek-reasoner", "DeepSeek R1", Provider.DEEPSEEK),

    # xAI
    ModelInfo("xai/grok-4", "Grok 4", Provider.XAI),
]


def is_anthropic(model_id: str) -> bool:
    """LiteLLM accepts both prefixed and bare Anthropic model names."""
    return model_id.startswith("anthropic/") or model_id.startswith("claude-")


def get_info(model_id: str) -> ModelInfo | None:
    return next((m for m in CATALOG if m.id == model_id), None)


def supports_prompt_caching(model_id: str) -> bool:
    info = get_info(model_id)
    if info:
        return info.supports_caching
    # Default heuristic for off-catalogue strings
    return is_anthropic(model_id)


def supports_mcp(model_id: str) -> bool:
    info = get_info(model_id)
    if info:
        return info.supports_mcp
    return is_anthropic(model_id)
