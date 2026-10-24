"""Phase 5 defect intelligence rules without a database."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from qaswarm.agents.base import AgentContext, AgentTaskInput, validate_output
from qaswarm.agents.evidence import EvidenceAnalysisAgent
from qaswarm.defects.intelligence import (
    carry_over_status,
    risk_priority,
    root_cause_hypotheses,
    suggested_duplicates,
)
from qaswarm.defects.triage import _TRANSITIONS
from qaswarm.domain.enums import FindingStatus


def test_risk_priority_is_explainable_and_matches_design_examples() -> None:
    value, breakdown = risk_priority("critical", "confirmed", "external")
    assert value == 10.0 and breakdown["formula"].startswith("severity_weight")
    assert risk_priority("high", "probable", "external")[0] == 4.2
    assert risk_priority("medium", "candidate", "internal")[0] == 0.84
    assert risk_priority("medium", "rejected", "external")[0] == 0.0
    assert risk_priority("informational", "confirmed", "external")[0] == 0.0


def test_root_cause_hypotheses_cite_evidence_and_state_uncertainty() -> None:
    ev = [
        {
            "id": "evd_1",
            "content": {
                "response": {
                    "status": 404,
                    "headers": {"content-type": "text/html"},
                    "body_excerpt": "<h1>Not Found</h1>",
                }
            },
        }
    ]
    hyps = root_cause_hypotheses(404, 200, ev)
    assert len(hyps) == 2
    assert all(
        h["verified"] is False and h["uncertainty"] in ("low", "medium", "high") for h in hyps
    )
    assert all(h["supporting_evidence"] == ["evd_1"] for h in hyps)
    assert "static or proxy" in hyps[1]["hypothesis"]
    assert root_cause_hypotheses(None, 200, [])[0]["uncertainty"] == "high"
    assert "credentials" in root_cause_hypotheses(401, 200, [])[0]["hypothesis"]
    gw = root_cause_hypotheses(
        503, 200, [{"id": "e", "content": {"response": {"body_excerpt": "upstream timed out"}}}]
    )
    assert len(gw) == 3  # server error + timeout + gateway


def test_carry_over_status_applies_suppression_and_reopen_rules() -> None:
    assert carry_over_status({"prior_occurrences": []}) == ("candidate", None)
    recent = (datetime.now(UTC) - timedelta(days=10)).isoformat()
    old = (datetime.now(UTC) - timedelta(days=120)).isoformat()
    fp = {"display_id": "FND-0001", "status": "false_positive", "seen_at": recent}
    status, note = carry_over_status({"prior_occurrences": [fp]})
    assert status == "false_positive" and note and "Suppressed" in note
    assert carry_over_status({"prior_occurrences": [{**fp, "seen_at": old}]}) == ("candidate", None)
    fixed = {"display_id": "FND-0002", "status": "fix_verified", "seen_at": recent}
    assert carry_over_status({"prior_occurrences": [fixed]})[0] == "reopened"
    cand = {"display_id": "FND-0003", "status": "candidate", "seen_at": recent}
    assert carry_over_status({"prior_occurrences": [cand]}) == ("candidate", None)


def test_suggested_duplicates_require_same_location_and_high_similarity() -> None:
    out = suggested_duplicates(
        "status:500!=200 x y z w",
        "GET /a",
        [
            ("f1", "GET /a", "status:500!=200 x y z w"),  # identical signature: exact, not near
            ("f2", "GET /a", "status:500!=200 x y z v"),  # 5/6 tokens shared → 0.71, no
            ("f3", "GET /b", "status:500!=200 x y z w"),  # other location
            ("f4", "GET /a", "status:500!=200 x y z w extra"),  # 6/7 = 0.857, no
            ("f5", "GET /a", "status:500!=200 x y z w q r s t u v w1 w2 w3 w4 w5 w6"),
        ],
    )
    assert all(o["finding_id"] not in ("f1", "f2", "f3", "f4") for o in out)


def test_evidence_agent_produces_full_defect_record_without_discarding_executions() -> None:
    agent = EvidenceAnalysisAgent()
    execs = [
        {
            "id": "tex_1",
            "name": "GET /nope",
            "status": "failed",
            "evidence_id": "evd_1",
            "scenario_id": "SCN-API-001",
            "meta": {
                "method": "GET",
                "url": "http://localhost/nope",
                "expected_status": 200,
                "observed_status": 404,
            },
        },
        {
            "id": "tex_2",
            "name": "GET /nope",
            "status": "failed",
            "evidence_id": "evd_2",
            "scenario_id": "SCN-API-002",
            "meta": {
                "method": "GET",
                "url": "http://localhost/nope",
                "expected_status": 200,
                "observed_status": 404,
            },
        },
    ]
    evidence = [
        {
            "id": "evd_1",
            "content": {"response": {"status": 404, "headers": {}, "body_excerpt": "{}"}},
        },
        {
            "id": "evd_2",
            "content": {"response": {"status": 404, "headers": {}, "body_excerpt": "{}"}},
        },
    ]
    task = AgentTaskInput(
        job_id="job_x",
        org_id="org_x",
        task_id="tsk_x",
        task_type="evidence.correlate",
        stage="s",
        attempt_no=1,
        inputs={},
        upstream={"executions": execs, "evidence": evidence},
    )
    r = validate_output(agent, agent.run(task, AgentContext()))
    f = r.payload["findings"][0]
    assert f["occurrences"] == 2 and len(f["affected_tests"]) == 2
    assert {t["execution_id"] for t in f["affected_tests"]} == {"tex_1", "tex_2"}
    assert f["reproducibility"]["attempted"] is False and f["reproducibility"]["runs"] == 0
    assert f["root_causes"] and f["root_causes"][0]["supporting_evidence"] == ["evd_1", "evd_2"]
    assert "does not discard" in f["description"]
    assert f["dcs"] < 80  # recurrence or grouping never confirms anything


@pytest.mark.parametrize(
    ("action", "src", "dst"),
    [
        ("mark_false_positive", FindingStatus.CANDIDATE, FindingStatus.FALSE_POSITIVE),
        ("mark_duplicate", FindingStatus.CONFIRMED, FindingStatus.DUPLICATE),
        ("accept_risk", FindingStatus.REOPENED, FindingStatus.ACCEPTED_RISK),
        ("reopen", FindingStatus.FALSE_POSITIVE, FindingStatus.REOPENED),
        ("reopen", FindingStatus.FIX_VERIFIED, FindingStatus.REOPENED),
    ],
)
def test_triage_transition_table(action: str, src: FindingStatus, dst: FindingStatus) -> None:
    assert _TRANSITIONS[(action, src)] == dst


def test_triage_table_has_no_transition_from_rejected_to_rejected() -> None:
    assert ("mark_false_positive", FindingStatus.FALSE_POSITIVE) not in _TRANSITIONS
    assert ("reopen", FindingStatus.CANDIDATE) not in _TRANSITIONS
