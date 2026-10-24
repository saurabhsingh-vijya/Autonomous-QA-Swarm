"""Result normalisation: JUnit XML → test results, worker result envelope (LLD schema)."""

from qaswarm_exec.results.junit import parse_junit
from qaswarm_exec.results.worker_result import build_worker_result

__all__ = ["build_worker_result", "parse_junit"]
