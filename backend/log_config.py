"""Structured logging setup.

- Bridges Python's stdlib `logging` through structlog so libraries (SQLAlchemy,
  uvicorn, asyncpg, etc.) emit through the same pipeline as our own logger.
- Pretty key=value console output in development; line-delimited JSON in
  production (drop-in compatible with Datadog / Loki / Cloud Logging).
- Library loggers (especially SQL) are pinned to WARNING by default to keep
  the request log clean.
"""
from __future__ import annotations

import logging
import sys

import structlog

_SERVICE_NAME = "content-engine"
_SERVICE_VERSION = "0.1.0"


def _add_service_context(
    _logger: structlog.types.WrappedLogger,
    _method_name: str,
    event_dict: structlog.types.EventDict,
) -> structlog.types.EventDict:
    from config import get_settings

    settings = get_settings()
    event_dict.setdefault("service", _SERVICE_NAME)
    event_dict.setdefault("version", _SERVICE_VERSION)
    event_dict.setdefault("env", settings.app_env)
    return event_dict


_LIBRARY_LOG_LEVELS = {
    "sqlalchemy.engine": logging.WARNING,
    "sqlalchemy.pool": logging.WARNING,
    "sqlalchemy.dialects": logging.WARNING,
    "sqlalchemy.orm": logging.WARNING,
    "asyncpg": logging.WARNING,
    "aiosmtplib": logging.WARNING,
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "uvicorn.access": logging.WARNING,   # we emit our own request log
    "watchfiles": logging.WARNING,
    "litellm": logging.WARNING,
}


def configure_logging(level: str = "INFO", *, is_production: bool = False) -> None:
    """Configure structlog + stdlib logging. Call once at process startup."""
    log_level = getattr(logging, level.upper(), logging.INFO)

    shared_processors: list = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        _add_service_context,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if is_production:
        renderer: structlog.types.Processor = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=True)

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Bridge stdlib `logging` records into structlog so they get the same
    # JSON / console formatting. Without this, uvicorn / SQLAlchemy messages
    # would render through their own logger and look inconsistent.
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processor=renderer,
        )
    )

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(log_level)

    for name, lvl in _LIBRARY_LOG_LEVELS.items():
        logging.getLogger(name).setLevel(lvl)
