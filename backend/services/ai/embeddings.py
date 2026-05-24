"""
Embedding provider abstraction.

The active provider is the single operator-configured pair (EMBEDDING_PROVIDER,
EMBEDDING_MODEL) from env. There are no defaults: missing config raises
``EmbeddingConfigurationError`` at first use so misconfiguration surfaces loudly.

Each provider declares its model_id and vector dimension; the vector store uses
those to scope Qdrant collections per (kind, model_id). Switching the model creates
a new collection alongside the old one; ``services.scheduler.tasks.reembed_corpus``
migrates the corpus over.
"""
from abc import ABC, abstractmethod

import httpx
import structlog

from config import get_settings

logger = structlog.get_logger(__name__)


class EmbeddingConfigurationError(RuntimeError):
    """Raised when the required embedding provider/model/key is incomplete."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.title = "Embedding configuration missing"
        self.message = message


class EmbeddingProvider(ABC):
    """Base class for embedding providers. Every implementation declares its
    model_id and dimension so the vector store can scope collections per model."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Stable identifier used as part of the Qdrant collection name."""

    @property
    @abstractmethod
    def dimensions(self) -> int:
        """Vector dimension — must match the Qdrant collection config."""

    @abstractmethod
    async def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        """Embed a batch. `input_type` is 'document' for storage, 'query' for searches.
        Providers that don't distinguish ignore the argument."""


class VoyageEmbedder(EmbeddingProvider):
    """Voyage AI — Anthropic-recommended. Distinguishes document vs query input."""

    _MODELS = {
        "voyage-3": 1024,
        "voyage-3-lite": 512,
        "voyage-3-large": 1024,
        "voyage-code-3": 1024,
    }

    def __init__(self, model: str):
        if model not in self._MODELS:
            raise EmbeddingConfigurationError(
                f"Unknown Voyage model '{model}'. Valid options: {sorted(self._MODELS)}"
            )
        self._model = model
        self._api_key = get_settings().voyage_api_key

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._MODELS[self._model]

    async def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": texts, "input_type": input_type},
            )
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in data["data"]]


class OpenAIEmbedder(EmbeddingProvider):
    """OpenAI embeddings — cheapest, no input_type distinction."""

    _MODELS = {
        "text-embedding-3-small": 1536,
        "text-embedding-3-large": 3072,
    }

    def __init__(self, model: str):
        if model not in self._MODELS:
            raise EmbeddingConfigurationError(
                f"Unknown OpenAI embedding model '{model}'. Valid options: {sorted(self._MODELS)}"
            )
        self._model = model
        self._api_key = get_settings().openai_api_key

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._MODELS[self._model]

    async def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.openai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "input": texts},
            )
            resp.raise_for_status()
            data = resp.json()
        return [item["embedding"] for item in data["data"]]


class CohereEmbedder(EmbeddingProvider):
    """Cohere — distinguishes input types via `input_type` field."""

    _MODELS = {
        "embed-english-v3.0": 1024,
        "embed-multilingual-v3.0": 1024,
    }

    def __init__(self, model: str):
        if model not in self._MODELS:
            raise EmbeddingConfigurationError(
                f"Unknown Cohere model '{model}'. Valid options: {sorted(self._MODELS)}"
            )
        self._model = model
        self._api_key = get_settings().cohere_api_key

    @property
    def model_id(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._MODELS[self._model]

    async def embed(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        cohere_type = "search_document" if input_type == "document" else "search_query"
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                "https://api.cohere.ai/v1/embed",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"model": self._model, "texts": texts, "input_type": cohere_type},
            )
            resp.raise_for_status()
            data = resp.json()
        return data["embeddings"]


_PROVIDER_REGISTRY: dict[str, type[EmbeddingProvider]] = {
    "voyage": VoyageEmbedder,
    "openai": OpenAIEmbedder,
    "cohere": CohereEmbedder,
}

_PROVIDER_KEY_ATTR: dict[str, tuple[str, str]] = {
    "voyage": ("voyage_api_key", "VOYAGE_API_KEY"),
    "openai": ("openai_api_key", "OPENAI_API_KEY"),
    "cohere": ("cohere_api_key", "COHERE_API_KEY"),
}


