"""Parse every Python file with ``ast.parse``. Nothing is imported or executed."""

from __future__ import annotations

import ast
import json
import platform

from qaswarm_exec.host.source import iter_files
from qaswarm_exec.tools.base import FAILED, PASSED, SKIPPED, CheckContext, CheckResult

MAX_REPORTED = 50


class PythonSyntaxEngine:
    engine_id = "python_syntax"
    display_name = "Python syntax (ast.parse, no execution)"
    executes_repository_code = False

    def tool_version(self) -> str:
        return f"python {platform.python_version()} ast"

    def run(self, ctx: CheckContext) -> CheckResult:
        files = [p for p in iter_files(ctx.workspace) if p.suffix == ".py"]
        if not files:
            return CheckResult(SKIPPED, "No Python files in the snapshot.", {"files": 0})
        errors: list[dict[str, object]] = []
        log_lines: list[str] = []
        for path in files:
            rel = path.relative_to(ctx.workspace).as_posix()
            try:
                source = path.read_bytes()
                ast.parse(source, filename=rel)
            except SyntaxError as exc:
                errors.append(
                    {"file": rel, "line": exc.lineno, "column": exc.offset, "message": exc.msg}
                )
                log_lines.append(f"{rel}:{exc.lineno}:{exc.offset}: {exc.msg}")
            except (ValueError, RecursionError) as exc:  # null bytes, pathological nesting
                errors.append({"file": rel, "line": None, "column": None, "message": str(exc)})
                log_lines.append(f"{rel}: {exc}")
        report_id = ctx.evidence.put(
            kind="scanner_report",
            label="Python syntax report",
            media_type="application/json",
            content=json.dumps({"files": len(files), "errors": errors}, indent=1).encode(),
        )
        summary = {"files": len(files), "errors": len(errors)}
        if errors:
            first = errors[:MAX_REPORTED]
            msg = f"{len(errors)} file(s) failed to parse: " + "; ".join(
                f"{e['file']}:{e['line']} {e['message']}" for e in first[:3]
            )
            return CheckResult(
                FAILED, msg, summary, log="\n".join(log_lines) + "\n", evidence_ids=[report_id]
            )
        return CheckResult(
            PASSED,
            None,
            summary,
            log=f"parsed {len(files)} Python files\n",
            evidence_ids=[report_id],
        )
