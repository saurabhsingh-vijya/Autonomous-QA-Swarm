from __future__ import annotations

import shutil
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path
from types import TracebackType
from typing import Protocol


class RuntimeUnavailable(Exception):
    """The requested runtime cannot run on this host (for example no Docker/gVisor)."""


@dataclass(frozen=True)
class ProcessResult:
    exit_code: int | None
    timed_out: bool
    cancelled: bool
    duration_ms: int
    output_path: Path
    output_bytes: int
    truncated: bool
    killed_reason: str | None = None


@dataclass(frozen=True)
class RunLimits:
    timeout_seconds: int = 1800
    output_cap_bytes: int = 50 * 1024 * 1024
    env: dict[str, str] = field(default_factory=dict)


class Runtime(Protocol):
    name: str
    isolation: str
    network_policy: str

    def available(self) -> bool: ...

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        limits: RunLimits,
        output_path: Path,
        cancel: threading.Event | None = None,
    ) -> ProcessResult: ...


class Workspace:
    """Disposable per-task directory. Always removed on exit, even after errors."""

    def __init__(self, root: str | Path, prefix: str = "aqs-task-") -> None:
        self.root = Path(root)
        self.prefix = prefix
        self.path: Path = self.root

    def __enter__(self) -> Workspace:
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = Path(tempfile.mkdtemp(prefix=self.prefix, dir=self.root))
        (self.path / "src").mkdir()
        (self.path / "out").mkdir()
        return self

    @property
    def src(self) -> Path:
        return self.path / "src"

    @property
    def out(self) -> Path:
        return self.path / "out"

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        shutil.rmtree(self.path, ignore_errors=True)
