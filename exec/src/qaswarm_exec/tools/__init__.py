"""Check engines behind one interface.

Import the registry explicitly (``qaswarm_exec.tools.registry``) to look engines up; this package
only re-exports the interface types so that engines and result parsers can import it freely.
"""

from qaswarm_exec.tools.base import (
    CheckContext,
    CheckEngine,
    CheckResult,
    EvidenceSink,
    TestResult,
)

__all__ = ["CheckContext", "CheckEngine", "CheckResult", "EvidenceSink", "TestResult"]
