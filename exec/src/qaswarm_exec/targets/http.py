"""HTTP client whose every connection goes through the target policy.

``PolicyTransport`` re-checks the destination host immediately before the request is handed to
the connection pool (the closest point to "connect time" httpx exposes), so a DNS answer that
changed since planning is caught. Redirects are never followed automatically: ``CheckedClient``
walks them itself, re-validating every ``Location`` against the policy and the authorised host set,
with a bounded hop count. Environment proxies are ignored (``trust_env=False``).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin

import httpx

from qaswarm_exec.targets.policy import TargetBlocked, TargetPolicy

DEFAULT_TIMEOUT_MS = 10_000
MAX_BODY_CAPTURE = 64 * 1024


class PolicyTransport(httpx.HTTPTransport):
    def __init__(self, policy: TargetPolicy, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.policy = policy

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.policy.check_url(str(request.url))
        return super().handle_request(request)


@dataclass
class Hop:
    url: str
    status: int
    location: str | None


@dataclass
class Exchange:
    """Result of one logical request including any redirect chain."""

    method: str
    url: str
    final_url: str
    status: int
    headers: dict[str, str]
    body: bytes
    elapsed_ms: int
    hops: list[Hop] = field(default_factory=list)
    body_truncated: bool = False

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")

    def json(self) -> Any:
        import json

        return json.loads(self.body.decode("utf-8", errors="replace"))


class CheckedClient:
    def __init__(self, policy: TargetPolicy, *, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> None:
        self.policy = policy
        self._client = httpx.Client(
            transport=PolicyTransport(policy, retries=0),
            follow_redirects=False,
            trust_env=False,
            timeout=httpx.Timeout(timeout_ms / 1000.0),
            headers={"User-Agent": "qaswarm-exec/phase4 (+authorized-testing)"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> CheckedClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
        json_body: Any = None,
        timeout_ms: int | None = None,
        follow_redirects: bool = True,
    ) -> Exchange:
        """Perform ``method url``; raises ``TargetBlocked`` / ``httpx.TimeoutException`` etc."""
        hops: list[Hop] = []
        current = url
        current_method = method.upper()
        body: bytes | None = content
        json_payload = json_body
        started = time.perf_counter()
        timeout = httpx.Timeout((timeout_ms or DEFAULT_TIMEOUT_MS) / 1000.0)
        for _ in range(self.policy.max_redirects + 1):
            self.policy.check_url(current)
            resp = self._client.request(
                current_method,
                current,
                headers=headers,
                content=body,
                json=json_payload,
                timeout=timeout,
            )
            try:
                raw = resp.read()
            finally:
                resp.close()
            location = resp.headers.get("location")
            if not follow_redirects or not (300 <= resp.status_code < 400) or not location:
                elapsed = int((time.perf_counter() - started) * 1000)
                truncated = len(raw) > MAX_BODY_CAPTURE
                return Exchange(
                    method=method.upper(),
                    url=url,
                    final_url=current,
                    status=resp.status_code,
                    headers={k.lower(): v for k, v in resp.headers.items()},
                    body=raw[:MAX_BODY_CAPTURE],
                    elapsed_ms=elapsed,
                    hops=hops,
                    body_truncated=truncated,
                )
            hops.append(Hop(url=current, status=resp.status_code, location=location))
            next_url = urljoin(current, location)
            self.policy.check_url(next_url)  # refuses redirects to unauthorised/blocked hosts
            current = next_url
            if resp.status_code in (301, 302, 303) and current_method != "GET":
                current_method, body, json_payload = "GET", None, None
        raise TargetBlocked(
            url, "too_many_redirects", f"more than {self.policy.max_redirects} hops"
        )
