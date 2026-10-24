"""Opaque cursor pagination over ULID primary keys (newest first)."""

from __future__ import annotations

import base64
import json

from qaswarm.api.errors import Problem

DEFAULT_LIMIT = 50
MAX_LIMIT = 200


def encode_cursor(last_id: str) -> str:
    raw = json.dumps({"k": last_id}, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode_cursor(cursor: str | None) -> str | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        key = data["k"]
        if not isinstance(key, str):
            raise ValueError
        return key
    except Exception as exc:
        raise Problem(400, "bad_request", "The cursor is malformed or expired.") from exc


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_LIMIT
    if limit < 1 or limit > MAX_LIMIT:
        raise Problem(400, "bad_request", f"limit must be between 1 and {MAX_LIMIT}.")
    return limit
