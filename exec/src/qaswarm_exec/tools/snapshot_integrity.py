"""Verify the fetched snapshot matches the digest recorded at Environment Preparation."""

from __future__ import annotations

import json

from qaswarm_exec import __version__
from qaswarm_exec.host.source import iter_files, snapshot_digest
from qaswarm_exec.tools.base import FAILED, PASSED, CheckContext, CheckResult


class SnapshotIntegrityEngine:
    engine_id = "snapshot_integrity"
    display_name = "Snapshot integrity (SHA-256 of the pinned source)"
    executes_repository_code = False

    def tool_version(self) -> str:
        return f"qaswarm_exec {__version__}"

    def run(self, ctx: CheckContext) -> CheckResult:
        digest, count, total = snapshot_digest(ctx.workspace)
        inventory = [
            {"path": p.relative_to(ctx.workspace).as_posix(), "bytes": p.stat().st_size}
            for p in iter_files(ctx.workspace)
        ]
        inv_id = ctx.evidence.put(
            kind="source_inventory",
            label="Source inventory",
            media_type="application/json",
            content=json.dumps({"snapshot_sha256": digest, "files": inventory}, indent=1).encode(),
        )
        summary = {
            "snapshot_sha256": digest,
            "expected_sha256": ctx.snapshot_sha256,
            "file_count": count,
            "total_bytes": total,
        }
        if ctx.snapshot_sha256 and ctx.snapshot_sha256 != digest:
            return CheckResult(
                FAILED,
                "Snapshot digest differs from the one recorded at Environment Preparation.",
                summary,
                log=f"expected {ctx.snapshot_sha256}\nactual   {digest}\n",
                evidence_ids=[inv_id],
            )
        return CheckResult(
            PASSED,
            None,
            summary,
            log=f"snapshot sha256 {digest}\n{count} files, {total} bytes\n",
            evidence_ids=[inv_id],
        )
