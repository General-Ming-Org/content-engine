"""
Provider-agnostic LLM client.

Every LLM call in the codebase goes through this module. Responsibilities:
  1. Resolve the configured model via `model_router.pick_model(task)`.
  2. Apply per-model parameter rules from `model_capabilities`.
  3. Pass explicit API keys from Settings when available.
  4. Normalize token usage logging via LiteLLM's OpenAI-shaped response.

If a call needs JSON output, use `generate_json()` which retries once on parse failure.
"""
import json
from typing import Any

import structlog
from litellm import acompletion
from tenacity import retry, stop_after_attempt, wait_exponential

from config import get_settings
from services.ai.api_keys import api_key_for_model
from services.ai.model_capabilities import effective_max_tokens, get_capabilities
from services.ai.model_router import pick_model
from services.ai.providers import supports_mcp, supports_prompt_caching
from services.observability.metrics import record_llm_call

logger = structlog.get_logger(__name__)


def _build_completion_kwargs(
    *,
    model: str,
    system_content: Any,
    user: str,
    max_tokens: int,
    temperature: float,
    json_mode: bool = False,
) -> dict[str, Any]:
    caps = get_capabilities(model)
    limit = effective_max_tokens(model, max_tokens)

    kwargs: dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user},
        ],
    }

    if caps.uses_max_completion_tokens:
        kwargs["max_completion_tokens"] = limit
    else:
        kwargs["max_tokens"] = limit

    if not caps.omits_temperature:
        kwargs["temperature"] = temperature

    if json_mode and caps.supports_json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    key = api_key_for_model(model)
    if key:
        kwargs["api_key"] = key

    return kwargs


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
async def generate(
    task: str,
    system: str,
    user: str,
    max_tokens: int = 2048,
    temperature: float = 0.7,
    mcp_servers: list[dict[str, Any]] | None = None,
) -> str:
    """Issue a completion against whichever provider the task is routed to."""
    settings = get_settings()
    model = await pick_model(task)

    use_caching = settings.anthropic_prompt_caching and supports_prompt_caching(model)
    if use_caching:
        system_content: Any = [
            {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system_content = system

    kwargs = _build_completion_kwargs(
        model=model,
        system_content=system_content,
        user=user,
        max_tokens=max_tokens,
        temperature=temperature,
    )

    if mcp_servers and supports_mcp(model):
        kwargs["mcp_servers"] = mcp_servers
        kwargs["extra_headers"] = {"anthropic-beta": "mcp-client-2025-04-04"}
    elif mcp_servers:
        logger.debug("mcp_servers_ignored_unsupported_provider", model=model)

    response = await acompletion(**kwargs)

    usage = response.usage
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    logger.info(
        "llm_call",
        task=task,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cache_creation=getattr(usage, "cache_creation_input_tokens", 0) or 0,
        cache_read=getattr(usage, "cache_read_input_tokens", 0) or 0,
    )
    record_llm_call(
        task=task,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    return response.choices[0].message.content or ""


async def generate_json(
    task: str,
    system: str,
    user: str,
    max_tokens: int = 2048,
    temperature: float = 0.3,
) -> dict[str, Any]:
    """Generate and parse JSON. Retries once with stricter instructions on parse failure."""
    settings = get_settings()
    model = await pick_model(task)
    caps = get_capabilities(model)

    use_caching = settings.anthropic_prompt_caching and supports_prompt_caching(model)
    system_content: Any = (
        [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]
        if use_caching
        else system
    )

    kwargs = _build_completion_kwargs(
        model=model,
        system_content=system_content,
        user=user,
        max_tokens=max_tokens,
        temperature=temperature,
        json_mode=True,
    )
    response = await acompletion(**kwargs)
    raw = response.choices[0].message.content or ""

    usage = response.usage
    input_tokens = getattr(usage, "prompt_tokens", 0) or 0
    output_tokens = getattr(usage, "completion_tokens", 0) or 0
    logger.info(
        "llm_call",
        task=task,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        json_mode=True,
    )
    record_llm_call(
        task=task,
        model=model,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )

    try:
        return json.loads(_strip_fences(raw))
    except json.JSONDecodeError:
        logger.warning("llm_json_parse_retry", task=task, model=model)
        retry_temp = 0.0 if not caps.omits_temperature else 1.0
        repaired = await generate(
            task,
            system + "\n\nIMPORTANT: respond with valid JSON only. No markdown fences, no commentary.",
            user,
            max_tokens=effective_max_tokens(model, max_tokens),
            temperature=retry_temp,
        )
        return json.loads(_strip_fences(repaired))


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
    return text.strip()
