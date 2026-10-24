"""Target egress policy (SEC-005, TM-23): which hosts a check may talk to.

Externally supplied targets (registered ``TargetEnvironment`` rows, redirect locations, browser
navigations) are refused when they resolve to loopback, RFC1918, link-local (including the cloud
metadata address ``169.254.169.254``), CGNAT, multicast, reserved, unspecified or IPv6 unique-local
addresses, unless the operator enables controlled local testing with
``AQS_EXEC_ALLOW_LOCAL_TARGETS=true``. The worker-started local fixture target is not "external":
it is bound to ``127.0.0.1`` by the worker itself and is allowed by construction.

The address is checked at **connect time** by :mod:`qaswarm_exec.targets.http` (resolution happens
immediately before each connection), not only when the target was registered.
"""

from __future__ import annotations

import ipaddress
import socket
from dataclasses import dataclass, field
from urllib.parse import urlsplit

_CGNAT = ipaddress.ip_network("100.64.0.0/10")
_METADATA = ipaddress.ip_address("169.254.169.254")
ALLOWED_SCHEMES = frozenset({"http", "https"})


class TargetBlocked(Exception):
    """The policy refused a host. ``reason`` is a short machine-readable code."""

    def __init__(self, host: str, reason: str, detail: str) -> None:
        self.host = host
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}")


def classify_address(ip: str) -> str | None:
    """Return why ``ip`` is non-public, or ``None`` when it is a public unicast address."""
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if addr == _METADATA:
        return "cloud_metadata"
    if isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT:
        return "cgnat"
    if addr.is_unspecified:
        return "unspecified"
    if addr.is_loopback:
        return "loopback"
    if addr.is_link_local:
        return "link_local"
    if addr.is_private:
        return "private"
    if addr.is_multicast:
        return "multicast"
    if addr.is_reserved:
        return "reserved"
    return None


def is_public_address(ip: str) -> bool:
    return classify_address(ip) is None


@dataclass(frozen=True)
class TargetPolicy:
    """What one check may connect to.

    ``allowed_hosts`` is the authorised host set (``host`` or ``host:port`` entries, lower case).
    An empty set means "no host is authorised" and every connection is refused. ``allow_local``
    is the controlled local-testing mode; ``local_fixture`` marks the worker-started target whose
    loopback address is allowed by construction.
    """

    allowed_hosts: frozenset[str] = frozenset()
    allow_local: bool = False
    local_fixture: bool = False
    max_redirects: int = 5

    def host_allowed(self, host: str, port: int | None) -> bool:
        h = host.lower().strip("[]")
        if h in self.allowed_hosts:
            return True
        return port is not None and f"{h}:{port}" in self.allowed_hosts

    def check_url(self, url: str) -> tuple[str, int]:
        """Validate scheme, authority and policy for ``url``; return ``(host, port)``."""
        parts = urlsplit(url)
        if parts.scheme not in ALLOWED_SCHEMES:
            raise TargetBlocked(
                url, "scheme_not_allowed", f"scheme '{parts.scheme}' is not allowed"
            )
        if parts.username or parts.password:
            raise TargetBlocked(url, "userinfo_not_allowed", "URL must not carry credentials")
        host = parts.hostname
        if not host:
            raise TargetBlocked(url, "no_host", "URL has no host")
        port = parts.port or (443 if parts.scheme == "https" else 80)
        if not self.host_allowed(host, port):
            raise TargetBlocked(
                host,
                "host_not_authorized",
                f"host '{host}:{port}' is outside the authorised target",
            )
        self.check_host(host, port)
        return host, port

    def check_host(self, host: str, port: int = 80) -> list[str]:
        """Resolve ``host`` now and refuse non-public addresses (unless allowed). Returns the IPs."""
        if self.local_fixture:
            # The worker started this target itself on loopback; nothing external is involved.
            return [host]
        try:
            infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise TargetBlocked(
                host, "dns_failure", f"host '{host}' could not be resolved"
            ) from exc
        addresses = sorted({str(info[4][0]) for info in infos})
        if not addresses:
            raise TargetBlocked(host, "dns_failure", f"host '{host}' resolved to no address")
        if self.allow_local:
            return addresses
        for ip in addresses:
            why = classify_address(ip)
            if why is not None:
                raise TargetBlocked(
                    host,
                    "private_address",
                    f"host '{host}' resolves to a {why.replace('_', ' ')} address ({ip}); "
                    "set AQS_EXEC_ALLOW_LOCAL_TARGETS=true for controlled local testing",
                )
        return addresses


@dataclass(frozen=True)
class ResolvedTarget:
    """A target as the engines see it: base URL plus the policy that governs connections."""

    kind: str  # local_fixture | registered
    base_url: str
    policy: TargetPolicy
    name: str = ""
    target_id: str | None = None
    allowed_activities: frozenset[str] = field(default_factory=frozenset)

    def url(self, path: str) -> str:
        if path.startswith(("http://", "https://")):
            return path
        return self.base_url.rstrip("/") + "/" + path.lstrip("/")


def hosts_for(base_url: str, extra: list[str] | None = None) -> frozenset[str]:
    """Authorised host set for a base URL: ``host`` and ``host:port`` plus explicit extras."""
    parts = urlsplit(base_url)
    out: set[str] = set()
    if parts.hostname:
        host = parts.hostname.lower()
        port = parts.port or (443 if parts.scheme == "https" else 80)
        out.add(f"{host}:{port}")
        if parts.port is None:
            out.add(host)
    for item in extra or []:
        if item:
            out.add(item.lower())
    return frozenset(out)
