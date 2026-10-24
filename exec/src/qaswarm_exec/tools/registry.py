from __future__ import annotations

from qaswarm_exec.tools.base import CheckEngine
from qaswarm_exec.tools.pytest_runner import PytestEngine
from qaswarm_exec.tools.python_syntax import PythonSyntaxEngine
from qaswarm_exec.tools.secret_scan import SecretScanEngine
from qaswarm_exec.tools.snapshot_integrity import SnapshotIntegrityEngine

ENGINES: dict[str, type[CheckEngine]] = {
    SnapshotIntegrityEngine.engine_id: SnapshotIntegrityEngine,
    PythonSyntaxEngine.engine_id: PythonSyntaxEngine,
    SecretScanEngine.engine_id: SecretScanEngine,
    PytestEngine.engine_id: PytestEngine,
}


class UnknownEngine(Exception):
    pass


def get_engine(engine_id: str) -> CheckEngine:
    try:
        return ENGINES[engine_id]()
    except KeyError as exc:
        raise UnknownEngine(engine_id) from exc
