"""Deny-by-default local policy for API checks.

Allowed: safe methods (GET, HEAD, OPTIONS) against hosts on the allow-list (loopback by default).
Everything else is blocked with a reason; mutating methods need target authorization (HA-01),
which is not implemented yet, so they are never run.
"""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlsplit

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_BLOCKED_HOSTS = frozenset({"169.254.169.254", "metadata.google.internal"})


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    reason: str
    rule: str


def evaluate_api_check(method: str, url: str, allowed_hosts: list[str]) -> PolicyDecision:
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return PolicyDecision(False, "Only http and https targets are supported.", "scheme")
    host = (parts.hostname or "").lower()
    if not host:
        return PolicyDecision(False, "The URL has no host.", "host")
    if host in _BLOCKED_HOSTS:
        return PolicyDecision(False, "Cloud metadata endpoints are always blocked.", "metadata")
    if parts.username or parts.password:
        return PolicyDecision(False, "Credentials in URLs are not allowed.", "credentials")
    if method.upper() not in SAFE_METHODS:
        return PolicyDecision(
            False,
            f"{method.upper()} is a mutating method; it needs target authorization (HA-01), "
            "which is not available in this build.",
            "method",
        )
    allowed = {h.lower() for h in allowed_hosts}
    if host in allowed:
        return PolicyDecision(True, "host on the local allow-list", "allowlist")
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        ip = None
    if ip is not None and ip.is_loopback and "127.0.0.1" in allowed:
        return PolicyDecision(True, "loopback address", "loopback")
    return PolicyDecision(
        False,
        f"Host '{host}' is not on the API-check allow-list (AQS_API_ALLOWED_HOSTS). "
        "External targets need registration and attestation (HA-01).",
        "allowlist",
    )
