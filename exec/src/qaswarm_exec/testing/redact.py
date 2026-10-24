"""Redaction for request/response summaries, console logs and failure messages (SEC-008).

Runs in the worker *before* anything is uploaded; the control plane's Evidence Store redacts again.
Header values of credential-bearing headers are replaced wholesale; free text is scrubbed with the
same token patterns the control plane uses.
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "proxy-authorization",
        "cookie",
        "set-cookie",
        "x-api-key",
        "x-auth-token",
        "x-csrf-token",
        "x-xsrf-token",
        "x-amz-security-token",
        "x-dev-user",
    }
)
SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "password",
        "passwd",
        "secret",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "cookie",
        "session",
        "client_secret",
        "private_key",
    }
)
REDACTED = "[REDACTED]"

_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)(authorization[\"']?\s*[:=]\s*[\"']?)(bearer\s+)?[A-Za-z0-9._\-+/=]+"),
        r"[REDACTED]",
    ),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-+/=]{8,}"), "Bearer [REDACTED]"),
    (
        re.compile(
            r"(?i)\b(x-api-key|api[_-]?key|access[_-]?token|refresh[_-]?token)\s*[:=]\s*\S+"
        ),
        r"\1=[REDACTED]",
    ),
    (re.compile(r"(?i)\b(password|passwd|secret|token)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)\b(cookie|set-cookie)\s*[:=]\s*[^\r\n]+"), r"\1=[REDACTED]"),
    (re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"), "[REDACTED:github-token]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED:gitlab-token]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED:aws-access-key]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED:anthropic-key]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
        "[REDACTED:jwt]",
    ),
    (re.compile(r"(://[^/\s:@]+:)[^@/\s]+@"), r"\1[REDACTED]@"),
]


def redact_text(text: str) -> str:
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_headers(headers: dict[str, str] | None) -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in (headers or {}).items():
        out[k] = REDACTED if k.lower() in SENSITIVE_HEADERS else redact_text(str(v))
    return out


def redact_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.username or parts.password:
        netloc = parts.hostname or ""
        if parts.port:
            netloc += f":{parts.port}"
        parts = parts._replace(netloc=f"{REDACTED}@{netloc}")
    return redact_text(urlunsplit(parts))


def redact_value(value: Any, *, depth: int = 0) -> Any:
    if depth > 12:
        return REDACTED
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            str(k): (
                REDACTED if str(k).lower() in SENSITIVE_KEYS else redact_value(v, depth=depth + 1)
            )
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_value(v, depth=depth + 1) for v in value]
    return value


def summarize_body(body: bytes, *, limit: int = 2048) -> dict[str, Any]:
    """Short, redacted body summary for evidence: never the whole payload."""
    text = body[:limit].decode("utf-8", errors="replace")
    return {
        "bytes": len(body),
        "preview": redact_text(text),
        "preview_truncated": len(body) > limit,
    }
