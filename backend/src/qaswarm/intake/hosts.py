"""DNS resolution with private-address rejection (SEC-002, TM-07)."""

from __future__ import annotations

import ipaddress
import socket

_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def is_public_address(ip: str) -> bool:
    addr = ipaddress.ip_address(ip)
    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped
    if isinstance(addr, ipaddress.IPv4Address) and addr in _CGNAT:
        return False
    return not (
        addr.is_private
        or addr.is_loopback
        or addr.is_link_local
        or addr.is_multicast
        or addr.is_reserved
        or addr.is_unspecified
    )


class HostRejected(Exception):
    def __init__(self, reason: str, message: str) -> None:
        self.reason = reason
        self.message = message
        super().__init__(message)


def resolve_public_host(host: str, port: int = 443) -> list[str]:
    """Resolve ``host`` and return its addresses; raise ``HostRejected`` if any is non-public."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except socket.gaierror as exc:
        raise HostRejected("dns_failure", f"Host '{host}' could not be resolved.") from exc
    addresses = sorted({str(info[4][0]) for info in infos})
    if not addresses:
        raise HostRejected("dns_failure", f"Host '{host}' resolved to no address.")
    for ip in addresses:
        if not is_public_address(ip):
            raise HostRejected(
                "private_address",
                f"Host '{host}' resolves to a private, loopback, link-local or reserved address.",
            )
    return addresses
