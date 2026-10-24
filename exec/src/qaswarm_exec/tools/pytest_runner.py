"""Run the repository's pytest suite through the runtime and normalise JUnit XML.

This engine **executes repository code**. The worker refuses it unless the operator allowed
unsandboxed execution; the refusal is recorded as a ``skipped`` check with the reason.
Dependencies of the target repository are not installed (dependency-fetch phase is slice 1c);
collection errors therefore end the check as ``error`` with the log attached, never as "passed".
"""

from __future__ import annotations

import sys
from importlib import metadata
from pathlib import Path

from qaswarm_exec.results.junit import parse_junit
from qaswarm_exec.runtime.base import RuntimeUnavailable
from qaswarm_exec.tools.base import ERROR, FAILED, PASSED, SKIPPED, CheckContext, CheckResult

EXIT_OK, EXIT_TESTS_FAILED, EXIT_INTERRUPTED, EXIT_INTERNAL, EXIT_USAGE, EXIT_NO_TESTS = (
    0,
    1,
    2,
    3,
    4,
    5,
)


def _has_tests(root: Path) -> bool:
    for p in root.rglob("*.py"):
        name = p.name
        if name.startswith("test_") or name.endswith("_test.py"):
            return True
    return False


class PytestEngine:
    engine_id = "pytest"
    display_name = "pytest (existing test suite)"
    executes_repository_code = True

    def tool_version(self) -> str:
        try:
            return f"pytest {metadata.version('pytest')}"
        except metadata.PackageNotFoundError:
            return "pytest (not installed)"

    def run(self, ctx: CheckContext) -> CheckResult:
        if not _has_tests(ctx.workspace):
            return CheckResult(
                SKIPPED, "No pytest test files (test_*.py / *_test.py) found.", {"tests": 0}
            )
        junit = ctx.out_dir / "junit.xml"
        argv = [
            sys.executable,
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            "-o",
            "junit_family=xunit2",
            f"--junitxml={junit}",
            "--rootdir",
            str(ctx.workspace),
        ]
        try:
            proc = ctx.runtime.run(
                argv,
                cwd=ctx.workspace,
                limits=ctx.limits,
                output_path=ctx.out_dir / "pytest.log",
                cancel=ctx.cancel,
            )
        except RuntimeUnavailable as exc:
            return CheckResult(ERROR, f"runtime unavailable: {exc}", {}, exit_code=None)
        log = (
            proc.output_path.read_text(encoding="utf-8", errors="replace")
            if proc.output_path.exists()
            else ""
        )
        if proc.timed_out:
            raise TimeoutError("pytest exceeded the task wall clock")
        if proc.cancelled:
            return CheckResult(ERROR, "cancelled", {}, log=log, exit_code=proc.exit_code)
        tests = parse_junit(junit) if junit.exists() else []
        junit_id = None
        if junit.exists():
            junit_id = ctx.evidence.put(
                kind="junit_xml",
                label="pytest JUnit XML",
                media_type="application/xml",
                content=junit.read_bytes(),
            )
        counts = {
            s: sum(1 for t in tests if t.status == s) for s in ("passed", "failed", "skipped")
        }
        summary = {
            "exit_code": proc.exit_code,
            "tests": len(tests),
            **counts,
            "truncated_output": proc.truncated,
        }
        evidence = [junit_id] if junit_id else []
        if proc.exit_code == EXIT_OK:
            return CheckResult(
                PASSED,
                None,
                summary,
                log=log,
                evidence_ids=evidence,
                tests=tests,
                exit_code=proc.exit_code,
            )
        if proc.exit_code == EXIT_TESTS_FAILED:
            failing = [t.node_id for t in tests if t.status == "failed"][:3]
            msg = f"{counts['failed']} test(s) failed: " + ", ".join(failing)
            return CheckResult(
                FAILED,
                msg,
                summary,
                log=log,
                evidence_ids=evidence,
                tests=tests,
                exit_code=proc.exit_code,
            )
        if proc.exit_code == EXIT_NO_TESTS:
            return CheckResult(
                SKIPPED,
                "pytest collected no tests.",
                summary,
                log=log,
                evidence_ids=evidence,
                exit_code=proc.exit_code,
            )
        tail = "\n".join(log.strip().splitlines()[-5:])
        return CheckResult(
            ERROR,
            f"pytest exited {proc.exit_code} (collection/usage/internal error): {tail[:400]}",
            summary,
            log=log,
            evidence_ids=evidence,
            tests=tests,
            exit_code=proc.exit_code,
        )
