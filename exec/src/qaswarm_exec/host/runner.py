"""Process entry points: ``python -m qaswarm_exec`` and the embedded dev worker."""

from __future__ import annotations

import logging
import os
import socket
import tempfile
import threading
import uuid
from pathlib import Path

import httpx

from qaswarm_exec.host.client import ControlPlaneClient
from qaswarm_exec.host.worker import ExecWorker
from qaswarm_exec.runtime.subprocess_runtime import SubprocessRuntime

log = logging.getLogger("qaswarm_exec.runner")


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


def build_worker(
    *,
    control_plane_url: str,
    token: str,
    allow_code_execution: bool,
    fixtures_dir: str | None,
    worker_id: str | None = None,
    workspace_root: str | None = None,
    heartbeat_seconds: float = 30.0,
) -> ExecWorker:
    http = httpx.Client(base_url=control_plane_url.rstrip("/"), timeout=60.0)
    client = ControlPlaneClient(http, token)
    return ExecWorker(
        client,
        SubprocessRuntime(),
        worker_id=worker_id or f"exec-{socket.gethostname()}-{uuid.uuid4().hex[:8]}",
        workspace_root=workspace_root or Path(tempfile.gettempdir()) / "aqs-workers",
        allow_code_execution=allow_code_execution,
        fixtures_dir=fixtures_dir,
        heartbeat_seconds=heartbeat_seconds,
    )


def run_embedded(
    *,
    control_plane_url: str,
    token: str,
    allow_code_execution: bool,
    fixtures_dir: str | None,
    stop: threading.Event,
) -> None:
    """Started by the API process when ``AQS_EMBEDDED_EXEC_WORKER=true`` (local dev only)."""
    stop.wait(2.0)  # let uvicorn bind before the first lease call
    worker = build_worker(
        control_plane_url=control_plane_url,
        token=token,
        allow_code_execution=allow_code_execution,
        fixtures_dir=fixtures_dir,
        worker_id="exec-embedded",
    )
    worker.run_forever(stop)


def main() -> None:  # pragma: no cover - process entry point
    logging.basicConfig(level=os.environ.get("AQS_EXEC_LOG_LEVEL", "INFO"))
    token = os.environ.get("AQS_EXEC_TOKEN")
    if not token:
        raise SystemExit("AQS_EXEC_TOKEN is required")
    worker = build_worker(
        control_plane_url=os.environ.get("AQS_EXEC_CONTROL_PLANE_URL", "http://127.0.0.1:8000"),
        token=token,
        allow_code_execution=_flag("AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION"),
        fixtures_dir=os.environ.get("AQS_EXEC_FIXTURES_DIR") or None,
        worker_id=os.environ.get("AQS_EXEC_WORKER_ID") or None,
        workspace_root=os.environ.get("AQS_EXEC_WORKSPACE_ROOT") or None,
        heartbeat_seconds=float(os.environ.get("AQS_EXEC_HEARTBEAT_SECONDS", "30")),
    )
    log.warning(
        "runtime=%s isolation=%s repository_code_execution_allowed=%s",
        worker.runtime.name,
        worker.runtime.isolation,
        worker.allow_code_execution,
    )
    worker.run_forever()


if __name__ == "__main__":  # pragma: no cover
    main()
