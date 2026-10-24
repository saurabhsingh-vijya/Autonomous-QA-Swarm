"""Phase 2 unit tests for control-plane pieces that need no database."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from qaswarm.api.services.jobs import _stages
from qaswarm.db.models import Job, Task
from qaswarm.evidence import EvidenceStore
from qaswarm.intake.hosts import is_public_address
from qaswarm.intake.resolvers import (
    FixtureRefResolver,
    GitLsRemoteResolver,
    IntakeError,
    resolver_for,
    tree_hash,
)
from qaswarm.planning import CRITICAL_TASK_TYPES, build_template_plan
from qaswarm.reporting import render_html

FIXTURES = Path(__file__).resolve().parents[3] / "exec" / "fixtures"


def _job(**over: Any) -> Job:
    base: dict[str, Any] = {
        "id": "job_x",
        "org_id": "org_x",
        "project_id": "prj_x",
        "repository_id": "rep_x",
        "display_id": "QJ-1",
        "ref": "main",
        "commit_sha": None,
        "profiles": {"functional": "standard", "security": "none", "performance": "none"},
        "profile_hash": "h",
        "state": "validating",
        "held_reason": "held",
        "created_by": "u",
        "warnings": {},
    }
    base.update(over)
    return Job(**base)


# ------------------------------------------------------------------- planner
def test_template_plan_shapes_follow_profiles() -> None:
    plan = build_template_plan(_job(commit_sha="a" * 40), "https://github.com/o/r", "github")
    types = [(t.task_type, t.inputs.get("engine")) for t in plan.tasks]
    assert types[0] == ("env_prepare", None)
    assert ("check", "pytest") in types and ("check", "python_syntax") in types
    assert ("check", "secret_scan") not in types
    assert all(t.depends_on == ["env_prepare"] for t in plan.tasks[1:])
    assert "env_prepare" in CRITICAL_TASK_TYPES and plan.warnings == []

    sec = build_template_plan(
        _job(profiles={"functional": "none", "security": "deep", "performance": "baseline"}),
        "https://github.com/o/r",
        "github",
    )
    engines = [t.inputs.get("engine") for t in sec.tasks if t.task_type == "check"]
    assert engines == ["snapshot_integrity", "secret_scan"]
    assert any("Future" in w for w in sec.warnings) and any("slice 3b" in w for w in sec.warnings)


# ---------------------------------------------------------------- evidence
def test_evidence_store_is_content_addressed_and_idempotent(tmp_path: Path) -> None:
    store = EvidenceStore(tmp_path)
    sha, key = store.put("org_1", b"hello")
    sha2, key2 = store.put("org_1", b"hello")
    assert (sha, key) == (sha2, key2) and key == f"evidence/org_1/{sha[:2]}/{sha}"
    assert store.get("org_1", sha) == b"hello"
    (tmp_path / key).write_bytes(b"tampered")
    with pytest.raises(Exception, match=sha):
        store.get("org_1", sha)


def test_store_evidence_redacts_before_hashing(tmp_path: Path) -> None:
    from unittest.mock import MagicMock

    from qaswarm.evidence import store_evidence

    session = MagicMock()
    store = EvidenceStore(tmp_path)
    item = store_evidence(
        session,
        store,
        org_id="org_1",
        job_id="job_1",
        kind="log",
        content="token=ghp_" + "a" * 36 + " done",
        media_type="text/plain",
        producer="t",
    )
    stored = store.get("org_1", item.sha256).decode()
    assert "ghp_" not in stored and "[REDACTED" in stored and item.redactions == 1


# ------------------------------------------------------------------ intake
@pytest.mark.parametrize(
    ("ip", "public"),
    [
        ("8.8.8.8", True),
        ("140.82.121.4", True),
        ("10.0.4.12", False),
        ("127.0.0.1", False),
        ("169.254.169.254", False),
        ("192.168.1.1", False),
        ("100.64.0.1", False),
        ("::1", False),
        ("::ffff:10.0.0.1", False),
        ("2606:4700::1111", True),
    ],
)
def test_public_address_classification(ip: str, public: bool) -> None:
    assert is_public_address(ip) is public


def test_fixture_resolver_pins_a_tree_hash_and_rejects_unknown_refs() -> None:
    r = FixtureRefResolver(FIXTURES)
    resolved = r.resolve("https://fixtures.local/local/sample-python-app", "main")
    assert resolved.commit_sha == tree_hash(FIXTURES / "sample-python-app" / "refs" / "main")
    assert resolved.default_branch == "main" and resolved.resolver == "fixture"
    with pytest.raises(IntakeError) as exc:
        r.resolve("https://fixtures.local/local/sample-python-app", "missing")
    assert exc.value.code == "E-INTAKE-002" and not exc.value.policy
    with pytest.raises(IntakeError) as exc2:
        r.resolve("https://fixtures.local/../etc", "main")
    assert exc2.value.policy


def test_git_resolver_refuses_private_hosts_before_contacting_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import qaswarm.intake.resolvers as mod

    monkeypatch.setattr(
        mod,
        "resolve_public_host",
        lambda host: (_ for _ in ()).throw(mod.HostRejected("private_address", "x")),
    )
    with pytest.raises(IntakeError) as exc:
        GitLsRemoteResolver().resolve("https://github.com/o/r", "main")
    assert (
        exc.value.code == "E-INTAKE-001"
        and exc.value.reason == "private_address"
        and exc.value.policy
    )


def test_git_resolver_parses_ls_remote_output(monkeypatch: pytest.MonkeyPatch) -> None:
    r = GitLsRemoteResolver(dns_check=False)
    out = "ref: refs/heads/main\tHEAD\n" + "a" * 40 + "\tHEAD\n" + "b" * 40 + "\trefs/heads/main\n"
    monkeypatch.setattr(r, "_run", lambda args: out)
    resolved = r.resolve("https://github.com/o/r", "main")
    assert resolved.commit_sha == "b" * 40 and resolved.default_branch == "main"
    with pytest.raises(IntakeError) as exc:
        r.resolve("https://github.com/o/r", "nope")
    assert exc.value.code == "E-INTAKE-002"
    assert r.resolve("https://github.com/o/r", "c" * 40).commit_sha == "c" * 40


def test_resolver_for_gates_fixtures_behind_the_dev_flag() -> None:
    with pytest.raises(IntakeError) as exc:
        resolver_for(
            "https://fixtures.local/x",
            dev_fixture_repos=False,
            fixtures_dir="",
            timeout_seconds=1,
            dns_check=False,
        )
    assert exc.value.policy
    assert isinstance(
        resolver_for(
            "https://github.com/o/r",
            dev_fixture_repos=False,
            fixtures_dir="",
            timeout_seconds=1,
            dns_check=False,
        ),
        GitLsRemoteResolver,
    )


# ------------------------------------------------------------ stage timeline
def _task(stage: str, state: str, code: str | None = None) -> Task:
    return Task(
        id=f"tsk_{stage}_{state}",
        org_id="org_x",
        job_id="job_x",
        stage=stage,
        task_type="check",
        state=state,
        idempotency_key="k",
        depends_on={"tasks": []},
        inputs={},
        last_error_code=code,
    )


def test_stage_timeline_is_derived_from_tasks_never_fabricated() -> None:
    held = _stages(_job(), [])
    assert [s.status for s in held][:3] == ["held", "pending", "pending"]

    running = _stages(
        _job(state="running", commit_sha="a" * 40, held_reason=None),
        [
            _task("environment_preparation", "succeeded"),
            _task("baseline_run", "running"),
            _task("security_testing", "pending"),
        ],
    )
    by = {s.stage: s for s in running}
    assert by["intake_and_pinning"].status == "succeeded" and by["planning"].status == "succeeded"
    assert (
        by["environment_preparation"].status == "succeeded"
        and by["baseline_run"].status == "running"
    )
    assert (
        by["security_testing"].status == "pending" and by["performance_testing"].status == "skipped"
    )

    failed = _stages(
        _job(state="failed", commit_sha="a" * 40, held_reason=None),
        [
            _task("environment_preparation", "failed", "E-EXEC-003"),
            _task("baseline_run", "skipped"),
        ],
    )
    by = {s.stage: s for s in failed}
    assert by["environment_preparation"].status == "failed" and "E-EXEC-003" in (
        by["environment_preparation"].note or ""
    )
    assert by["baseline_run"].status == "skipped"


def test_html_report_renders_without_external_assets() -> None:
    content = {
        "job": {
            "display_id": "QJ-7",
            "repository": "https://x/y",
            "ref": "main",
            "commit_sha": "abc",
            "snapshot_sha256": "s",
            "state": "completed",
        },
        "partial": False,
        "generated_at": datetime.now(UTC).isoformat(),
        "checks": [
            {
                "engine": "pytest",
                "name": "n",
                "outcome": "failed",
                "duration_ms": 3,
                "failure_message": "<b>x</b>",
            }
        ],
        "tests": [],
        "warnings": [],
        "limitations": ["l"],
        "evidence": [],
    }
    html = render_html(content)
    assert (
        "QJ-7" in html
        and "&lt;b&gt;x&lt;/b&gt;" in html
        and "http" not in html.split("<body>")[0].replace("https://x/y", "")
    )
