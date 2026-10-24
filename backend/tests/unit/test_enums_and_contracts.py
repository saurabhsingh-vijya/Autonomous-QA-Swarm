from __future__ import annotations

import json

from qaswarm.api.contract_table import CONTRACT
from qaswarm.contracts import get_schema, list_schemas
from qaswarm.domain import enums
from qaswarm.domain.ids import display_id, is_id, new_id


def test_enum_vocabularies_match_data_model() -> None:
    assert [s.value for s in enums.JobState] == [
        "created",
        "validating",
        "queued",
        "planning",
        "awaiting_approval",
        "running",
        "analyzing",
        "reporting",
        "cancelling",
        "completed",
        "completed_with_warnings",
        "failed",
        "cancelled",
        "timed_out",
        "blocked",
    ]
    assert [s.value for s in enums.TaskState] == [
        "pending",
        "leased",
        "running",
        "succeeded",
        "failed_retryable",
        "retry_scheduled",
        "failed",
        "invalid_output",
        "timed_out",
        "cancelled",
        "skipped",
    ]
    assert [s.value for s in enums.TestExecutionStatus] == [
        "passed",
        "failed",
        "skipped",
        "blocked",
        "timed_out",
        "infrastructure_error",
    ]
    assert [s.value for s in enums.FindingStatus] == [
        "candidate",
        "triaging",
        "reproducing",
        "confirmed",
        "not_reproducible",
        "false_positive",
        "duplicate",
        "accepted_risk",
        "fix_proposed",
        "fix_verified",
        "fix_failed",
        "reopened",
    ]
    assert [s.value for s in enums.PatchStatus] == [
        "proposed",
        "awaiting_review",
        "approved_for_verification",
        "verification_running",
        "verified",
        "verification_failed",
        "rejected",
    ]
    assert [s.value for s in enums.GateResult] == [
        "passed",
        "failed",
        "advisory_failed",
        "inconclusive",
        "not_applicable",
        "pending",
    ]
    assert [s.value for s in enums.Verdict] == [
        "READY",
        "READY_WITH_RISKS",
        "NOT_READY",
        "INCONCLUSIVE",
    ]
    assert [s.value for s in enums.Role] == [
        "Org Admin",
        "QA Lead",
        "QA Engineer",
        "Developer",
        "Security Reviewer",
        "Viewer",
        "CI Service Account",
    ]
    assert [s.value for s in enums.Severity] == [
        "critical",
        "high",
        "medium",
        "low",
        "informational",
    ]
    assert [s.value for s in enums.Confidence] == ["confirmed", "probable", "candidate", "rejected"]
    assert len(enums.PIPELINE_STAGES) == 13


def test_prefixed_ulids() -> None:
    jid = new_id("job")
    assert jid.startswith("job_") and len(jid) == 30
    assert is_id(jid, "job") and not is_id(jid, "task")
    assert display_id("QJ", 1042) == "QJ-1042"


def test_contract_schemas_load_and_validate_lld_examples() -> None:
    assert {s.name for s in list_schemas()} == {"task_contract", "worker_result"}
    tc = get_schema("task_contract/1")
    wr = get_schema("worker_result/1")
    assert tc["properties"]["schema_version"] == {"const": "1.0"}
    assert wr["properties"]["evidence_refs"]["maxItems"] == 1000
    assert (
        wr["properties"]["resource_usage"]["properties"]["output_bytes"]["maximum"]
        == 50 * 1024 * 1024
    )
    json.dumps(tc)


def test_contract_table_covers_every_endpoint_in_the_api_contract() -> None:
    expected = {
        ("POST", "/projects"),
        ("GET", "/projects"),
        ("POST", "/repositories"),
        ("GET", "/repositories/{repository_id}"),
        ("POST", "/repositories/{repository_id}/validate"),
        ("POST", "/targets"),
        ("POST", "/targets/{target_id}/authorizations"),
        ("POST", "/jobs"),
        ("GET", "/jobs"),
        ("GET", "/jobs/{job_id}"),
        ("POST", "/jobs/{job_id}/cancel"),
        ("GET", "/jobs/{job_id}/events"),
        ("GET", "/jobs/{job_id}/plan"),
        ("POST", "/jobs/{job_id}/plan/approval"),
        ("GET", "/jobs/{job_id}/tasks"),
        ("GET", "/jobs/{job_id}/test-executions"),
        ("GET", "/jobs/{job_id}/findings"),
        ("GET", "/findings/{finding_id}"),
        ("POST", "/findings/{finding_id}/triage"),
        ("GET", "/findings/{finding_id}/evidence"),
        ("GET", "/jobs/{job_id}/performance-runs"),
        ("GET", "/jobs/{job_id}/mutation-runs"),
        ("GET", "/jobs/{job_id}/patches"),
        ("POST", "/patches/{patch_id}/review"),
        ("POST", "/patches/{patch_id}/verifications"),
        ("GET", "/verifications/{verification_id}"),
        ("GET", "/jobs/{job_id}/quality-gates"),
        ("GET", "/jobs/{job_id}/report"),
        ("POST", "/jobs/{job_id}/release-decision"),
        ("GET", "/audit-events"),
    }
    assert {(e.method, e.path) for e in CONTRACT} == expected
    assert len(CONTRACT) == 30
