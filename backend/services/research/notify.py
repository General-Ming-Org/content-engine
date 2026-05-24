"""Admin notifications for research sweep outcomes."""
from __future__ import annotations

from typing import Any

import structlog

logger = structlog.get_logger(__name__)


async def notify_sweep_outcome(result: dict[str, Any]) -> None:
    """Notify admins when a sweep fails or is blocked (idempotent per outcome)."""
    status = result.get("status")
    found = int(result.get("results_found", 0) or 0)
    stored = int(result.get("results_stored", 0) or 0)
    skipped = int(result.get("results_skipped", 0) or 0)

    if status == "blocked":
        title = result.get("reason") or "Research sweep blocked"
        message = result.get("message") or "The sweep stopped due to an LLM provider issue."
        await _broadcast(title, message)
        return

    if status == "failed":
        await _broadcast(
            "Research sweep failed",
            result.get("error") or "The sweep task failed unexpectedly. Check worker logs.",
        )
        return

    if status != "complete":
        return

    if found == 0:
        await _broadcast(
            "Research sweep found no topics",
            "Search returned no results across domains. Verify Tavily or Serper API keys "
            "in .env and that search providers are reachable.",
        )
        return

    if stored == 0:
        reasons = result.get("skip_reasons") or {}
        dup = int(reasons.get("duplicate", 0) or 0)
        indexed = int(reasons.get("already_indexed", 0) or 0)
        errors = int(reasons.get("error", 0) or 0)
        if errors > 0:
            await _broadcast(
                "Research sweep failed",
                f"Found {found} topics but stored none. {errors} failed with errors — "
                "check worker logs (often PDF/binary source text or DB issues).",
            )
        elif dup + indexed >= found:
            await _broadcast(
                "Research sweep complete (no new topics)",
                f"Search found {found} candidates, but they are already in your research "
                "library (duplicates or previously indexed). No new topics were added.",
            )
        else:
            await _broadcast(
                "Research sweep failed",
                f"Found {found} topics but stored none ({skipped} skipped). Check "
                "LLM_PROVIDER, LLM_MODEL, API keys, and worker logs.",
            )


async def _broadcast(title: str, message: str) -> None:
    try:
        from services.notifications.notifier import broadcast_admin_error

        await broadcast_admin_error(title, message)
    except Exception as exc:
        logger.warning("research_sweep_notification_failed", error=str(exc))
