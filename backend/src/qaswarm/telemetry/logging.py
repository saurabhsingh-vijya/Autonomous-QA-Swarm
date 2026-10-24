"""JSON log formatter with correlation id and a redaction filter for tokens and passwords."""

from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

correlation_id_var: ContextVar[str | None] = ContextVar("correlation_id", default=None)

# Order matters: specific token shapes first, generic key/value shapes last. The key/value patterns
# accept plain (``password=x``), header (``Password: x``) and JSON (``"password": "x"``) forms.
_KV_KEYS = r"(password|passwd|pwd|secret|token|access[_-]?key|private[_-]?key|client[_-]?secret)"
_REDACTION_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.S),
        "[REDACTED:private-key]",
    ),
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*"), "[REDACTED:private-key]"),
    (re.compile(r"\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{20,}\b"), "[REDACTED:github-token]"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b"), "[REDACTED:github-token]"),
    (re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED:gitlab-token]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[REDACTED:aws-access-key]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"), "[REDACTED:slack-token]"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"), "[REDACTED:anthropic-key]"),
    (re.compile(r"\bsk-[A-Za-z0-9_\-]{32,}\b"), "[REDACTED:api-key]"),
    (
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
        "[REDACTED:jwt]",
    ),
    (re.compile(r"(?i)(authorization\s*[:=]\s*)(bearer\s+)?[A-Za-z0-9._\-+/=]+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._\-+/=]{8,}"), "Bearer [REDACTED]"),
    (
        re.compile(r"(?i)\b(x-dev-user|x-api-key|x-exec-token|api[_-]?key)\s*[:=]\s*\S+"),
        r"\1=[REDACTED]",
    ),
    # JSON / YAML shape: "password": "value"  or  'token': 'value'  (quotes around key and value)
    (
        re.compile(r"(?i)([\"']" + _KV_KEYS + r"[\"']\s*[:=]\s*)[\"'][^\"'\n]*[\"']"),
        r"\1[REDACTED]",
    ),
    # Plain shape: password=value, token: value, AQS_EXEC_TOKEN=value
    (re.compile(r"(?i)\b([A-Z0-9_]*" + _KV_KEYS + r")\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"(://[^/\s:@]+:)[^@/\s]+@"), r"\1[REDACTED]@"),
]

SENSITIVE_KEYS = frozenset(
    {
        "authorization",
        "password",
        "passwd",
        "secret",
        "token",
        "x-dev-user",
        "x-exec-token",
        "x-api-key",
        "api_key",
        "cookie",
        "set-cookie",
        "private_key",
        "client_secret",
    }
)


def redact_text(text: str) -> str:
    for pattern, replacement in _REDACTION_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            k: ("[REDACTED]" if str(k).lower() in SENSITIVE_KEYS else redact_value(v))
            for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact_value(v) for v in value]
    return value


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_value(record.msg) if isinstance(record.msg, str | dict) else record.msg
        if record.args:
            record.args = tuple(redact_value(a) for a in record.args)
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "correlation_id": correlation_id_var.get(),
        }
        for key in ("job_id", "task_id", "org_id", "method", "path", "status_code", "duration_ms"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return redact_text(json.dumps(payload, default=str))


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access",):
        logging.getLogger(noisy).handlers[:] = []
        logging.getLogger(noisy).propagate = False
