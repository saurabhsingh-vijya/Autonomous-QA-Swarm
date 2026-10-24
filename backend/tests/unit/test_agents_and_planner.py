"""Agents, planner, policy and LLM adapter without a database."""

from __future__ import annotations

import json

import pytest

from qaswarm.agents.api_testing import ApiTestingAgent, HttpChecker
from qaswarm.agents.base import AgentContext, AgentFailure, AgentTaskInput, validate_output
from qaswarm.agents.evidence import EvidenceAnalysisAgent
from qaswarm.agents.functional import SKIP_REASON, FunctionalTestingAgent
from qaswarm.agents.llm import NoLLM, OllamaAdapter, parse_json_object
from qaswarm.agents.registry import AGENT_CATALOGUE, get_agent, registered_agents
from qaswarm.agents.reporting import ReportingAgent
from qaswarm.agents.requirements import RequirementsAnalysisAgent
from qaswarm.planning.planner import PlanNode, build_plan, plan_hash, validate_plan
from qaswarm.policy.local import evaluate_api_check


def _task(task_type: str, inputs: dict, upstream: dict | None = None) -> AgentTaskInput:  # type: ignore[type-arg]
    return AgentTaskInput(
        job_id="job_x",
        org_id="org_x",
        task_id="tsk_x",
        task_type=task_type,
        stage="s",
        attempt_no=1,
        inputs=inputs,
        upstream=upstream or {},
    )


def test_registry_has_six_real_roles_and_labels_kinds_honestly() -> None:
    ids = {a.agent_id for a in registered_agents()}
    assert ids == {"AG-02", "AG-03", "AG-04", "AG-08", "AG-11"}
    assert get_agent("api.check") is not None and get_agent("nope") is None
    implemented = [a for a in AGENT_CATALOGUE if a.implemented]
    assert {a.agent_id for a in implemented} == {
        "AG-01",
        "AG-02",
        "AG-03",
        "AG-04",
        "AG-08",
        "AG-11",
    }
    assert all(a.planned_slice for a in AGENT_CATALOGUE if not a.implemented)


def test_requirements_agent_is_deterministic_and_traceable() -> None:
    agent = RequirementsAnalysisAgent()
    task = _task(
        "requirements.analyze",
        {
            "requirements": [
                "The API must reject unauthorised access",
                "Reports should be exportable",
            ],
            "api_checks": [
                {"method": "GET", "url": "http://localhost:8000/healthz", "expected_status": 200}
            ],
        },
    )
    r1 = validate_output(agent, agent.run(task, AgentContext()))
    r2 = validate_output(agent, agent.run(task, AgentContext()))
    assert r1.payload == r2.payload and r1.adapter == "deterministic" and r1.model_ref is None
    scns = r1.payload["scenarios"]
    assert [s["priority"] for s in scns] == ["P0", "P1", "P1"]
    assert all(s["requirement_ref"] for s in scns) and scns[2]["test_type"] == "api"
    assert task.sha256() == _task("requirements.analyze", task.inputs).sha256()


def test_requirements_agent_drops_llm_proposals_without_a_requirement_ref() -> None:
    class FakeLLM:
        name = "fake-local"
        is_llm = True

        def complete_json(self, prompt: str, *, schema_hint: dict) -> tuple[dict, object]:  # type: ignore[type-arg]
            from qaswarm.agents.llm import Completion

            return (
                {
                    "scenarios": [
                        {"title": "ok", "requirement_ref": "REQ-001-" + "x" * 6, "priority": "P1"},
                        {"title": "bad", "requirement_ref": "REQ-999", "priority": "P1"},
                    ]
                },
                Completion("", "fake/model", 10, 5, 1),
            )

    agent = RequirementsAnalysisAgent()
    task = _task("requirements.analyze", {"requirements": ["must do x"]})
    r = agent.run(task, AgentContext(llm=FakeLLM()))
    assert r.payload["dropped_llm_proposals"] == 2  # both refs unknown (hash differs)
    assert r.adapter == "fake-local" and r.model_ref == "fake/model"


