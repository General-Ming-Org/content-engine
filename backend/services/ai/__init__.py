"""
AI abstraction layer.

Every LLM call goes through `llm_client.generate()` — which resolves the single
operator-configured provider/model from `model_router.pick_model(task)` and
enables provider-specific extras when supported.

Every embedding call goes through `embeddings.get_active_embedder().embed(texts)` — which
returns the active provider configured in user_settings (with env fallback).

Vector storage is keyed by (collection_kind, embedding_model_id) — switching the embedding
model creates a new collection and triggers a re-embed task, leaving prior vectors intact
until the migration completes.
"""

from services.ai.embeddings import get_active_embedder, EmbeddingProvider
from services.ai.llm_client import generate, generate_json
from services.ai.model_router import LLMConfigurationError, pick_model
from services.ai.providers import CATALOG, Provider, get_info, supports_mcp, supports_prompt_caching
from services.ai.vector_store import VectorStore, get_vector_store

__all__ = [
    "generate",
    "generate_json",
    "get_active_embedder",
    "EmbeddingProvider",
    "LLMConfigurationError",
    "pick_model",
    "CATALOG",
    "Provider",
    "get_info",
    "supports_mcp",
    "supports_prompt_caching",
    "VectorStore",
    "get_vector_store",
]
