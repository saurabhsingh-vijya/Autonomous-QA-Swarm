"""AG-11 QA Reporting Agent (deterministic aggregator).

Builds the report from persisted execution records handed in as upstream data. Gate evaluation
is limited to what this build can measure: QG-01/QG-02 on findings, QG-03 on executed checks,
QG-04 coverage of planned scenarios, QG-08 infrastructure health. Other gates are reported as
``not_applicable`` or ``inconclusive`` with the reason, never as passed.
"""

from __future__ import annotations

from typing import Any

from pydantic import Field

from qaswarm.agents.base import AgentContext, AgentOutputModel, AgentResult, AgentTaskInput
from qaswarm.domain.enums import AgentKind


class GateResultModel(AgentOutputModel):
    gate_id: str
    result: str
    blocking: bool
    measured: dict[str, Any] = Field(default_factory=dict)
    threshold: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class ReportOutput(AgentOutputModel):
    verdict: str
    verdict_reason: str
    gates: list[GateResultModel]
    test_summary: dict[str, int]
    finding_summary: dict[str, int]
    findings_by_priority: list[dict[str, Any]] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    checks: list[dict[str, Any]] = Field(default_factory=list)
    coverage: dict[str, Any]
    residual_risk: list[str]
    agents: list[dict[str, Any]]
    narrative: str
    narrative_source: str


def _verdict(gates: list[GateResultModel], hard_blocker: bool) -> tuple[str, str]:
    if hard_blocker:
        return "NOT_READY", "An open Confirmed Critical or High security finding forces NOT_READY."
    failed = [g.gate_id for g in gates if g.result == "failed" and g.blocking]
    if failed:
        return "NOT_READY", f"Blocking gate(s) failed: {', '.join(failed)}."
    inconclusive = [g.gate_id for g in gates if g.result == "inconclusive"]
    if inconclusive:
        return "INCONCLUSIVE", f"Gate(s) could not be measured: {', '.join(inconclusive)}."
    advisory = [g.gate_id for g in gates if g.result == "advisory_failed"]
    if advisory:
        return "READY_WITH_RISKS", f"Advisory gate(s) failed: {', '.join(advisory)}."
    return (
        "READY",
        "No blocking or advisory gate failed and every gate was measured or not applicable.",
    )


