from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from qaswarm_exec.runtime.base import RunLimits, Runtime

# Outcome vocabulary for a check (phase prompt): passed | failed | skipped | error.
PASSED = "passed"
FAILED = "failed"
SKIPPED = "skipped"
ERROR = "error"

# Design test statuses (TestExecutionStatus).
TEST_STATUSES = ("passed", "failed", "skipped", "blocked", "timed_out", "infrastructure_error")


class EvidenceSink(Protocol):
    def put(
        self, *, kind: str, label: str, media_type: str, content: bytes, deterministic: bool = True
    ) -> str:
        """Store evidence and return its id."""
        ...


@dataclass(frozen=True)
class TestResult:
    node_id: str
    name: str
    status: str
    duration_ms: int = 0
    file: str | None = None
    message: str | None = None


@dataclass
class CheckResult:
    outcome: str
    message: str | None = None
    summary: dict[str, Any] = field(default_factory=dict)
    log: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    tests: list[TestResult] = field(default_factory=list)
    exit_code: int | None = 0


@dataclass
class CheckContext:
    task: dict[str, Any]
    workspace: Path  # the extracted source snapshot
    out_dir: Path  # scratch for tool output files
    runtime: Runtime
    limits: RunLimits
    evidence: EvidenceSink
    allow_code_execution: bool
    cancel: threading.Event
    snapshot_sha256: str | None = None
    # Worker-level settings the engines may consult (phase 4): ``fixtures_dir``,
    # ``allow_local_targets``, ``perf_max_requests``, ``perf_max_concurrency``,
    # ``perf_max_duration_seconds``. Never secrets.
    settings: dict[str, Any] = field(default_factory=dict)


class CheckEngine(Protocol):
    engine_id: str
    display_name: str
    executes_repository_code: bool

    def tool_version(self) -> str: ...

    def run(self, ctx: CheckContext) -> CheckResult: ...
