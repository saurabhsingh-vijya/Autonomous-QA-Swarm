"""AG-08 Evidence Analysis Agent (deterministic correlator).

Groups failed and errored checks by fingerprint, scores each group with the Defect Confidence
Score rules that apply to single-run evidence, and separates verified facts (observed status,
evidence ids) from inferred notes (possible causes, clearly labelled as inference).
"""

from __future__ import annotations

import hashlib
from typing import Any, Literal

from pydantic import Field

from qaswarm.agents.base import AgentContext, AgentOutputModel, AgentResult, AgentTaskInput
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


class EvidenceOutput(AgentOutputModel):
    findings: list[FindingDraft]
    executions_considered: int
    not_executed: dict[str, int]


def _fingerprint(category: str, location: str, signature: str) -> str:
    return hashlib.sha256(f"{category}|{location}|{signature}|".encode()).hexdigest()


class EvidenceAnalysisAgent:
    agent_id = "AG-08"
    name = "Evidence Analysis Agent"
    kind = AgentKind.DETERMINISTIC
    task_types = ("evidence.correlate",)
    output_model = EvidenceOutput

    def run(self, task: AgentTaskInput, ctx: AgentContext) -> AgentResult:
        executions: list[dict[str, Any]] = list(task.upstream.get("executions", []))
        groups: dict[str, dict[str, Any]] = {}
        not_executed = {"skipped": 0, "blocked": 0, "timed_out": 0, "infrastructure_error": 0}
        for ex in executions:
            status = ex.get("status")
            if status in not_executed:
                not_executed[status] += 1
                continue
            if status != "failed":
                continue
            meta = ex.get("meta", {})
            method, url = meta.get("method", ""), meta.get("url", "")
            observed, expected = meta.get("observed_status"), meta.get("expected_status")
            location = f"{method} {url}"
            signature = f"status:{observed}!={expected}"
            fp = _fingerprint("api.contract", location, signature)
            g = groups.setdefault(
                fp,
                {
                    "location": {"method": method, "url": url},
                    "observed": observed,
                    "expected": expected,
                    "execution_refs": [],
                    "evidence_refs": [],
                    "name": ex.get("name", location),
                },
            )
            g["execution_refs"].append(ex["id"])
            if ex.get("evidence_id"):
                g["evidence_refs"].append(ex["evidence_id"])

        findings: list[FindingDraft] = []
        for fp, g in groups.items():
            observed = g["observed"]
            severity: Literal["critical", "high", "medium", "low", "informational"]
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
            findings.append(
                FindingDraft(
                    fingerprint=fp,
                    category="api.contract",
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
            findings=findings, executions_considered=len(executions), not_executed=not_executed
        ).model_dump(mode="json")
        return AgentResult(
            schema_name="evidence_correlation",
            schema_version="1.0",
            payload=payload,
            adapter="deterministic",
            agent_kind=AgentKind.DETERMINISTIC,
        )
