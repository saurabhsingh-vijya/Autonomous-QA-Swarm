"""Policy-enforcing forward proxy for browser traffic (the worker-local "target egress gateway").

Chromium follows redirects inside the network stack, where Playwright's request interception does
not reliably see them, so the browser engine routes **all** traffic (loopback included) through this
proxy. Every plain request (absolute-URI form) and every ``CONNECT`` tunnel is checked against the
:class:`TargetPolicy` at connect time; refused destinations get ``403`` and are recorded as
violations. Bound to ``127.0.0.1`` on an ephemeral port, single purpose, torn down with the check.
"""

from __future__ import annotations

import contextlib
import select
import socket
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

import httpx

from qaswarm_exec.targets.policy import TargetBlocked, TargetPolicy

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "proxy-connection",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}
MAX_FORWARD_BODY = 10 * 1024 * 1024


@dataclass
class Violation:
    url: str
    reason: str
    detail: str
    stage: str = "proxy"


@dataclass
class ProxyState:
    policy: TargetPolicy
    violations: list[Violation] = field(default_factory=list)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def refuse(self, url: str, exc: TargetBlocked) -> None:
        with self.lock:
            if len(self.violations) < 200:
                self.violations.append(Violation(url, exc.reason, exc.detail))


class _Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    state: ProxyState  # set on the server class

    def log_message(self, fmt: str, *args: Any) -> None:  # silent; evidence comes from the engine
        return

    # ------------------------------------------------------------- CONNECT
    def do_CONNECT(self) -> None:  # noqa: N802 - http.server API
        host, _, port_text = self.path.rpartition(":")
        port = int(port_text) if port_text.isdigit() else 443
        url = f"https://{host}:{port}/"
        try:
            self.state.policy.check_url(url)
        except TargetBlocked as exc:
            self.state.refuse(url, exc)
            self._refuse(exc)
            return
        try:
            upstream = socket.create_connection((host.strip("[]"), port), timeout=10)
        except OSError:
            self.send_error(502, "upstream connection failed")
            return
        self.send_response(200, "Connection established")
        self.end_headers()
        self._tunnel(self.connection, upstream)

    def _tunnel(self, client: socket.socket, upstream: socket.socket) -> None:
        sockets = [client, upstream]
        try:
            while True:
                readable, _, errored = select.select(sockets, [], sockets, 30)
                if errored or not readable:
                    break
                for s in readable:
                    data = s.recv(65536)
                    if not data:
                        return
                    (upstream if s is client else client).sendall(data)
        except OSError:
            pass
        finally:
            with contextlib.suppress(OSError):
                upstream.close()

    # ---------------------------------------------------------- plain HTTP
    def _forward(self) -> None:
        url = self.path
        if not url.startswith(("http://", "https://")):
            host = self.headers.get("Host", "")
            url = f"http://{host}{url}"
        try:
            self.state.policy.check_url(url)
        except TargetBlocked as exc:
            self.state.refuse(url, exc)
            self._refuse(exc)
            return
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(min(length, MAX_FORWARD_BODY)) if length else b""
        headers = {
            k: v
            for k, v in self.headers.items()
            if k.lower() not in _HOP_BY_HOP and k.lower() != "host"
        }
        try:
            with httpx.Client(follow_redirects=False, trust_env=False, timeout=30.0) as client:
                resp = client.request(self.command, url, headers=headers, content=body)
        except httpx.HTTPError as exc:
            self.send_error(502, f"upstream error: {type(exc).__name__}")
            return
        self.send_response(resp.status_code)
        for k, v in resp.headers.multi_items():
            if k.lower() not in _HOP_BY_HOP and k.lower() != "content-length":
                self.send_header(k, v)
        self.send_header("Content-Length", str(len(resp.content)))
        self.send_header("Connection", "close")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(resp.content)
        self.close_connection = True

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = do_HEAD = do_OPTIONS = _forward  # noqa: N815

    def _refuse(self, exc: TargetBlocked) -> None:
        body = f"qaswarm egress policy refused {exc.host}: {exc.reason}".encode()
        self.send_response(403, "Refused by egress policy")
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)
        self.close_connection = True

    def _url_host(self, url: str) -> str:
        return urlsplit(url).hostname or ""


class PolicyProxy:
    def __init__(self, policy: TargetPolicy) -> None:
        self.state = ProxyState(policy)
        handler = type("BoundHandler", (_Handler,), {"state": self.state})
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    @property
    def address(self) -> str:
        return f"http://127.0.0.1:{self.server.server_port}"

    @property
    def violations(self) -> list[Violation]:
        with self.state.lock:
            return list(self.state.violations)

    def __enter__(self) -> PolicyProxy:
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
