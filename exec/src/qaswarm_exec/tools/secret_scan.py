"""Pattern-based secret detection. Evidence stores masked matches only (SEC-008, FR-024)."""

from __future__ import annotations

import hashlib
import json
import re

from qaswarm_exec import __version__
from qaswarm_exec.host.source import iter_files
from qaswarm_exec.tools.base import FAILED, PASSED, SKIPPED, CheckContext, CheckResult

RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "high"),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "high"),
    ("gitlab-token", re.compile(r"\bglpat-[A-Za-z0-9_\-]{20,}\b"), "high"),
    ("slack-token", re.compile(r"\bxox[abprs]-[A-Za-z0-9\-]{10,}\b"), "high"),
    (
        "private-key-block",
        re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA )?PRIVATE KEY-----"),
        "high",
    ),
    ("anthropic-api-key", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}\b"), "high"),
    (
        "jwt",
        re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\b"),
        "medium",
    ),
    (
        "password-assignment",
        re.compile(r"(?i)\b(?:password|passwd|secret)\s*[:=]\s*[\"'][^\"'\s]{8,}[\"']"),
        "medium",
    ),
]
MAX_FILE_BYTES = 1024 * 1024
TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".env",
    ".txt",
    ".md",
    ".sh",
    ".ps1",
    ".xml",
    ".properties",
    ".conf",
    ".pem",
    ".key",
    ".example",
    "",
}


def mask(value: str) -> str:
    return value[:4] + "****" + f"(sha256:{hashlib.sha256(value.encode()).hexdigest()[:8]})"


class SecretScanEngine:
    engine_id = "secret_scan"
    display_name = "Secret detection (pattern scan, masked evidence)"
    executes_repository_code = False

    def tool_version(self) -> str:
        return f"qaswarm_exec {__version__} rules={len(RULES)}"

    def run(self, ctx: CheckContext) -> CheckResult:
        scanned = 0
        findings: list[dict[str, object]] = []
        for path in iter_files(ctx.workspace):
            if path.suffix.lower() not in TEXT_SUFFIXES or path.stat().st_size > MAX_FILE_BYTES:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="strict")
            except (UnicodeDecodeError, OSError):
                continue
            scanned += 1
            rel = path.relative_to(ctx.workspace).as_posix()
            for rule, pattern, severity in RULES:
                for m in pattern.finditer(text):
                    line = text.count("\n", 0, m.start()) + 1
                    findings.append(
                        {
                            "rule": rule,
                            "severity": severity,
                            "file": rel,
                            "line": line,
                            "match": mask(m.group(0)),
                        }
                    )
        if scanned == 0:
            return CheckResult(SKIPPED, "No text files to scan.", {"files_scanned": 0})
        report_id = ctx.evidence.put(
            kind="scanner_report",
            label="Secret scan report (masked)",
            media_type="application/json",
            content=json.dumps({"files_scanned": scanned, "findings": findings}, indent=1).encode(),
        )
        high = [f for f in findings if f["severity"] == "high"]
        summary = {"files_scanned": scanned, "findings": len(findings), "high": len(high)}
        log = (
            "\n".join(f"{f['file']}:{f['line']} {f['rule']} {f['match']}" for f in findings) + "\n"
        )
        if findings:
            msg = f"{len(findings)} potential secret(s) found ({len(high)} high): " + ", ".join(
                f"{f['rule']} in {f['file']}:{f['line']}" for f in findings[:3]
            )
            return CheckResult(FAILED, msg, summary, log=log, evidence_ids=[report_id])
        return CheckResult(
            PASSED,
            None,
            summary,
            log=f"scanned {scanned} files, no matches\n",
            evidence_ids=[report_id],
        )