def test_functional_agent_reports_skipped_not_passed() -> None:
    agent = FunctionalTestingAgent()
    r = agent.run(
        _task(
            "functional.execute",
            {},
            {"scenarios": [{"id": "SCN-1", "title": "t", "test_type": "manual"}]},
        ),
        AgentContext(),
    )
    assert r.payload["summary"] == {"executed": 0, "passed": 0, "failed": 0, "skipped": 1}
    assert r.payload["executions"][0]["status"] == "skipped" and SKIP_REASON in r.warnings[0]


def _transport(method: str, url: str) -> tuple[int, dict[str, str], str]:
    if url.endswith("/healthz"):
        return (
            200,
            {"Authorization": "Bearer secret-token", "content-type": "application/json"},
            '{"status":"ok"}',
        )
    if url.endswith("/boom"):
        raise TimeoutError("ReadTimeout")
    return 404, {}, "not found"


def test_api_agent_runs_allowed_checks_blocks_others_and_redacts_evidence() -> None:
    agent = ApiTestingAgent()
    checks = [
        {"method": "GET", "url": "http://localhost:8000/healthz", "expected_status": 200},
        {"method": "GET", "url": "http://localhost:8000/missing", "expected_status": 200},
        {"method": "POST", "url": "http://localhost:8000/healthz", "expected_status": 200},
        {"method": "GET", "url": "https://example.com/", "expected_status": 200},
        {"method": "GET", "url": "http://localhost:8000/boom", "expected_status": 200},
    ]
    r = validate_output(
        agent,
        agent.run(
            _task("api.check", {"api_checks": checks}),
            AgentContext(http=HttpChecker(transport=_transport)),
        ),
    )
    statuses = [x["status"] for x in r.payload["results"]]
    assert statuses == ["passed", "failed", "blocked", "blocked", "timed_out"]
    assert r.payload["summary"]["executed"] == 2
    ev = r.evidence[0]["content"]
    assert ev["response"]["headers"]["authorization"] == "[REDACTED]"
    assert "secret-token" not in json.dumps(r.evidence)


@pytest.mark.parametrize(
    ("method", "url", "allowed"),
    [
        ("GET", "http://localhost:8000/x", True),
        ("HEAD", "http://127.0.0.1:1/x", True),
        ("POST", "http://localhost/x", False),
        ("GET", "http://169.254.169.254/latest", False),
        ("GET", "http://user:pw@localhost/x", False),
        ("GET", "ftp://localhost/x", False),
        ("GET", "https://api.github.com/", False),
    ],
)
def test_local_policy_is_deny_by_default(method: str, url: str, allowed: bool) -> None:
    assert evaluate_api_check(method, url, ["localhost", "127.0.0.1"]).allowed is allowed


def test_evidence_agent_groups_failures_and_separates_facts_from_inference() -> None:
    agent = EvidenceAnalysisAgent()
    execs = [
        {
            "id": "tex_1",
            "name": "GET /a",
            "status": "failed",
            "evidence_id": "evd_1",
            "meta": {
                "method": "GET",
                "url": "http://localhost/a",
                "expected_status": 200,
                "observed_status": 500,
            },
        },
        {
            "id": "tex_2",
            "name": "GET /a",
            "status": "failed",
            "evidence_id": "evd_2",
            "meta": {
                "method": "GET",
                "url": "http://localhost/a",
                "expected_status": 200,
                "observed_status": 500,
            },
        },
        {"id": "tex_3", "name": "x", "status": "skipped", "meta": {}},
        {"id": "tex_4", "name": "y", "status": "passed", "meta": {}},
    ]
    r = validate_output(
        agent, agent.run(_task("evidence.correlate", {}, {"executions": execs}), AgentContext())
    )
    assert len(r.payload["findings"]) == 1
    f = r.payload["findings"][0]
    assert f["occurrences"] == 2 and f["severity"] == "high" and f["confidence"] == "probable"
    assert f["dcs"] == sum(f["dcs_breakdown"].values()) and f["dcs"] < 80
    assert f["facts"][0].startswith("Observed HTTP 500") and f["inferred"][0].startswith(
        "Inference:"
    )
    assert r.payload["not_executed"]["skipped"] == 1


