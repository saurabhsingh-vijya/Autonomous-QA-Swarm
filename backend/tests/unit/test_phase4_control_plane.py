"""Phase 4 control-plane unit tests: planner profiles, target URL validation, request schemas."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from qaswarm.api.errors import Problem
from qaswarm.api.schemas import JobCreate, TargetCreate
from qaswarm.api.services.targets import validate_base_url
from qaswarm.db.models import Job
from qaswarm.planning import build_template_plan
from qaswarm.planning.template import (
    KNOWN_ENGINES,
    TARGET_ENGINES,
    needs_target,
    requested_activities,
)

REPO = "rep_01JB8Q2W6V3K9X4M7N5P2R8T1A"
TGT = "tgt_01JB6T2G3H4J5K6M7N8P9Q0R1S"


def _job(**over: Any) -> Job:
    base: dict[str, Any] = {
        "id": "job_x",
        "org_id": "org_x",
        "project_id": "prj_x",
        "repository_id": "rep_x",
        "display_id": "QJ-1",
        "ref": "main",
        "commit_sha": "a" * 40,
        "profiles": {"functional": "standard", "security": "none", "performance": "none"},
        "inputs": {},
        "profile_hash": "h",
        "state": "queued",
        "held_reason": None,
        "created_by": "u",
        "warnings": {},
    }
    base.update(over)
    return Job(**base)


def _engines(plan: Any) -> list[str]:
    return [t.inputs.get("engine") for t in plan.tasks if t.task_type == "check"]


# ------------------------------------------------------------------------ planner
def test_plans_without_phase4_config_are_unchanged() -> None:
    for profiles in (
        {"functional": "standard", "security": "none", "performance": "none"},
        {"functional": "standard", "security": "quick", "performance": "smoke"},
        {"functional": "none", "security": "deep", "performance": "baseline"},
    ):
        job = _job(profiles=profiles)
        plan = build_template_plan(job, "https://github.com/o/r", "github")
        with_fixtures = build_template_plan(
            job, "https://github.com/o/r", "github", fixture_targets=True
        )
        assert not any(e in TARGET_ENGINES for e in _engines(plan))
        assert plan == with_fixtures
        assert all("target" not in t.inputs for t in plan.tasks)
        assert needs_target(job) is False
    quick = build_template_plan(
        _job(profiles={"functional": "none", "security": "quick", "performance": "smoke"}),
        "https://github.com/o/r",
        "github",
    )
    assert _engines(quick) == ["snapshot_integrity", "secret_scan"]
    assert any("slice 3b" in w for w in quick.warnings)


def test_plan_adds_target_engines_with_local_fixture_target() -> None:
    job = _job(
        profiles={"functional": "standard", "security": "standard", "performance": "smoke"},
        inputs={
            "testing": {
                "target": "local_fixture",
                "api": {"suites": [".qaswarm/tests"]},
                "browser": {},
                "security": {"paths": ["/", "/login"]},
                "performance": {"max_requests": 12},
            }
        },
    )
    assert needs_target(job) and requested_activities(job) == {
        "api",
        "browser",
        "security",
        "performance",
    }
    plan = build_template_plan(job, "https://fixtures.local/local/x", "other", fixture_targets=True)
    assert _engines(plan) == [
        "snapshot_integrity",
        "python_syntax",
        "pytest",
        "secret_scan",
        "api_tests",
        "browser_tests",
        "security_checks",
        "performance_probe",
    ]
    by_engine = {t.inputs["engine"]: t for t in plan.tasks if t.task_type == "check"}
    assert by_engine["api_tests"].inputs["target"] == {
        "kind": "local_fixture",
        "name": "sample-target-app",
    }
    assert by_engine["api_tests"].inputs["config"] == {"suites": [".qaswarm/tests"]}
    assert by_engine["security_checks"].inputs["config"] == {
        "profile": "standard",
        "paths": ["/", "/login"],
    }
    assert by_engine["performance_probe"].inputs["config"] == {
        "profile": "smoke",
        "max_requests": 12,
    }
    assert by_engine["performance_probe"].stage == "performance_testing"
    assert (
        by_engine["api_tests"].agent_id == "AG-04"
        and by_engine["performance_probe"].agent_id == "AG-06"
    )
    assert all(t.depends_on == ["env_prepare"] for t in plan.tasks[1:])
    assert not any("slice 3b" in w for w in plan.warnings)
    assert any("not a security assessment" in w for w in plan.warnings)

    # Without fixture targets enabled, nothing target-facing is planned and the user is told why.
    no_fixture = build_template_plan(job, "https://fixtures.local/local/x", "other")
    assert not any(e in TARGET_ENGINES for e in _engines(no_fixture))
    assert any("Target checks need a registered target" in w for w in no_fixture.warnings)


def test_plan_respects_registered_target_authorization_and_ha03() -> None:
    target = {
        "kind": "registered",
        "target_id": TGT,
        "base_url": "https://staging.example.test",
        "allowed_hosts": [],
        "allowed_activities": ["api", "security"],
    }
    job = _job(
        profiles={"functional": "none", "security": "quick", "performance": "baseline"},
        inputs={"target_id": TGT, "testing": {"api": {}, "browser": {}}},
    )
    plan = build_template_plan(job, "https://github.com/o/r", "github", target=target)
    assert _engines(plan) == ["snapshot_integrity", "secret_scan", "api_tests", "security_checks"]
    assert any("'browser' is not covered" in w for w in plan.warnings)
    assert any("'performance' is not covered" in w for w in plan.warnings)
    full = {**target, "allowed_activities": ["api", "browser", "security", "performance"]}
    plan = build_template_plan(job, "https://github.com/o/r", "github", target=full)
    assert "performance_probe" not in _engines(plan)
    assert any("requires HA-03" in w for w in plan.warnings)
    smoke = _job(
        profiles={"functional": "none", "security": "none", "performance": "smoke"},
        inputs={"target_id": TGT},
    )
    plan = build_template_plan(smoke, "https://github.com/o/r", "github", target=full)
    assert _engines(plan) == ["snapshot_integrity", "performance_probe"]
    assert plan.tasks[-1].inputs["target"]["base_url"] == "https://staging.example.test"


def test_rerun_restricts_the_plan_to_selected_engines() -> None:
    job = _job(
        profiles={"functional": "standard", "security": "quick", "performance": "none"},
        inputs={
            "testing": {"target": "local_fixture", "api": {}},
            "rerun": {"of_job": "job_old", "engines": ["api_tests", "pytest", "nope"]},
        },
    )
    plan = build_template_plan(job, "https://fixtures.local/local/x", "other", fixture_targets=True)
    assert plan.tasks[0].task_type == "env_prepare"
    assert _engines(plan) == ["pytest", "api_tests"]
    assert any("unknown engine(s): nope" in w for w in plan.warnings)
    assert {"pytest", "api_tests", "secret_scan"} <= KNOWN_ENGINES


# ------------------------------------------------------------------ target URLs
def test_target_base_url_validation() -> None:
    assert validate_base_url("https://Staging.Example.test/app/", allow_local=False) == (
        "https://staging.example.test/app"
    )
    for bad in ("ftp://x.test", "https://", "https://u:p@x.test", "https://x.test/?a=1"):
        with pytest.raises(Problem) as exc:
            validate_base_url(bad, allow_local=False)
        assert exc.value.status == 422
    for local in (
        "http://127.0.0.1:8000",
        "http://localhost",
        "http://10.0.0.5",
        "http://169.254.169.254",
    ):
        with pytest.raises(Problem) as exc:
            validate_base_url(local, allow_local=False)
        assert exc.value.error_code == "target_host_not_allowed"
        assert validate_base_url(local, allow_local=True).startswith("http://")


# ---------------------------------------------------------------------- schemas
def test_job_create_accepts_strict_testing_config() -> None:
    body = JobCreate.model_validate(
        {
            "repository_id": REPO,
            "ref": "main",
            "testing": {"api": {"suites": ["t"]}, "performance": {"max_requests": 5}},
            "target_id": TGT,
        }
    )
    assert body.testing is not None and body.testing.performance is not None
    assert body.testing.model_dump(mode="json", exclude_none=True) == {
        "api": {"suites": ["t"]},
        "performance": {"paths": ["/health"], "max_requests": 5},
    }
    with pytest.raises(ValidationError):
        JobCreate.model_validate({"repository_id": REPO, "ref": "main", "testing": {"fuzz": {}}})
    with pytest.raises(ValidationError):
        JobCreate.model_validate(
            {"repository_id": REPO, "ref": "main", "testing": {"performance": {"concurrency": 0}}}
        )
    with pytest.raises(ValidationError):
        TargetCreate.model_validate(
            {
                "project_id": "prj_x",
                "name": "n",
                "environment_type": "production",
                "base_url": "https://x.test",
                "owner": "o",
            }
        )
