"""Correlation-ID propagation and structured request logging."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from qaswarm.telemetry.logging import correlation_id_var

log = logging.getLogger("qaswarm.api.request")

CORRELATION_HEADER = "X-Correlation-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        incoming = request.headers.get(CORRELATION_HEADER)
        correlation_id = incoming if incoming and len(incoming) <= 100 else uuid.uuid4().hex
        token = correlation_id_var.set(correlation_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            log.exception(
                "request failed",
                extra={"method": request.method, "path": request.url.path, "status_code": 500},
            )
            raise
        finally:
            correlation_id_var.reset(token)
        response.headers[CORRELATION_HEADER] = correlation_id
        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        correlation_id_var.set(correlation_id)
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response