def test_reporting_agent_never_passes_unmeasured_gates() -> None:
    agent = ReportingAgent()
    up = {"executions": [], "findings": [], "scenarios": [], "tasks": []}
    r = validate_output(agent, agent.run(_task("report.build", {}, up), AgentContext()))
    gates = {g["gate_id"]: g["result"] for g in r.payload["gates"]}
    assert gates["QG-03"] == "inconclusive" and gates["QG-04"] == "inconclusive"
    assert gates["QG-05"] == "not_applicable" and r.payload["verdict"] == "INCONCLUSIVE"
    assert "deterministic" in r.payload["narrative_source"]
    up2 = {
        "executions": [{"id": "t", "scenario_id": "S1", "status": "passed", "meta": {}}] * 3,
        "findings": [
            {"confidence": "confirmed", "severity": "critical", "category": "api.contract"}
        ],
        "scenarios": [{"id": "S1", "priority": "P0"}],
        "tasks": [{"state": "succeeded"}],
    }
    r2 = agent.run(_task("report.build", {}, up2), AgentContext())
    assert (
        r2.payload["verdict"] == "NOT_READY" and "forces NOT_READY" in r2.payload["verdict_reason"]
    )


def test_planner_builds_acyclic_plan_and_detects_bad_plans() -> None:
    nodes = build_plan(
        {"requirements": ["r"], "api_checks": [{"url": "http://localhost/x"}]},
        {"functional": "standard"},
    )
    assert [n.key for n in nodes] == ["requirements", "functional", "api", "evidence", "report"]
    assert validate_plan(nodes) == [] and len(plan_hash(nodes)) == 64
    assert plan_hash(nodes) == plan_hash(
        build_plan(
            {"requirements": ["r"], "api_checks": [{"url": "http://localhost/x"}]},
            {"functional": "standard"},
        )
    )
    bad = [
        PlanNode("a", "AG-02", "requirements.analyze", "planning", depends_on=("b",)),
        PlanNode("b", "AG-11", "report.build", "x", depends_on=("a",)),
        PlanNode("c", "AG-99", "unknown.type", "x"),
    ]
    problems = validate_plan(bad)
    assert any("cycle" in p for p in problems) and any("no agent" in p for p in problems)


def test_llm_adapter_handles_malformed_timeouts_and_rate_limits() -> None:
    assert parse_json_object('```json\n{"a": 1}\n```')["a"] == 1
    with pytest.raises(AgentFailure) as exc:
        parse_json_object("no json here")
    assert exc.value.retryable and exc.value.error_code == "E-MODEL-003"

    calls = {"n": 0}

    def transport(url: str, payload: dict, timeout: float) -> dict:  # type: ignore[type-arg]
        calls["n"] += 1
        if calls["n"] == 1:
            return {"response": '{"scenarios": []}', "prompt_eval_count": 3, "eval_count": 2}
        return {"response": "garbage"}

    adapter = OllamaAdapter("http://localhost:11434", "llama3.1", transport=transport, per_minute=2)
    parsed, completion = adapter.complete_json("p", schema_hint={})
    assert (
        parsed == {"scenarios": []}
        and completion.model_ref == "ollama/llama3.1"
        and completion.tokens_in == 3
    )
    with pytest.raises(AgentFailure):
        adapter.complete_json("p", schema_hint={})  # malformed → retryable failure
    with pytest.raises(AgentFailure) as rl:
        adapter.complete_json("p", schema_hint={})  # third call in a minute → rate limited
    assert "rate limit" in str(rl.value)
    with pytest.raises(AgentFailure):
        NoLLM().complete_json("p", schema_hint={})
