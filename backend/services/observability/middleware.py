"""HTTP middleware for request correlation and structured access logs."""
from __future__ import annotations

import time

import structlog
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from services.observability.context import bind_request_context, clear_context, new_request_id
from services.observability.metrics import is_slow_request, normalize_path, record_http_request

logger = structlog.get_logger(__name__)

_SKIP_LOG_PATHS = frozenset({"/api/health", "/api/docs", "/api/redoc", "/api/openapi.json"})


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        request_id = request.headers.get("x-request-id") or new_request_id()
        path = request.url.path
        method = request.method
        bind_request_context(request_id=request_id, method=method, path=path)

        start = time.perf_counter()
        status = 500
        response: Response | None = None

        try:
            response = await call_next(request)
            status = response.status_code
            return response
        except Exception:
            logger.exception(
                "request_unhandled_exception",
                route=f"{method} {normalize_path(path)}",
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            record_http_request(method=method, path=path, status=status, duration_ms=duration_ms)

            if path not in _SKIP_LOG_PATHS:
                log_kwargs = {
                    "method": method,
                    "path": path,
                    "route": f"{method} {normalize_path(path)}",
                    "status": status,
                    "duration_ms": round(duration_ms, 2),
                }
                if status >= 500:
                    logger.error("http_request", **log_kwargs)
                elif is_slow_request(duration_ms):
                    logger.warning("http_request", slow=True, **log_kwargs)
                else:
                    logger.info("http_request", **log_kwargs)

            if response is not None:
                response.headers["X-Request-ID"] = request_id

            clear_context()
