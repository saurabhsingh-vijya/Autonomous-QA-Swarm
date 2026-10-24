from __future__ import annotations

from qaswarm_exec.tools.api_tests import ApiTestsEngine
from qaswarm_exec.tools.base import CheckEngine
from qaswarm_exec.tools.browser_tests import BrowserTestsEngine
from qaswarm_exec.tools.performance_probe import PerformanceProbeEngine
from qaswarm_exec.tools.pytest_runner import PytestEngine
from qaswarm_exec.tools.python_syntax import PythonSyntaxEngine
from qaswarm_exec.tools.secret_scan import SecretScanEngine
from qaswarm_exec.tools.security_checks import SecurityChecksEngine
from qaswarm_exec.tools.snapshot_integrity import SnapshotIntegrityEngine

ENGINES: dict[str, type[CheckEngine]] = {
    SnapshotIntegrityEngine.engine_id: SnapshotIntegrityEngine,
    PythonSyntaxEngine.engine_id: PythonSyntaxEngine,
    SecretScanEngine.engine_id: SecretScanEngine,
    PytestEngine.engine_id: PytestEngine,
    # Phase 4: target-facing engines (explicit, authorised targets only).
    ApiTestsEngine.engine_id: ApiTestsEngine,
    BrowserTestsEngine.engine_id: BrowserTestsEngine,
    SecurityChecksEngine.engine_id: SecurityChecksEngine,
    PerformanceProbeEngine.engine_id: PerformanceProbeEngine,
}
# Engines that need a ``target`` descriptor in the task inputs.
TARGET_ENGINES: frozenset[str] = frozenset(
    {"api_tests", "browser_tests", "security_checks", "performance_probe"}
)


class UnknownEngine(Exception):
    pass


def get_engine(engine_id: str) -> CheckEngine:
    try:
        return ENGINES[engine_id]()
    except KeyError as exc:
        raise UnknownEngine(engine_id) from exc
