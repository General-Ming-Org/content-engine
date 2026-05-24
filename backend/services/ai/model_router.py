"""Single explicit LLM model resolver.

There are no model tiers or per-task overrides. The operator specifies exactly
one provider and one model in env:

    LLM_PROVIDER=anthropic
    LLM_MODEL=claude-sonnet-4-6

The resolver returns LiteLLM's provider-qualified string:

    anthropic/claude-sonnet-4-6
"""
import structlog

from config import get_settings
from services.ai.api_keys import missing_key_message
from services.ai.model_capabilities import normalize_provider_model

logger = structlog.get_logger(__name__)

_notified_missing_config = False


class LLMConfigurationError(RuntimeError):
    """Raised when the required single-model LLM config is incomplete."""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.title = "LLM configuration missing"
        self.message = message


async def pick_model(task: str) -> str:
    """Return the configured provider-qualified LiteLLM model ID.

    Missing provider/model is a system configuration error. We log it and
    notify admins once per process so background jobs surface an actionable
    dashboard notification instead of failing silently.
    """
    settings = get_settings()
    raw_provider = settings.llm_provider.strip().strip("/")
    raw_model = settings.llm_model.strip().strip("/")

    missing: list[str] = []
    if not raw_provider:
        missing.append("LLM_PROVIDER")
    if not raw_model:
        missing.append("LLM_MODEL")
    if missing:
        message = (
            f"{' and '.join(missing)} must be set before running LLM task '{task}'. "
            "Set both values in .env, then restart backend and worker."
        )
        logger.error("llm_configuration_missing", task=task, missing=missing)
        await _notify_missing_config(message)
        raise LLMConfigurationError(message)

    provider, model = normalize_provider_model(raw_provider, raw_model)
    model_id = f"{provider}/{model}"

    key_message = missing_key_message(model_id)
    if key_message:
        logger.error("llm_api_key_missing", task=task, model_id=model_id)
        await _notify_missing_config(key_message)
        raise LLMConfigurationError(key_message)

    return model_id


async def _notify_missing_config(message: str) -> None:
    global _notified_missing_config
    if _notified_missing_config:
        return
    _notified_missing_config = True
    try:
        from services.notifications.notifier import broadcast_admin_error

        await broadcast_admin_error("LLM configuration missing", message)
    except Exception as exc:
        logger.warning("llm_configuration_notification_failed", error=str(exc))
