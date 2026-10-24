"""RFC 9457 problem+json errors with a stable ``error_code``."""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from qaswarm.config import get_settings
from qaswarm.telemetry.logging import correlation_id_var

PROBLEM_MEDIA_TYPE = "application/problem+json"

_TITLES: dict[int, str] = {
    400: "Bad request",
    401: "Unauthenticated",
    403: "Forbidden",
    404: "Not found",
    405: "Method not allowed",
    409: "Conflict",
    412: "Precondition failed",
    422: "Request validation failed",
    429: "Rate limited",
    500: "Internal error",
    501: "Not implemented",
    503: "Service unavailable",
}


class Problem(Exception):
    def __init__(
        self,
        status: int,
        error_code: str,
        detail: str,
        *,
        title: str | None = None,
        type_slug: str | None = None,
        headers: dict[str, str] | None = None,
        **extra: Any,
    ) -> None:
        self.status = status
        self.error_code = error_code
        self.detail = detail
        self.title = title or _TITLES.get(status, "Error")
        self.type_slug = type_slug or error_code.replace("_", "-")
        self.headers = headers or {}
        self.extra = extra
        super().__init__(detail)


def problem_body(
    request: Request,
    status: int,
    error_code: str,
    detail: str,
    title: str | None = None,
    type_slug: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    body: dict[str, Any] = {
        "type": get_settings().problem_type_base + (type_slug or error_code.replace("_", "-")),
        "title": title or _TITLES.get(status, "Error"),
        "status": status,
        "detail": detail,
        "instance": request.url.path,
        "error_code": error_code,
        "trace_id": correlation_id_var.get() or request.headers.get("x-correlation-id"),
    }
    body.update({k: v for k, v in extra.items() if v is not None})
    return body


def problem_response(
    request: Request,
    status: int,
    error_code: str,
    detail: str,
    *,
    title: str | None = None,
    type_slug: str | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content=problem_body(request, status, error_code, detail, title, type_slug, **extra),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )


def _pointer(loc: tuple[Any, ...]) -> str:
    parts = [str(p) for p in loc if p not in ("body",)]
    return "/" + "/".join(parts) if parts else "/"


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(Problem)
    async def _problem(request: Request, exc: Problem) -> JSONResponse:
        return problem_response(
            request,
            exc.status,
            exc.error_code,
            exc.detail,
            title=exc.title,
            type_slug=exc.type_slug,
            headers=exc.headers,
            **exc.extra,
        )

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError) -> JSONResponse:
        errors = [
            {
                "pointer": _pointer(tuple(e.get("loc", ()))),
                "code": e.get("type"),
                "message": e.get("msg"),
            }
            for e in exc.errors()
        ]
        return problem_response(
            request,
            422,
            "validation_failed",
            f"{len(errors)} field{'s' if len(errors) != 1 else ''} failed validation.",
            type_slug="validation-error",
            errors=errors,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        code = {
            404: "not_found",
            405: "method_not_allowed",
            401: "unauthenticated",
            403: "insufficient_role",
        }.get(exc.status_code, "http_error")
        detail = (
            exc.detail if isinstance(exc.detail, str) else _TITLES.get(exc.status_code, "Error")
        )
        return problem_response(
            request, exc.status_code, code, detail, headers=dict(exc.headers or {})
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception) -> JSONResponse:
        # Detail never includes the exception text: it may contain hostnames or secrets.
        return problem_response(
            request,
            500,
            "internal_error",
            "An internal error occurred. Use the trace_id when reporting it.",
        )
