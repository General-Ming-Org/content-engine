"""Research-pipeline error types and provider failure classification."""
from __future__ import annotations


class ResearchProviderError(RuntimeError):
    """A non-data issue with the configured LLM provider.

    These should stop the sweep and notify admins because retrying individual
    topics will not help until configuration, billing, or quota is fixed.
    """

    def __init__(self, title: str, message: str) -> None:
        super().__init__(message)
        self.title = title
        self.message = message


def classify_provider_error(exc: Exception) -> ResearchProviderError | None:
    """Return a user-actionable provider error when LiteLLM/provider failed.

    We classify by exception class name and message because LiteLLM wraps many
    provider-specific errors in RetryError / OpenAIException / AnthropicError
    depending on retry path.
    """
    text = f"{type(exc).__name__}: {exc}"
    lower = text.lower()

    if "llmconfigurationerror" in lower or "llm_provider" in lower or "llm_model" in lower:
        return ResearchProviderError(
            "Research sweep blocked: LLM configuration missing",
            str(exc),
        )

    if any(
        token in lower
        for token in [
            "authenticationerror",
            "401",
            "unauthorized",
            "invalid api key",
            "incorrect api key",
            "no api key",
            "must provide an api key",
        ]
    ):
        return ResearchProviderError(
            "Research sweep blocked: LLM authentication failed",
            "The selected research model could not authenticate with its provider. "
            "Check that the matching provider API key is present in .env for "
            "LLM_PROVIDER and LLM_MODEL, then restart backend and worker.",
        )

    if any(token in lower for token in ["insufficient_quota", "quota", "billing details"]):
        return ResearchProviderError(
            "Research sweep blocked: LLM quota exhausted",
            "The selected LLM provider rejected the request because the account has "
            "no remaining quota or billing is not enabled. Add quota/billing or "
            "choose a different model/provider, then rerun the sweep.",
        )

    if "ratelimiterror" in lower or "rate limit" in lower or "too many requests" in lower:
        return ResearchProviderError(
            "Research sweep blocked: LLM rate limit reached",
            "The selected LLM provider is rate limiting research synthesis. Wait a "
            "few minutes, reduce sweep volume, or choose a provider/model with a "
            "higher rate limit.",
        )

    if (
        "unsupported_parameter" in lower
        or "unsupported_value" in lower
        or "max_completion_tokens" in lower
    ):
        return ResearchProviderError(
            "Research sweep blocked: LLM request rejected",
            "The provider rejected the completion request (unsupported API parameters). "
            "Check LLM_MODEL compatibility with LLM_PROVIDER or update the application.",
        )

    return None