class ReportingAgent:
    agent_id = "AG-11"
    name = "QA Reporting Agent"
    kind = AgentKind.DETERMINISTIC
    task_types = ("report.build",)
    output_model = ReportOutput

    def run(self, task: AgentTaskInput, ctx: AgentContext) -> AgentResult:
        up = task.upstream
        executions: list[dict[str, Any]] = list(up.get("executions", []))
        findings: list[dict[str, Any]] = list(up.get("findings", []))
        scenarios: list[dict[str, Any]] = list(up.get("scenarios", []))
        tasks: list[dict[str, Any]] = list(up.get("tasks", []))
        check_runs: list[dict[str, Any]] = list(up.get("check_runs", []))
        check_counts: dict[str, int] = {}
        for c in check_runs:
            check_counts[c["outcome"]] = check_counts.get(c["outcome"], 0) + 1
        task_counts: dict[str, int] = {}
        for t in tasks:
            task_counts[t["state"]] = task_counts.get(t["state"], 0) + 1

        counts = {
            k: 0
            for k in ("passed", "failed", "skipped", "blocked", "timed_out", "infrastructure_error")
        }
        for ex in executions:
            counts[ex["status"]] = counts.get(ex["status"], 0) + 1
        executed = counts["passed"] + counts["failed"]
        fsum: dict[str, int] = {}
        for f in findings:
            fsum[f["confidence"]] = fsum.get(f["confidence"], 0) + 1
        rejected_statuses = {"false_positive", "duplicate", "not_reproducible"}
        open_findings = [
            f for f in findings if f.get("status", "candidate") not in rejected_statuses
        ]
        excluded = [f for f in findings if f.get("status", "candidate") in rejected_statuses]
        accepted = [f for f in findings if f.get("status") == "accepted_risk"]
        recurring = [f for f in open_findings if f.get("recurring")]

        open_conf_crit = sum(
            1
            for f in open_findings
            if f["confidence"] == "confirmed" and f["severity"] == "critical"
        )
        open_conf_high_sec = sum(
            1
            for f in open_findings
            if f["confidence"] == "confirmed"
            and f["severity"] == "high"
            and str(f.get("category", "")).startswith("security")
        )
        gates: list[GateResultModel] = [
            GateResultModel(
                gate_id="QG-01",
                result="failed" if open_conf_crit else "passed",
                blocking=True,
                measured={"open_confirmed_critical": open_conf_crit},
                threshold={"max": 0},
            ),
            GateResultModel(
                gate_id="QG-02",
                result="failed" if open_conf_high_sec else "passed",
                blocking=True,
                measured={"open_confirmed_high_security": open_conf_high_sec},
                threshold={"max": 0},
            ),
        ]
        if executed:
            rate = counts["passed"] / executed
            gates.append(
                GateResultModel(
                    gate_id="QG-03",
                    result="passed" if rate >= 0.98 else "failed",
                    blocking=True,
                    measured={"pass_rate": round(rate, 4), "executed": executed},
                    threshold={"min_pass_rate": 0.98},
                )
            )
        else:
            gates.append(
                GateResultModel(
                    gate_id="QG-03",
                    result="inconclusive",
                    blocking=True,
                    measured={"executed": 0},
                    threshold={"min_pass_rate": 0.98},
                    note="No test was executed to a verdict in this job.",
                )
            )
        planned = {s["id"]: s for s in scenarios}
        exec_by_scn = {
            ex.get("scenario_id") for ex in executions if ex["status"] in ("passed", "failed")
        }
        p0 = [s for s in planned.values() if s["priority"] == "P0"]
        p1 = [s for s in planned.values() if s["priority"] == "P1"]
        if planned:
            p0_cov = (sum(1 for s in p0 if s["id"] in exec_by_scn) / len(p0)) if p0 else 1.0
            p1_cov = (sum(1 for s in p1 if s["id"] in exec_by_scn) / len(p1)) if p1 else 1.0
            ok = p0_cov >= 0.95 and p1_cov >= 0.85
            gates.append(
                GateResultModel(
                    gate_id="QG-04",
                    result="passed" if ok else "inconclusive",
                    blocking=True,
                    measured={"p0_executed": round(p0_cov, 3), "p1_executed": round(p1_cov, 3)},
                    threshold={"p0_min": 0.95, "p1_min": 0.85},
                    note=None
                    if ok
                    else "Planned scenarios were not executed (no execution engine or blocked checks).",
                )
            )
        else:
            gates.append(
                GateResultModel(
                    gate_id="QG-04",
                    result="inconclusive",
                    blocking=True,
                    note="No scenarios were planned.",
                )
            )
        for gid, slice_ in (("QG-05", "3b"), ("QG-06", "3c"), ("QG-07", "3d")):
            gates.append(
                GateResultModel(
                    gate_id=gid,
                    result="not_applicable",
                    blocking=gid != "QG-06",
                    note=f"Not measured in this build (arrives in slice {slice_}).",
                )
            )
        total_tasks = len(tasks)
        infra = sum(
            1
            for t in tasks
            if t["state"] == "timed_out"
            or (t["state"] == "failed" and t.get("error_class") == "infrastructure_error")
        )
        ratio = (infra / total_tasks) if total_tasks else 0.0
        gates.append(
            GateResultModel(
                gate_id="QG-08",
                result="passed" if ratio <= 0.05 else "inconclusive",
                blocking=True,
                measured={"infra_error_ratio": round(ratio, 4), "tasks": total_tasks},
                threshold={"max": 0.05},
            )
        )

        verdict, reason = _verdict(gates, hard_blocker=bool(open_conf_crit or open_conf_high_sec))
        residual = [
            "Functional scenarios from supplied requirements were not executed: no sandbox "
            "scenario engine in this build (slice 1c); repository test suites run through the "
            "Execution Service's pytest engine only when the host allows code execution.",
            "Findings rest on single-run evidence; reproduction in fresh sandboxes arrives in slice 2b.",
            "Security, performance and mutation checks did not run (slices 2a, 3b, 3c).",
        ]
        if excluded:
            residual.append(
                f"{len(excluded)} finding(s) excluded from gates by triage or suppression "
                f"({', '.join(sorted({f['status'] for f in excluded}))}); they remain visible."
            )
        if accepted:
            residual.append(
                f"{len(accepted)} finding(s) carried as accepted risk (HA-08) with an expiry."
            )
        if recurring:
            residual.append(
                f"{len(recurring)} finding(s) recur from earlier jobs on this repository and are "
                "still unresolved."
            )
        residual += [w for w in up.get("warnings", []) if w not in residual]
        narrative = (
            f"RaOne ran {len(check_runs)} repository check(s) "
            f"({check_counts.get('passed', 0)} passed, {check_counts.get('failed', 0)} failed, "
            f"{check_counts.get('skipped', 0)} skipped) and "
            f"{executed} test/API execution(s) ({counts['passed']} passed, {counts['failed']} failed), "
            f"recorded {counts['skipped']} skipped and {counts['blocked']} blocked scenario(s), and correlated "
            f"{len(findings)} finding(s). Verdict {verdict}: {reason}"
        )
        payload = ReportOutput(
            verdict=verdict,
            verdict_reason=reason,
            gates=gates,
            test_summary={**counts, "executed": executed},
            finding_summary={**fsum, "open": len(open_findings), "excluded": len(excluded)},
            findings_by_priority=[
                {
                    "id": f.get("id"),
                    "display_id": f.get("display_id"),
                    "title": f.get("title"),
                    "severity": f["severity"],
                    "confidence": f["confidence"],
                    "status": f.get("status", "candidate"),
                    "dcs": f.get("dcs"),
                    "risk_priority": f.get("risk_priority", 0.0),
                }
                for f in sorted(
                    findings,
                    key=lambda f: (-float(f.get("risk_priority", 0.0)), -int(f.get("dcs", 0))),
                )
            ],
            coverage={
                "planned_scenarios": len(planned),
                "p0": len(p0),
                "p1": len(p1),
                "executed_scenarios": len(exec_by_scn),
            },
            residual_risk=residual,
            agents=tasks,
            summary={"tasks": task_counts, "checks": check_counts, "tests": dict(counts)},
            checks=check_runs,
            narrative=narrative,
            narrative_source="deterministic template (no LLM narrative in this build)",
        ).model_dump(mode="json")
        return AgentResult(
            schema_name="qa_report",
            schema_version="1.0",
            payload=payload,
            adapter="deterministic",
            agent_kind=AgentKind.DETERMINISTIC,
        )
