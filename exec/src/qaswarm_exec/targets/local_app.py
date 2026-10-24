"""Worker-started local fixture target (phase 4 stand-in for the ephemeral in-sandbox target).

The app lives under ``exec/fixtures/<name>/app.py``; it ships with the worker and is **not**
repository code. It is started with an isolated interpreter (``-I``), a scrubbed environment, bound
to ``127.0.0.1`` on an ephemeral port, health-checked with a bounded wait and always terminated
(process tree) when the check ends.
"""

from __future__ import annotations

import contextlib
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

from qaswarm_exec.runtime.subprocess_runtime import _kill_tree

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
READY_TIMEOUT_SECONDS = 20.0


class LocalTargetError(Exception):
    pass


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


class LocalTargetApp:
    def __init__(self, fixtures_dir: str | os.PathLike[str], name: str, log_path: Path) -> None:
        if not _NAME.match(name):
            raise LocalTargetError(f"invalid local target name '{name}'")
        self.script = Path(fixtures_dir) / name / "app.py"
        if not self.script.is_file():
            raise LocalTargetError(f"local target '{name}' not found in the fixtures directory")
        self.name = name
        self.log_path = log_path
        self.port = 0
        self.proc: subprocess.Popen[bytes] | None = None

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> LocalTargetApp:
        self.port = _free_port()
        env = {
            k: os.environ[k]
            for k in ("PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP")
            if k in os.environ
        }
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        windows = sys.platform == "win32"
        self._log = self.log_path.open("wb")
        self.proc = subprocess.Popen(  # noqa: S603 - fixed argv; the script ships with the worker
            [
                sys.executable,
                "-I",
                str(self.script),
                "--host",
                "127.0.0.1",
                "--port",
                str(self.port),
            ],
            cwd=str(self.script.parent),
            stdin=subprocess.DEVNULL,
            stdout=self._log,
            stderr=subprocess.STDOUT,
            env=env,
            creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if windows else 0,
            start_new_session=not windows,
        )
        deadline = time.monotonic() + READY_TIMEOUT_SECONDS
        with httpx.Client(trust_env=False, timeout=1.0) as client:
            while time.monotonic() < deadline:
                if self.proc.poll() is not None:
                    self.__exit__(None, None, None)
                    raise LocalTargetError(
                        f"local target exited early with code {self.proc.returncode}"
                    )
                try:
                    if client.get(f"{self.base_url}/health").status_code == 200:
                        return self
                except httpx.HTTPError:
                    pass
                time.sleep(0.1)
        self.__exit__(None, None, None)
        raise LocalTargetError("local target did not become healthy in time")

    def __exit__(self, *exc: object) -> None:
        if self.proc is not None:
            _kill_tree(self.proc)
            self.proc = None
        with contextlib.suppress(Exception):
            self._log.close()
