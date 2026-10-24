"""Build the worker result envelope exactly as the LLD ``worker_result/1`` schema requires."""

from __future__ import annotations

from typing import Any


def build_worker_result(
    *,
    task_id: str,
    attempt_no: int,
    worker_run_id: str,
    exit_code: int | None,
    duration_ms: int,
    tool_name: str,
    tool_version: str,
    image_digest: str,
    summary: dict[str, int],
    results_ref: str,
    evidence_refs: list[str],
    truncated: bool,
    redactions_applied: int,
    output_bytes: int,
    cpu_seconds: float = 0.0,
    max_rss_mib: float = 0.0,
) -> dict[str, Any]:
    counters = {k: int(summary.get(k, 0)) for k in ("passed", "failed", "skipped", "errors")}
    executed = int(summary.get("executed", sum(counters.values())))
    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "attempt_no": attempt_no,
        "worker_run_id": worker_run_id[:40],
        "exit": {
            "code": int(exit_code if exit_code is not None else -1),
            "signal": None,
            "duration_ms": max(0, duration_ms),
        },
        "tool": {
            "name": tool_name[:80],
            "version": tool_version[:40],
            "image_digest": image_digest,
        },
        "summary": {"executed": executed, **counters},
        "results_ref": results_ref[:4096],
        "evidence_refs": evidence_refs[:1000],
        "truncated": truncated,
        "redactions_applied": redactions_applied,
        "resource_usage": {
            "cpu_seconds": max(0.0, cpu_seconds),
            "max_rss_mib": max(0.0, max_rss_mib),
            "output_bytes": min(max(0, output_bytes), 52428800),
        },
    }
