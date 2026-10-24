"""Sample target app for API, browser, security and performance checks (dev/test fixture).

Standard library only, so the worker can start it with an isolated interpreter and no
dependencies. It is deliberately imperfect so the checks have something to find:

* ``/login`` sets a session cookie without ``HttpOnly``/``SameSite``;
* no Content-Security-Policy or Referrer-Policy headers are sent;
* ``/boom`` answers 500 with a Python traceback in the body (verbose error);
* ``/redirect?to=`` is an open redirect, and ``/redirect-private`` redirects to the cloud metadata
  address, which the worker's egress policy must refuse;
* ``X-Powered-By`` discloses a framework version.

Sample data — no repository code executed. This app is bundled with the Execution Service.
"""

from __future__ import annotations

import argparse
import json
import secrets
import threading
import time
import traceback
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Sample Target App</title></head>
<body>
<h1 id="title">Sample Target App</h1>
<p>Sample data — no repository code executed.</p>
<button id="inc" type="button">Increment</button>
<span id="count">0</span>
<form id="greet" onsubmit="return false">
  <input id="name" name="name" placeholder="name">
  <p id="greeting" hidden></p>
</form>
<a id="login-link" href="/login">login</a>
<script>
  let n = 0;
  document.getElementById('inc').addEventListener('click', () => {
    n += 1; document.getElementById('count').textContent = String(n);
    console.log('counter is now ' + n);
  });
  document.getElementById('name').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      const g = document.getElementById('greeting');
      g.textContent = 'Hello, ' + e.target.value + '!'; g.hidden = false;
    }
  });
  console.warn('sample warning from the page');
</script>
</body></html>
"""

LOGIN_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Login</title></head>
<body><h1>Login</h1><form method="post" action="/login">
<input id="user" name="user"><input id="password" name="password" type="password">
<button id="submit" type="submit">Sign in</button></form></body></html>
"""


class Store:
    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.items: dict[int, dict[str, object]] = {1: {"id": 1, "name": "seed-item"}}
        self.next_id = 2

    def create(self, name: str) -> dict[str, object]:
        with self.lock:
            item: dict[str, object] = {"id": self.next_id, "name": name}
            self.items[self.next_id] = item
            self.next_id += 1
            return item


STORE = Store()


class Handler(BaseHTTPRequestHandler):
    server_version = "SampleTarget/0.4"
    sys_version = ""

    def log_message(self, fmt: str, *args: object) -> None:  # quiet; the worker captures stdout
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)

    # ------------------------------------------------------------------ helpers
    def _send(
        self,
        status: int,
        body: bytes,
        content_type: str,
        extra: dict[str, str] | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("X-Powered-By", "SampleFramework/1.2.3")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, status: int, payload: object, extra: dict[str, str] | None = None) -> None:
        self._send(status, json.dumps(payload).encode(), "application/json; charset=utf-8", extra)

    def _body(self) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        return self.rfile.read(min(length, 1_000_000)) if length else b""

    # ------------------------------------------------------------------- routes
    def do_HEAD(self) -> None:  # noqa: N802 - http.server API
        self.do_GET()

    def do_GET(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        path, query = parts.path, parse_qs(parts.query)
        if path == "/health":
            self._json(200, {"status": "ok", "time": time.time()})
        elif path == "/":
            self._send(200, PAGE.encode(), "text/html; charset=utf-8")
        elif path == "/login":
            # Deliberately weak: a cookie without HttpOnly / SameSite (the checks must flag it).
            self._send(
                200,
                LOGIN_PAGE.encode(),
                "text/html; charset=utf-8",
                {"Set-Cookie": f"csrf={secrets.token_hex(8)}; Path=/"},
            )
        elif path == "/api/items":
            self._json(200, {"items": list(STORE.items.values()), "count": len(STORE.items)})
        elif path.startswith("/api/items/"):
            try:
                item = STORE.items.get(int(path.rsplit("/", 1)[1]))
            except ValueError:
                item = None
            if item is None:
                self._json(404, {"error": "not_found", "detail": "no such item"})
            else:
                self._json(200, item)
        elif path == "/api/slow":
            ms = min(int(query.get("ms", ["500"])[0]), 10_000)
            time.sleep(ms / 1000.0)
            self._json(200, {"slept_ms": ms})
        elif path == "/api/protected":
            auth = self.headers.get("Authorization", "")
            if auth != "Bearer fixture-token-not-a-secret":
                self._json(401, {"error": "unauthorized"}, {"WWW-Authenticate": "Bearer"})
            else:
                self._json(200, {"ok": True, "echo_authorization": auth})
        elif path == "/redirect":
            to = query.get("to", ["/"])[0]
            self._send(302, b"", "text/plain", {"Location": to})
        elif path == "/redirect-private":
            self._send(302, b"", "text/plain", {"Location": "http://169.254.169.254/latest/meta-data/"})
        elif path == "/redirect-loop":
            self._send(302, b"", "text/plain", {"Location": "/redirect-loop"})
        elif path == "/boom":
            try:
                raise RuntimeError("database connection refused for user app@db.internal")
            except RuntimeError:
                body = "Internal Server Error\n\n" + traceback.format_exc()
                self._send(500, body.encode(), "text/plain; charset=utf-8")
        else:
            self._send(
                404,
                f"<h1>Not Found</h1><p>No route for {path}</p>".encode(),
                "text/html; charset=utf-8",
            )

    def do_POST(self) -> None:  # noqa: N802
        parts = urlsplit(self.path)
        if parts.path == "/api/items":
            try:
                payload = json.loads(self._body() or b"{}")
                name = str(payload["name"])
            except (ValueError, KeyError, TypeError):
                self._json(422, {"error": "validation_failed", "detail": "name is required"})
                return
            self._json(201, STORE.create(name))
        elif parts.path == "/login":
            self._body()
            token = secrets.token_hex(8)
            self._send(
                303,
                b"",
                "text/plain",
                {"Location": "/", "Set-Cookie": f"session={token}; Path=/"},
            )
        else:
            self._json(405, {"error": "method_not_allowed"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"sample-target-app listening on http://{args.host}:{server.server_port}", flush=True)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