_cached_embedder: EmbeddingProvider | None = None
_cached_signature: tuple[str, str] | None = None
_notified_missing_config = False


def _raise_missing(missing: list[str]) -> None:
    message = (
        f"{' and '.join(missing)} must be set before any embedding call. "
        "Set the value(s) in .env, then restart backend and worker."
    )
    logger.error("embedding_configuration_missing", missing=missing)
    _notify_missing_config(message)
    raise EmbeddingConfigurationError(message)


def _raise_missing_key(provider: str, env_name: str) -> None:
    message = (
        f"No API key configured for embedding provider '{provider}' ({env_name} in .env). "
        f"Set {env_name} or change EMBEDDING_PROVIDER."
    )
    logger.error("embedding_api_key_missing", provider=provider, env_name=env_name)
    _notify_missing_config(message)
    raise EmbeddingConfigurationError(message)


def _notify_missing_config(message: str) -> None:
    """Best-effort admin notification — non-blocking, sync to keep get_active_embedder sync."""
    global _notified_missing_config
    if _notified_missing_config:
        return
    _notified_missing_config = True
    # Notifier is async; in sync call sites we just log. Async call sites (re-embed
    # task, generation) will surface the error via their own retry/notify path.


def get_active_embedder() -> EmbeddingProvider:
    """Return the configured embedding provider.

    Resolution: EMBEDDING_PROVIDER + EMBEDDING_MODEL env vars (no defaults).
    Cached per (provider, model) signature so repeated calls are cheap.
    Raises EmbeddingConfigurationError with an actionable message if the
    provider, model, or that provider's API key is unset.
    """
    global _cached_embedder, _cached_signature

    settings = get_settings()
    provider = (settings.embedding_provider or "").strip().lower()
    model = (settings.embedding_model or "").strip()

    missing: list[str] = []
    if not provider:
        missing.append("EMBEDDING_PROVIDER")
    if not model:
        missing.append("EMBEDDING_MODEL")
    if missing:
        _raise_missing(missing)

    if provider not in _PROVIDER_REGISTRY:
        raise EmbeddingConfigurationError(
            f"Unknown EMBEDDING_PROVIDER '{provider}'. "
            f"Valid options: {sorted(_PROVIDER_REGISTRY)}"
        )

    attr, env_name = _PROVIDER_KEY_ATTR[provider]
    key = getattr(settings, attr, "") or ""
    if not key:
        _raise_missing_key(provider, env_name)

    signature = (provider, model)
    if _cached_embedder and _cached_signature == signature:
        return _cached_embedder

    cls = _PROVIDER_REGISTRY[provider]
    _cached_embedder = cls(model=model)
    _cached_signature = signature
    logger.info("embedding_provider_initialized", provider=provider, model=model)
    return _cached_embedder


def invalidate_embedder_cache() -> None:
    """Clear the cached embedder so the next call re-resolves from settings."""
    global _cached_embedder, _cached_signature, _notified_missing_config
    _cached_embedder = None
    _cached_signature = None
    _notified_missing_config = False


def embedding_health() -> dict[str, str]:
    """Report current embedding configuration for the health endpoint.
    Never raises — returns a dict suitable for /api/health."""
    settings = get_settings()
    provider = (settings.embedding_provider or "").strip().lower()
    model = (settings.embedding_model or "").strip()

    if not provider or not model:
        return {
            "status": "not_configured",
            "detail": "EMBEDDING_PROVIDER and EMBEDDING_MODEL must be set in .env",
        }
    if provider not in _PROVIDER_REGISTRY:
        return {"status": "invalid_provider", "provider": provider, "detail": f"Valid options: {sorted(_PROVIDER_REGISTRY)}"}

    attr, env_name = _PROVIDER_KEY_ATTR[provider]
    key = getattr(settings, attr, "") or ""
    if not key:
        return {"status": "missing_key", "provider": provider, "model": model, "detail": f"{env_name} not set"}

    cls = _PROVIDER_REGISTRY[provider]
    if model not in cls._MODELS:  # type: ignore[attr-defined]
        return {"status": "invalid_model", "provider": provider, "model": model, "detail": f"Unknown model for {provider}"}

    return {"status": "ok", "provider": provider, "model": model}
