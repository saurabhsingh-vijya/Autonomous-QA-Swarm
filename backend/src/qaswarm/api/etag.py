"""ETag helpers: ``"<id>:v<version>"``; ``If-Match`` is optional in slice 1a but enforced when sent."""

from __future__ import annotations

from qaswarm.api.errors import Problem


def etag_for(resource_id: str, version: int) -> str:
    return f'"{resource_id}:v{version}"'


def parse_if_match(header: str | None, resource_id: str) -> int | None:
    if header is None or header.strip() == "*":
        return None
    value = header.strip().strip('"')
    prefix = f"{resource_id}:v"
    if not value.startswith(prefix) or not value[len(prefix) :].isdigit():
        raise Problem(412, "etag_mismatch", "If-Match does not match this resource.")
    return int(value[len(prefix) :])
