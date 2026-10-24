"""Docker/gVisor runtime placeholder (BUILD_PLAN slice 1c).

The sandbox the design requires (rootless container, gVisor, caps dropped, read-only root FS,
network off during execution) is not implemented in this build. This class exists so the worker
can select a runtime by name and report honestly that it is unavailable.
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from qaswarm_exec.runtime.base import ProcessResult, RunLimits, RuntimeUnavailable


class DockerRuntime:
    name = "docker"
    isolation = "gvisor"
    network_policy = "none"

    def available(self) -> bool:
        return False  # even with a docker binary present, the sandbox driver is not built yet

    def run(
        self,
        argv: list[str],
        *,
        cwd: Path,
        limits: RunLimits,
        output_path: Path,
        cancel: threading.Event | None = None,
    ) -> ProcessResult:
        docker = shutil.which("docker")
        raise RuntimeUnavailable(
            "Docker/gVisor sandbox runtime is not implemented in this build"
            + ("" if docker else " and no docker binary was found")
        )
