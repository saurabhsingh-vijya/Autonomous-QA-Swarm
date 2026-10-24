"""Bounded subprocess runtime.

**This is not a sandbox.** It gives a disposable working directory, a scrubbed environment, a wall
clock, an output cap and process-tree termination. It does **not** isolate the network, the file
system outside the workspace, CPU or memory. The design's gVisor/Docker sandbox (SEC-003/004) is
not available on this build, so worker runs record ``isolation = "process"`` and engines that
execute repository code are refused unless the operator opts in explicitly.
"""

from __future__ import annotations

import contextlib
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

from qaswarm_exec.runtime.base import ProcessResult, RunLimits

_POLL_SECONDS = 0.25
_SAFE_ENV_KEYS = ("PATH", "SYSTEMROOT", "COMSPEC", "TEMP", "TMP", "LANG", "LC_ALL", "PATHEXT")


def _kill_tree(proc: subprocess.Popen[bytes]) -> None:
    if proc.poll() is not None:
        return
    if platform.system() == "Windows":
        taskkill = shutil.which("taskkill") or "taskkill"
        subprocess.run(  # noqa: S603 - fixed argv, pid is an int
            [taskkill, "/F", "/T", "/PID", str(proc.pid)], capture_output=True, check=False
        )
    else:
        import signal

        killpg = getattr(os, "killpg", None)  # not present in the Windows stubs
        sigkill = getattr(signal, "SIGKILL", signal.SIGTERM)
        if killpg is not None:
            with contextlib.suppress(ProcessLookupError):
                killpg(proc.pid, sigkill)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()


class SubprocessRuntime:
    name = "subprocess"
    isolation = "process"
    network_policy = "unenforced"

    def __init__(self, python: str | None = None) -> None:
        self.python = python or sys.executable

    def available(self) -> bool:
        return True

    def scrubbed_env(self, extra: dict[str, str]) -> dict[str, str]:
        env = {k: os.environ[k] for k in _SAFE_ENV_KEYS if k in os.environ}
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = "utf-8"
        env["PYTHONUNBUFFERED"] = "1"
        env["AQS_SANDBOX"] = "process"
        env.update(extra)
        return env

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        limits: RunLimits,
        output_path: Path,
        cancel: threading.Event | None = None,
    ) -> ProcessResult:
        started = time.monotonic()
        windows = platform.system() == "Windows"
        # New process group (Windows) / session (POSIX) so the whole tree can be killed.
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) if windows else 0
        truncated = False
        killed_reason: str | None = None
        timed_out = False
        cancelled = False
        with output_path.open("wb") as out:
            proc = subprocess.Popen(  # noqa: S603 - argv built by an engine, never from repo text
                argv,
                cwd=str(cwd),
                stdin=subprocess.DEVNULL,
                stdout=out,
                stderr=subprocess.STDOUT,
                env=self.scrubbed_env(limits.env),
                creationflags=creationflags,
                start_new_session=not windows,
            )
            while True:
                code = proc.poll()
                if code is not None:
                    break
                elapsed = time.monotonic() - started
                if elapsed > limits.timeout_seconds:
                    timed_out = True
                    killed_reason = "wall clock exceeded"
                    _kill_tree(proc)
                    break
                if cancel is not None and cancel.is_set():
                    cancelled = True
                    killed_reason = "cancelled"
                    _kill_tree(proc)
                    break
                try:
                    size = output_path.stat().st_size
                except OSError:
                    size = 0
                if size > limits.output_cap_bytes:
                    truncated = True
                    killed_reason = "output cap exceeded"
                    _kill_tree(proc)
                    break
                time.sleep(_POLL_SECONDS)
        size = output_path.stat().st_size if output_path.exists() else 0
        if size > limits.output_cap_bytes:
            truncated = True
            with output_path.open("r+b") as f:
                f.truncate(limits.output_cap_bytes)
                f.seek(0, os.SEEK_END)
                f.write(b"\n[TRUNCATED: output cap exceeded]\n")
            size = output_path.stat().st_size
        return ProcessResult(
            exit_code=proc.returncode,
            timed_out=timed_out,
            cancelled=cancelled,
            duration_ms=int((time.monotonic() - started) * 1000),
            output_path=output_path,
            output_bytes=size,
            truncated=truncated,
            killed_reason=killed_reason,
        )
