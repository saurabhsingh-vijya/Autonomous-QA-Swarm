"""AG-08 Evidence Analysis Agent (deterministic correlator).

Groups failures by fingerprint, scores each group with the Defect Confidence Score rules that
apply to single-run evidence, and separates verified facts (observed status, evidence ids) from
inferred notes (possible causes, clearly labelled as inference). Three signal sources:

- API checks run by AG-04 (``status:<observed>!=<expected>`` on a method + URL);
- test executions reported by the Execution Service (pytest) — one finding per failing test
  signature per file, line numbers stripped;
- failed check runs of the deterministic engines (``python_syntax``, ``secret_scan``,
  ``snapshot_integrity``), located by file path without line numbers.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

from pydantic import Field

from qaswarm.agents.base import AgentContext, AgentOutputModel, AgentResult, AgentTaskInput
from qaswarm.defects.intelligence import root_cause_hypotheses
from qaswarm.domain.enums import AgentKind


class FindingDraft(AgentOutputModel):
    fingerprint: str
    category: str
    title: str
    severity: Literal["critical", "high", "medium", "low", "informational"]
    confidence: Literal["confirmed", "probable", "candidate"]
    dcs: int
    dcs_breakdown: dict[str, int]
    location: dict[str, Any]
    occurrences: int
    facts: list[str]
    inferred: list[str] = Field(default_factory=list)
    execution_refs: list[str]
    evidence_refs: list[str] = Field(default_factory=list)
    description: str = ""
    affected_tests: list[dict[str, Any]] = Field(default_factory=list)
    reproducibility: dict[str, Any] = Field(default_factory=dict)
    root_causes: list[dict[str, Any]] = Field(default_factory=list)


class EvidenceOutput(AgentOutputModel):
    findings: list[FindingDraft]
    executions_considered: int
    not_executed: dict[str, int]


def _fingerprint(category: str, location: str, signature: str, rule: str = "") -> str:
    return hashlib.sha256(f"{category}|{location}|{signature}|{rule}".encode()).hexdigest()


_LINE_RE = re.compile(r":\d+(?::\d+)?")
_DIGITS_RE = re.compile(r"\d+")


def _strip_lines(text: str) -> str:
    return _LINE_RE.sub("", text)


def _signature(message: str | None) -> str:
    first = (message or "").strip().splitlines()[0] if (message or "").strip() else "failure"
    return _DIGITS_RE.sub("N", _strip_lines(first))[:160]


_ENGINE_CATEGORY = {
    "python_syntax": ("code.syntax", "high"),
    "secret_scan": ("security.secret", "high"),
    "snapshot_integrity": ("integrity.snapshot", "high"),
    "pytest": ("test.suite", "medium"),
    "env_prepare": ("infrastructure.environment", "medium"),
}


def _check_location(engine: str, message: str | None) -> tuple[str, str]:
    """(location, rule) for a failed check: file path without line numbers, rule id if any."""
    text = (message or "").strip()
    if engine == "secret_scan":
        # "aws-access-key-id in config/settings_example.py:8"
        m = re.match(r"([\w.-]+) in (\S+?)(?::\d+)?$", text.splitlines()[0] if text else "")
        if m:
            return m.group(2), m.group(1)
    m = re.search(r"([\w./\\-]+\.[a-zA-Z0-9]+)(?::\d+)", text)
    if m:
        return m.group(1), ""
    return engine, ""


def _check_hypotheses(
    engine: str, message: str | None, evidence: list[str]
) -> list[dict[str, Any]]:
    base = {"supporting_evidence": evidence, "source": "deterministic rule", "verified": False}
    if engine == "python_syntax":
        return [
            {
                **base,
                "hypothesis": "The file does not parse under Python 3.12: an unfinished edit, a "
                "merge leftover, or syntax that targets another Python version.",
                "basis": "python_syntax reported a parse error with a file and line",
                "uncertainty": "low",
            }
        ]
    if engine == "secret_scan":
        return [
            {
                **base,
                "hypothesis": "A credential-shaped string is committed. It may be a sample or "
                "fixture value, but it must be treated as exposed until confirmed and rotated.",
                "basis": "secret_scan rule matched; the value is stored masked",
                "uncertainty": "medium",
            }
        ]
    if engine == "snapshot_integrity":
        return [
            {
                **base,
                "hypothesis": "The fetched tree differs from the pinned commit: a non-deterministic "
                "fetch, a changed ref, or an archive that is not reproducible.",
                "basis": "snapshot digest mismatch",
                "uncertainty": "medium",
            }
        ]
    return [
        {
            **base,
            "hypothesis": f"Check engine {engine} failed; see its log evidence.",
            "basis": "engine outcome failed",
            "uncertainty": "high",
        }
    ]


def _test_hypotheses(message: str | None, evidence: list[str]) -> list[dict[str, Any]]:
    base = {"supporting_evidence": evidence, "source": "deterministic rule", "verified": False}
    text = (message or "").lower()
    if "assert" in text:
        return [
            {
                **base,
                "hypothesis": "The implementation returns a different value than the test expects "
                "(logic, rounding or boundary difference).",
                "basis": "assertion failure in the test message",
                "uncertainty": "medium",
            }
        ]
    if "importerror" in text or "modulenotfound" in text:
        return [
            {
                **base,
                "hypothesis": "A dependency or module is missing from the execution environment.",
                "basis": "import error in the test message",
                "uncertainty": "low",
            }
        ]
    if "timeout" in text or "timed out" in text:
        return [
            {
                **base,
                "hypothesis": "The test waits on something that never completes in the sandbox.",
                "basis": "timeout in the test message",
                "uncertainty": "medium",
            }
        ]
    return [
        {
            **base,
            "hypothesis": "The test fails for a reason not classified by rule; read the failure "
            "message and the run log.",
            "basis": "test status failed",
            "uncertainty": "high",
        }
    ]


class EvidenceAnalysisAgent:
    @staticmethod
    def _non_api_finding(
        fp: str, g: dict[str, Any], evidence_by_id: dict[str, dict[str, Any]]
    ) -> FindingDraft:
        is_check = g["kind"] == "check"
        category = g["category"] if is_check else "test.failure"
        severity: Literal["critical", "high", "medium", "low", "informational"] = (
            g["severity"] if is_check else "medium"
        )
        occurrences = len(g["check_refs"]) if is_check else len(g["execution_refs"])
        message = str(g.get("message") or "").strip()
        first_line = message.splitlines()[0] if message else "no failure message recorded"
        breakdown = {
            "reproducibility": 15,
            "deterministic_oracle": 25,
            "evidence_completeness": 15 if g["evidence_refs"] else 9,
            "independent_corroboration": 0,
            "stability_history": 8,
        }
        dcs = sum(breakdown.values())
        if is_check:
            facts = [
                f"Check engine {g['engine']} reported failed: {first_line}.",
                f"Observed in {occurrences} check run(s) of this job; not yet reproduced in a fresh run.",
            ]
            hyps = _check_hypotheses(g["engine"], message, list(g["evidence_refs"]))
            title = f"{g['engine']} failed at {g['location']['file']}"
            description = (
                f"The deterministic check engine {g['engine']} failed on "
                f"{g['location']['file']}: {first_line}. The run log is linked as evidence; "
                "the check run remains listed under its own record."
            )
            tests: list[dict[str, Any]] = []
        else:
            facts = [
                f"Test {g['location']['node_id']} failed: {first_line}.",
                f"Observed in {occurrences} execution(s) of this job; not yet reproduced in a fresh run.",
            ]
            hyps = _test_hypotheses(message, list(g["evidence_refs"]))
            title = f"{g['location']['node_id']}: {first_line[:120]}"
            description = (
                f"Test {g['location']['node_id']} failed in {g['location']['file'] or 'the suite'}: "
                f"{first_line}. Every execution stays listed under affected_tests."
            )
            tests = g["tests"]
        return FindingDraft(
            fingerprint=fp,
            category=category,
            description=description,
            affected_tests=tests,
            reproducibility={
                "attempted": False,
                "runs": 0,
                "reproduced": 0,
                "fresh_workers": False,
                "note": "Not reproduced: fresh-sandbox reproduction runs arrive in slice 2b.",
            },
            root_causes=hyps,
            title=title[:300],
            severity=severity,
            confidence="probable" if dcs >= 50 else "candidate",
            dcs=dcs,
            dcs_breakdown=breakdown,
            location=g["location"],
            occurrences=occurrences,
            facts=facts,
            inferred=[f"Inference: {h['hypothesis']}" for h in hyps[:1]],
            execution_refs=list(g["execution_refs"]),
            evidence_refs=list(g["evidence_refs"]),
        )

    agent_id = "AG-08"
    name = "Evidence Analysis Agent"
    kind = AgentKind.DETERMINISTIC
    task_types = ("evidence.correlate",)
    output_model = EvidenceOutput

    def run(self, task: AgentTaskInput, ctx: AgentContext) -> AgentResult:
        executions: list[dict[str, Any]] = list(task.upstream.get("executions", []))
        evidence_by_id: dict[str, dict[str, Any]] = {
            str(e.get("id")): e for e in task.upstream.get("evidence", []) if e.get("id")
        }
        groups: dict[str, dict[str, Any]] = {}
        not_executed = {"skipped": 0, "blocked": 0, "timed_out": 0, "infrastructure_error": 0}
        check_runs: list[dict[str, Any]] = list(task.upstream.get("check_runs", []))
        check_log = {
            str(c.get("id")): [
                e for e in [c.get("log_evidence_id"), *list(c.get("evidence_ids", []))] if e
            ]
            for c in check_runs
        }
        for ex in executions:
            status = ex.get("status")
            if status in not_executed:
                not_executed[status] += 1
                continue
            if status != "failed":
                continue
            meta = ex.get("meta", {}) or {}
            if ex.get("test_type") == "api" or meta.get("method"):
                method, url = meta.get("method", ""), meta.get("url", "")
                observed, expected = meta.get("observed_status"), meta.get("expected_status")
                location = f"{method} {url}"
                signature = f"status:{observed}!={expected}"
                fp = _fingerprint("api.contract", location, signature)
                g = groups.setdefault(
                    fp,
                    {
                        "kind": "api",
                        "location": {"method": method, "url": url},
                        "observed": observed,
                        "expected": expected,
                        "execution_refs": [],
                        "evidence_refs": [],
                        "name": ex.get("name", location),
                        "tests": [],
                    },
                )
            else:
                file = str(ex.get("file") or "")
                node = str(ex.get("node_id") or ex.get("name") or "")
                location = _strip_lines(file or node.split("::")[0])
                signature = _signature(ex.get("message"))
                fp = _fingerprint("test.failure", location, signature)
                g = groups.setdefault(
                    fp,
                    {
                        "kind": "test",
                        "location": {"file": location, "node_id": node},
                        "message": ex.get("message"),
                        "execution_refs": [],
                        "evidence_refs": list(check_log.get(str(ex.get("check_run_id")), [])),
                        "name": node or ex.get("name", "test"),
                        "tests": [],
                    },
                )
            g["execution_refs"].append(ex["id"])
            g["tests"].append(
                {
                    "execution_id": ex["id"],
                    "name": ex.get("name", location),
                    "scenario_id": ex.get("scenario_id"),
                    "status": status,
                    "test_type": ex.get("test_type", "api"),
                }
            )
            if ex.get("evidence_id"):
                g["evidence_refs"].append(ex["evidence_id"])

        for c in check_runs:
            outcome = c.get("outcome")
            if outcome == "error":
                not_executed["infrastructure_error"] += 1
                continue
            if outcome != "failed" or c.get("engine") == "pytest":
                continue  # pytest failures are represented by their test executions
            engine = str(c.get("engine", ""))
            location, rule = _check_location(engine, c.get("failure_message"))
            category, check_severity = _ENGINE_CATEGORY.get(engine, ("check.failure", "medium"))
            signature = _signature(c.get("failure_message")) if not rule else f"rule:{rule}"
            fp = _fingerprint(category, location, signature, rule)
            g = groups.setdefault(
                fp,
                {
                    "kind": "check",
                    "engine": engine,
                    "category": category,
                    "severity": check_severity,
                    "location": {"file": location, "engine": engine, "rule": rule or None},
                    "message": c.get("failure_message"),
                    "execution_refs": [],
                    "check_refs": [],
                    "evidence_refs": [],
                    "name": f"{engine}: {location}",
                    "tests": [],
                },
            )
            g["check_refs"].append(c["id"])
            g["evidence_refs"] += [
                e for e in check_log.get(str(c["id"]), []) if e not in g["evidence_refs"]
            ]

        findings: list[FindingDraft] = []
        for fp, g in groups.items():
            if g.get("kind") in ("test", "check"):
                findings.append(self._non_api_finding(fp, g, evidence_by_id))
                continue
            observed = g["observed"]
            if isinstance(observed, int) and observed >= 500:
                severity = "high"
            elif observed in (401, 403):
                severity = "medium"
            else:
                severity = "medium"
            # Single deterministic run, no reproduction yet: oracle 25, completeness 15 (request,
            # response, expected, environment present), corroboration 0, stability 8 (new check),
            # reproducibility 15 (single run, no attempt yet). Total 63 → Probable.
            breakdown = {
                "reproducibility": 15,
                "deterministic_oracle": 25,
                "evidence_completeness": 15 if g["evidence_refs"] else 9,
                "independent_corroboration": 0,
                "stability_history": 8,
            }
            dcs = sum(breakdown.values())
            inferred: list[str] = []
            if isinstance(observed, int) and observed >= 500:
                inferred.append(
                    "Inference: a 5xx usually indicates an unhandled server error; confirm with server logs."
                )
            elif observed in (401, 403):
                inferred.append(
                    "Inference: the target may require credentials the check did not send."
                )
            elif observed == 404:
                inferred.append(
                    "Inference: the route may be missing or the path differs from the contract."
                )
            linked_evidence = [evidence_by_id[i] for i in g["evidence_refs"] if i in evidence_by_id]
            hypotheses = root_cause_hypotheses(
                observed if isinstance(observed, int) else None,
                g["expected"] if isinstance(g["expected"], int) else None,
                linked_evidence,
            )
            description = (
                f"{g['location'].get('method')} {g['location'].get('url')} returned HTTP {observed} "
                f"while the contract expects {g['expected']}. Observed in "
                f"{len(g['execution_refs'])} execution(s) of this job with "
                f"{len(g['evidence_refs'])} captured HTTP exchange(s). Each execution remains "
                "listed under affected_tests; grouping does not discard any result."
            )
            findings.append(
                FindingDraft(
                    fingerprint=fp,
                    category="api.contract",
                    description=description,
                    affected_tests=g["tests"],
                    reproducibility={
                        "attempted": False,
                        "runs": 0,
                        "reproduced": 0,
                        "fresh_workers": False,
                        "note": "Not reproduced: fresh-sandbox reproduction runs arrive in slice 2b. "
                        "Recorded inputs (method, URL, expected status) allow a manual replay.",
                    },
                    root_causes=hypotheses,
                    title=f"{g['name']}: expected HTTP {g['expected']}, observed {observed}",
                    severity=severity,
                    confidence="probable" if dcs >= 50 else "candidate",
                    dcs=dcs,
                    dcs_breakdown=breakdown,
                    location=g["location"],
                    occurrences=len(g["execution_refs"]),
                    facts=[
                        f"Observed HTTP {observed} where {g['expected']} was expected.",
                        f"Observed in {len(g['execution_refs'])} execution(s) of this job; "
                        "not yet reproduced in a fresh run.",
                    ],
                    inferred=inferred,
                    execution_refs=g["execution_refs"],
                    evidence_refs=g["evidence_refs"],
                )
            )
        payload = EvidenceOutput(
            findings=findings,
            executions_considered=len(executions) + len(check_runs),
            not_executed=not_executed,
        ).model_dump(mode="json")
        return AgentResult(
            schema_name="evidence_correlation",
            schema_version="1.0",
            payload=payload,
            adapter="deterministic",
            agent_kind=AgentKind.DETERMINISTIC,
        )
