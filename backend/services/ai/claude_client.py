"""
Deprecated shim. The wrapped client is now provider-agnostic and lives in
`llm_client.py`. This module re-exports the same names so existing call sites
(`from services.ai.claude_client import generate, generate_json`) continue to
work. New code should import from `services.ai.llm_client` or
`services.ai` directly.
"""
from services.ai.llm_client import generate, generate_json

__all__ = ["generate", "generate_json"]
