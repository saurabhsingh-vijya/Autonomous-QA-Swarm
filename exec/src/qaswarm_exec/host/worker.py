"""The Execution Service worker loop.

For every leased task: register a worker run, heartbeat the lease on a thread, fetch the pinned
snapshot into a disposable workspace, run the engine (or the fetch itself for ``env_prepare``),
upload evidence, submit a schema-shaped result, and **always** report the worker run destroyed.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import logging
import platform
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from qaswarm_exec import __version__
from qaswarm_exec.host.client import (
    ControlPlaneClient,
    ControlPlaneError,
    LeaseLostError,
    ResultRejected,
)
from qaswarm_exec.host.source import FetchedSource, FetchError, fetcher_for
from qaswarm_exec.results.worker_result import build_worker_result
from qaswarm_exec.runtime.base import RunLimits, Runtime, Workspace
from qaswarm_exec.tools.base import ERROR, PASSED, SKIPPED, CheckContext, CheckResult
from qaswarm_exec.tools.browser_tests import playwright_status
from qaswarm_exec.tools.registry import ENGINES, UnknownEngine, get_engine

log = logging.getLogger("qaswarm_exec.worker")
LEASABLE = ["env_prepare", "check"]


def _iso(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


class _Sink:
    """Evidence sink that uploads through the control plane and remembers the ids."""

    def __init__(
        self, client: ControlPlaneClient, task_id: str, worker_id: str, worker_run_id: str
    ) -> None:
        self.client, self.task_id, self.worker_id, self.worker_run_id = (
            client,
            task_id,
            worker_id,
            worker_run_id,
        )
        self.ids: list[str] = []
        self.redactions = 0

    def put(
        self, *, kind: str, label: str, media_type: str, content: bytes, deterministic: bool = True
    ) -> str:
        res = self.client.upload_evidence(
            self.task_id,
            {
                "worker_id": self.worker_id,
                "worker_run_id": self.worker_run_id,
                "kind": kind,
                "label": label,
                "media_type": media_type,
                "content_base64": base64.b64encode(content).decode("ascii"),
                "deterministic": deterministic,
                "producer": f"qaswarm_exec {__version__}",
            },
        )
        self.ids.append(str(res["evidence_id"]))
        self.redactions += int(res.get("redactions", 0))
        return str(res["evidence_id"])


class ExecWorker:
    def __init__(
        self,
        client: ControlPlaneClient,
        runtime: Runtime,
        *,
        worker_id: str,
        workspace_root: str | Path,
        allow_code_execution: bool = False,
        fixtures_dir: str | None = None,
        heartbeat_seconds: float = 30.0,
        engine_settings: dict[str, Any] | None = None,
    ) -> None:
        self.client = client
        self.runtime = runtime
        self.worker_id = worker_id
        self.workspace_root = Path(workspace_root)
        self.allow_code_execution = allow_code_execution
        self.fixtures_dir = fixtures_dir
        self.heartbeat_seconds = heartbeat_seconds
        # Phase 4: worker-level settings for target-facing engines (never secrets).
        self.engine_settings: dict[str, Any] = {
            "fixtures_dir": fixtures_dir,
            "allow_local_targets": False,
            **(engine_settings or {}),
        }
        self.image_digest = (
            "sha256:"
            + hashlib.sha256(
                f"qaswarm_exec/{__version__}/{platform.python_version()}/{sorted(ENGINES)}".encode()
            ).hexdigest()[:32]
        )

    # ------------------------------------------------------------------ loop
    def run_once(self, batch_size: int = 1) -> int:
        tasks = self.client.lease(self.worker_id, LEASABLE, batch_size=batch_size)
        for task in tasks:
            self.process(task)
        return len(tasks)

    def run_forever(self, stop: threading.Event | None = None, idle_sleep: float = 1.0) -> None:
        stop = stop or threading.Event()
        log.info("exec worker started", extra={"worker_id": self.worker_id})
        while not stop.is_set():
            try:
                n = self.run_once()
            except ControlPlaneError as exc:
                log.warning("control plane error: %s", exc)
                n = 0
            except Exception:
                log.exception("worker loop error")
                n = 0
            if n == 0:
                stop.wait(idle_sleep)

    # --------------------------------------------------------------- process
    def process(self, task: dict[str, Any]) -> None:
        task_id = str(task["task_id"])
        limits = task.get("limits", {})
        run_limits = RunLimits(
            timeout_seconds=int(limits.get("task_wall_clock_seconds", 1800)),
            output_cap_bytes=int(limits.get("output_cap_bytes", 50 * 1024 * 1024)),
        )
        cancel = threading.Event()
        stop_hb = threading.Event()
        hb = threading.Thread(
            target=self._heartbeat_loop, args=(task_id, cancel, stop_hb), daemon=True
        )
        hb.start()
        started = time.monotonic()
        outcome, exit_code, output_bytes, truncated = "failed", None, 0, False
        worker_run_id: str | None = None
        try:
            worker_run_id = self.client.create_worker_run(
                task_id,
                {
                    "worker_id": self.worker_id,
                    "attempt_id": task.get("attempt_id"),
                    "runtime": self.runtime.name,
                    "isolation": self.runtime.isolation,
                    "image_digest": self.image_digest,
                    "limits": {
                        "timeout_seconds": run_limits.timeout_seconds,
                        "output_cap_bytes": run_limits.output_cap_bytes,
                    },
                    "network_policy": self.runtime.network_policy,
                },
            )
            with Workspace(self.workspace_root) as ws:
                sink = _Sink(self.client, task_id, self.worker_id, worker_run_id)
                if task["task_type"] == "env_prepare":
                    payload = self._env_prepare(task, ws.src, sink, worker_run_id)
                else:
                    payload = self._check(task, ws, sink, worker_run_id, run_limits, cancel)
                exit_code = payload["worker_result"]["exit"]["code"]
                output_bytes = payload["worker_result"]["resource_usage"]["output_bytes"]
                truncated = payload["worker_result"]["truncated"]
                if cancel.is_set():
                    outcome = "cancelled"
                    return
                self.client.submit_result(task_id, payload)
                outcome = "succeeded"
        except LeaseLostError:
            outcome = "cancelled"
            log.info("lease lost; result discarded", extra={"task_id": task_id})
        except ResultRejected as exc:
            outcome = "failed"
            log.warning("result rejected by control plane: %s", exc.body)
        except TimeoutError as exc:
            outcome = "timed_out"
            self._fail(task_id, "E-EXEC-007", "tool_error", False, "timed_out", str(exc))
        except FetchError as exc:
            outcome = "failed"
            self._fail(
                task_id, exc.code, "infrastructure_error", exc.retryable, "error", exc.detail
            )
        except UnknownEngine as exc:
            outcome = "failed"
            self._fail(
                task_id, "E-POLICY-001", "contract_error", False, "error", f"unknown engine {exc}"
            )
        except ControlPlaneError as exc:
            outcome = "failed"
            log.warning("control plane error during task: %s", exc)
        except Exception as exc:  # anything else is an infrastructure error, retried within budget
            outcome = "failed"
            log.exception("task crashed", extra={"task_id": task_id})
            self._fail(
                task_id,
                "E-EXEC-001",
                "infrastructure_error",
                True,
                "error",
                f"{type(exc).__name__}: {exc}",
            )
        finally:
            stop_hb.set()
            hb.join(timeout=5)
            if worker_run_id is None:
                log.info("task released before a worker run started", extra={"task_id": task_id})
            else:
                try:
                    self.client.destroy_worker_run(
                        worker_run_id,
                        {
                            "outcome": outcome,
                            "exit_code": exit_code,
                            "output_bytes": output_bytes,
                            "truncated": truncated,
                        },
                    )
                except ControlPlaneError:
                    log.exception(
                        "could not report worker run destroyed", extra={"task_id": task_id}
                    )
            log.info(
                "task finished",
                extra={
                    "task_id": task_id,
                    "outcome": outcome,
                    "duration_ms": int((time.monotonic() - started) * 1000),
                },
            )

    def _fail(
        self, task_id: str, code: str, error_class: str, retryable: bool, kind: str, message: str
    ) -> None:
        with contextlib.suppress(LeaseLostError):
            self.client.submit_failure(
                task_id,
                {
                    "worker_id": self.worker_id,
                    "error_code": code,
                    "error_class": error_class,
                    "retryable": retryable,
                    "kind": kind,
                    "message": message[:20000],
                },
            )

    def _heartbeat_loop(self, task_id: str, cancel: threading.Event, stop: threading.Event) -> None:
        while not stop.wait(self.heartbeat_seconds):
            try:
                self.client.heartbeat(task_id, self.worker_id)
            except LeaseLostError:
                cancel.set()
                return
            except ControlPlaneError as exc:
                log.warning("heartbeat failed: %s", exc)

    # ----------------------------------------------------------- task kinds
    def _fetch(self, task: dict[str, Any], dest: Path) -> FetchedSource:
        source = task["inputs"].get("source") or {}
        fetcher = fetcher_for(source, self.fixtures_dir)
        return fetcher.fetch(source, dest)

    def _env_prepare(
        self, task: dict[str, Any], src: Path, sink: _Sink, worker_run_id: str
    ) -> dict[str, Any]:
        t0 = datetime.now(UTC)
        fetched = self._fetch(task, src)
        manifest = {
            "worker_run_id": worker_run_id,
            "task_id": task["task_id"],
            "commit_sha": fetched.commit_sha,
            "snapshot_sha256": fetched.snapshot_sha256,
            "fetcher": fetched.fetcher,
            "runtime": {
                "name": self.runtime.name,
                "isolation": self.runtime.isolation,
                "network_policy": self.runtime.network_policy,
            },
            "python": platform.python_version(),
            "platform": platform.platform(),
            "engines": sorted(ENGINES),
            "repository_code_execution_allowed": self.allow_code_execution,
            "browser_testing": playwright_status()[1],
            "local_targets_allowed": bool(self.engine_settings.get("allow_local_targets")),
        }
        ev = sink.put(
            kind="environment_manifest",
            label="Environment manifest",
            media_type="application/json",
            content=json.dumps(manifest, indent=1).encode(),
        )
        t1 = datetime.now(UTC)
        log_text = (
            f"fetched {fetched.commit_sha} via {fetched.fetcher}: {fetched.file_count} files, "
            f"{fetched.total_bytes} bytes\nsnapshot sha256 {fetched.snapshot_sha256}\n"
        )
        log_id = sink.put(
            kind="log", label="env_prepare log", media_type="text/plain", content=log_text.encode()
        )
        duration = int((t1 - t0).total_seconds() * 1000)
        check = {
            "engine_id": "env_prepare",
            "name": "Fetch pinned snapshot",
            "outcome": PASSED,
            "started_at": _iso(t0),
            "ended_at": _iso(t1),
            "duration_ms": duration,
            "failure_message": None,
            "summary": {
                "commit_sha": fetched.commit_sha,
                "snapshot_sha256": fetched.snapshot_sha256,
                "file_count": fetched.file_count,
                "total_bytes": fetched.total_bytes,
                "fetcher": fetched.fetcher,
            },
            "tool_name": f"qaswarm_exec.{fetched.fetcher}",
            "tool_version": __version__,
            "executes_repository_code": False,
            "log_evidence_id": log_id,
            "evidence_ids": [ev, log_id],
        }
        wr = build_worker_result(
            task_id=task["task_id"],
            attempt_no=int(task["attempt_no"]),
            worker_run_id=worker_run_id,
            exit_code=0,
            duration_ms=duration,
            tool_name="qaswarm_exec.fetch",
            tool_version=__version__,
            image_digest=self.image_digest,
            summary={"executed": 1, "passed": 1},
            results_ref=ev,
            evidence_refs=sink.ids,
            truncated=False,
            redactions_applied=sink.redactions,
            output_bytes=len(log_text),
        )
        return {
            "worker_id": self.worker_id,
            "worker_result": wr,
            "snapshot_sha256": fetched.snapshot_sha256,
            "check_runs": [check],
            "test_executions": [],
        }

    def _check(
        self,
        task: dict[str, Any],
        ws: Workspace,
        sink: _Sink,
        worker_run_id: str,
        limits: RunLimits,
        cancel: threading.Event,
    ) -> dict[str, Any]:
        engine_id = str(task["inputs"].get("engine", ""))
        engine = get_engine(engine_id)
        t0 = datetime.now(UTC)
        fetched = self._fetch(task, ws.src)
        expected = task.get("context", {}).get("snapshot_sha256")
        ctx = CheckContext(
            task=task,
            workspace=ws.src,
            out_dir=ws.out,
            runtime=self.runtime,
            limits=limits,
            evidence=sink,
            allow_code_execution=self.allow_code_execution,
            cancel=cancel,
            snapshot_sha256=expected or fetched.snapshot_sha256,
            settings=self.engine_settings,
        )
        if engine.executes_repository_code and not self.allow_code_execution:
            result = CheckResult(
                SKIPPED,
                "Engine executes repository code and no sandbox runtime is available; refused. "
                "Set AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true on a trusted dev host to allow it.",
                {"refused": True},
            )
        else:
            try:
                result = engine.run(ctx)
            except TimeoutError:
                raise
            except Exception as exc:  # engine bug or tool crash → error outcome, never "passed"
                log.exception("engine crashed", extra={"engine": engine_id})
                result = CheckResult(ERROR, f"{type(exc).__name__}: {exc}", {}, exit_code=None)
        t1 = datetime.now(UTC)
        log_id = sink.put(
            kind="log",
            label=f"{engine_id} log",
            media_type="text/plain",
            content=(result.log or "").encode("utf-8", errors="replace"),
        )
        evidence_ids = [*result.evidence_ids, log_id]
        duration = int((t1 - t0).total_seconds() * 1000)
        check = {
            "engine_id": engine_id,
            "name": engine.display_name,
            "outcome": result.outcome,
            "started_at": _iso(t0),
            "ended_at": _iso(t1),
            "duration_ms": duration,
            "failure_message": result.message,
            "summary": result.summary,
            "tool_name": engine_id,
            "tool_version": engine.tool_version(),
            "executes_repository_code": engine.executes_repository_code,
            "log_evidence_id": log_id,
            "evidence_ids": evidence_ids,
        }
        tests = [
            {
                "node_id": t.node_id,
                "file": t.file,
                "name": t.name,
                "status": t.status,
                "duration_ms": t.duration_ms,
                "message": t.message,
            }
            for t in result.tests
        ]
        if tests:
            summary = {
                "executed": len(tests),
                "passed": sum(t.status == "passed" for t in result.tests),
                "failed": sum(t.status == "failed" for t in result.tests),
                "skipped": sum(t.status == "skipped" for t in result.tests),
                "errors": sum(
                    t.status in ("infrastructure_error", "timed_out", "blocked")
                    for t in result.tests
                ),
            }
        else:
            key = {PASSED: "passed", "failed": "failed", SKIPPED: "skipped", ERROR: "errors"}[
                result.outcome
            ]
            summary = {"executed": 1, key: 1}
        wr = build_worker_result(
            task_id=task["task_id"],
            attempt_no=int(task["attempt_no"]),
            worker_run_id=worker_run_id,
            exit_code=result.exit_code,
            duration_ms=duration,
            tool_name=engine_id,
            tool_version=engine.tool_version(),
            image_digest=self.image_digest,
            summary=summary,
            results_ref=log_id,
            evidence_refs=sink.ids,
            truncated=bool(result.summary.get("truncated_output", False)),
            redactions_applied=sink.redactions,
            output_bytes=len(result.log or ""),
        )
        return {
            "worker_id": self.worker_id,
            "worker_result": wr,
            "check_runs": [check],
            "test_executions": tests,
        }
