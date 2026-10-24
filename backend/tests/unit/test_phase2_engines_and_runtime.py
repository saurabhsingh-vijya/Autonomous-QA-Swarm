"""Phase 2 unit tests: check engines, runtime, source digests, JUnit parsing, worker result."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

import jsonschema
import pytest
from qaswarm_exec.host.source import FixtureSourceFetcher, snapshot_digest, tree_hash
from qaswarm_exec.results.junit import parse_junit
from qaswarm_exec.results.worker_result import build_worker_result
from qaswarm_exec.runtime.base import RunLimits, Workspace
from qaswarm_exec.runtime.docker_runtime import DockerRuntime
from qaswarm_exec.runtime.subprocess_runtime import SubprocessRuntime
from qaswarm_exec.tools.base import CheckContext
from qaswarm_exec.tools.pytest_runner import PytestEngine
from qaswarm_exec.tools.python_syntax import PythonSyntaxEngine
from qaswarm_exec.tools.registry import ENGINES, UnknownEngine, get_engine
from qaswarm_exec.tools.secret_scan import SecretScanEngine
from qaswarm_exec.tools.snapshot_integrity import SnapshotIntegrityEngine

from qaswarm.contracts import get_schema

FIXTURES = Path(__file__).resolve().parents[3] / "exec" / "fixtures"


class MemorySink:
    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def put(
        self, *, kind: str, label: str, media_type: str, content: bytes, deterministic: bool = True
    ) -> str:
        self.items.append(
            {"kind": kind, "label": label, "media_type": media_type, "content": content}
        )
        return f"evd_{len(self.items)}"


def _ctx(
    tmp_path: Path, src: Path, *, allow: bool = False, snapshot: str | None = None
) -> CheckContext:
    out = tmp_path / "out"
    out.mkdir(exist_ok=True)
    return CheckContext(
        task={"task_id": "tsk_x", "inputs": {}},
        workspace=src,
        out_dir=out,
        runtime=SubprocessRuntime(),
        limits=RunLimits(timeout_seconds=120, output_cap_bytes=1_000_000),
        evidence=MemorySink(),
        allow_code_execution=allow,
        cancel=threading.Event(),
        snapshot_sha256=snapshot,
    )


# ---------------------------------------------------------------- source digests
def test_tree_hash_and_snapshot_digest_are_deterministic(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "x.py").write_text("print(1)\n")
    (tmp_path / "b.txt").write_text("hello")
    h1, d1 = tree_hash(tmp_path), snapshot_digest(tmp_path)
    time.sleep(0.01)
    (tmp_path / "b.txt").touch()  # mtime change must not matter
    h2, d2 = tree_hash(tmp_path), snapshot_digest(tmp_path)
    assert h1 == h2 and d1 == d2 and len(h1) == 40 and len(d1[0]) == 64 and d1[1] == 2
    (tmp_path / "b.txt").write_text("changed")
    assert tree_hash(tmp_path) != h1 and snapshot_digest(tmp_path)[0] != d1[0]


def test_fixture_fetcher_copies_ref_and_rejects_moved_content(tmp_path: Path) -> None:
    fetcher = FixtureSourceFetcher(FIXTURES)
    src = {
        "repository_url": "https://fixtures.local/local/sample-python-app",
        "ref": "main",
        "commit_sha": "",
    }
    fetched = fetcher.fetch(src, tmp_path / "s1")
    assert (tmp_path / "s1" / "app" / "money.py").exists()
    assert fetched.commit_sha == tree_hash(FIXTURES / "sample-python-app" / "refs" / "main")
    with pytest.raises(Exception, match="changed since"):
        fetcher.fetch({**src, "commit_sha": "0" * 40}, tmp_path / "s2")
    with pytest.raises(Exception, match="not found"):
        fetcher.fetch({**src, "ref": "nope"}, tmp_path / "s3")


# ------------------------------------------------------------------- engines
def test_registry_lists_four_engines_and_rejects_unknown() -> None:
    assert {"snapshot_integrity", "python_syntax", "secret_scan", "pytest"} <= set(ENGINES)
    assert get_engine("secret_scan").engine_id == "secret_scan"
    with pytest.raises(UnknownEngine):
        get_engine("nope")


def test_python_syntax_passes_fails_and_skips(tmp_path: Path) -> None:
    good = tmp_path / "good"
    good.mkdir()
    (good / "ok.py").write_text("x = 1\n")
    r = PythonSyntaxEngine().run(_ctx(tmp_path, good))
    assert r.outcome == "passed" and r.summary == {"files": 1, "errors": 0}

    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "ok.py").write_text("x = 1\n")
    (bad / "broken.py").write_text("def f(:\n  pass\n")
    r = PythonSyntaxEngine().run(_ctx(tmp_path, bad))
    assert r.outcome == "failed" and r.summary["errors"] == 1 and "broken.py" in (r.message or "")

    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "readme.md").write_text("no python here")
    assert PythonSyntaxEngine().run(_ctx(tmp_path, empty)).outcome == "skipped"


def test_secret_scan_masks_matches_in_evidence(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "settings.py").write_text('KEY = "AKIAIOSFODNN7EXAMPLE"\n')
    ctx = _ctx(tmp_path, src)
    r = SecretScanEngine().run(ctx)
    assert r.outcome == "failed" and r.summary["high"] == 1
    report = json.loads(ctx.evidence.items[0]["content"])  # type: ignore[attr-defined]
    assert "AKIAIOSFODNN7EXAMPLE" not in json.dumps(report)
    assert report["findings"][0]["match"].startswith("AKIA****")
    (src / "settings.py").write_text("KEY = os.environ['K']\n")
    assert SecretScanEngine().run(_ctx(tmp_path, src)).outcome == "passed"


def test_snapshot_integrity_compares_with_recorded_digest(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    (src / "a.txt").write_text("a")
    digest = snapshot_digest(src)[0]
    assert SnapshotIntegrityEngine().run(_ctx(tmp_path, src, snapshot=digest)).outcome == "passed"
    assert SnapshotIntegrityEngine().run(_ctx(tmp_path, src, snapshot="f" * 64)).outcome == "failed"


def test_pytest_engine_is_refused_without_opt_in_and_runs_fixture_when_allowed(
    tmp_path: Path,
) -> None:
    engine = PytestEngine()
    assert engine.executes_repository_code is True
    main_src = tmp_path / "main"
    FixtureSourceFetcher(FIXTURES).fetch(
        {"repository_url": "https://fixtures.local/local/sample-python-app", "ref": "main"},
        main_src,
    )
    r = engine.run(_ctx(tmp_path, main_src, allow=True))
    assert r.outcome == "failed", r.message
    statuses = {t.node_id.split("::")[-1]: t.status for t in r.tests}
    assert statuses["test_rounds_half_even"] == "failed"
    assert statuses["test_rejects_sub_minor_unit_amount"] == "failed"
    assert statuses["test_two_decimals_pass_through"] == "passed"
    assert len(r.tests) == 7 and r.summary["failed"] == 2

    fixed_src = tmp_path / "fixed"
    FixtureSourceFetcher(FIXTURES).fetch(
        {"repository_url": "https://fixtures.local/local/sample-python-app", "ref": "fix-rounding"},
        fixed_src,
    )
    r2 = engine.run(_ctx(tmp_path, fixed_src, allow=True))
    assert r2.outcome == "passed" and r2.summary["passed"] == 7

    empty = tmp_path / "empty"
    empty.mkdir()
    assert engine.run(_ctx(tmp_path, empty, allow=True)).outcome == "skipped"


# ------------------------------------------------------------------- runtime
def test_subprocess_runtime_times_out_and_kills_the_process(tmp_path: Path) -> None:
    rt = SubprocessRuntime()
    started = time.monotonic()
    res = rt.run(
        [sys.executable, "-c", "import time; print('x', flush=True); time.sleep(30)"],
        cwd=tmp_path,
        limits=RunLimits(timeout_seconds=1, output_cap_bytes=10_000),
        output_path=tmp_path / "out.log",
    )
    assert res.timed_out and res.killed_reason == "wall clock exceeded"
    assert time.monotonic() - started < 20
    assert (tmp_path / "out.log").read_text().startswith("x")


def test_subprocess_runtime_caps_output_and_scrubs_env(tmp_path: Path) -> None:
    rt = SubprocessRuntime()
    res = rt.run(
        [
            sys.executable,
            "-c",
            "import os,sys; print(os.environ.get('AQS_EXEC_TOKEN','none')); print('y'*5000)",
        ],
        cwd=tmp_path,
        limits=RunLimits(timeout_seconds=30, output_cap_bytes=1000, env={}),
        output_path=tmp_path / "out.log",
    )
    text = (tmp_path / "out.log").read_text()
    assert text.startswith("none") and res.truncated and "[TRUNCATED" in text
    assert (tmp_path / "out.log").stat().st_size < 1200


def test_subprocess_runtime_honours_cancel(tmp_path: Path) -> None:
    cancel = threading.Event()
    threading.Timer(0.5, cancel.set).start()
    res = SubprocessRuntime().run(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        cwd=tmp_path,
        limits=RunLimits(timeout_seconds=60),
        output_path=tmp_path / "o.log",
        cancel=cancel,
    )
    assert res.cancelled and not res.timed_out


def test_workspace_is_always_removed(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError), Workspace(tmp_path) as ws:
        path = ws.path
        assert ws.src.exists() and ws.out.exists()
        raise RuntimeError("boom")
    assert not path.exists()


def test_docker_runtime_reports_unavailable(tmp_path: Path) -> None:
    rt = DockerRuntime()
    assert rt.available() is False
    with pytest.raises(Exception, match="not implemented"):
        rt.run(["x"], cwd=tmp_path, limits=RunLimits(), output_path=tmp_path / "o")


# ---------------------------------------------------------- results/normalise
def test_junit_parser_maps_failure_error_skip(tmp_path: Path) -> None:
    xml = tmp_path / "j.xml"
    xml.write_text(
        """<?xml version="1.0"?><testsuites><testsuite name="s">
        <testcase classname="t.a" name="ok" time="0.5"/>
        <testcase classname="t.a" name="bad" time="0.1"><failure message="assert 1 == 2">trace</failure></testcase>
        <testcase classname="t.a" name="err"><error message="ImportError">x</error></testcase>
        <testcase classname="t.a" name="skip"><skipped message="not now"/></testcase>
        </testsuite></testsuites>"""
    )
    results = {t.name: t for t in parse_junit(xml)}
    assert results["ok"].status == "passed" and results["ok"].duration_ms == 500
    assert results["bad"].status == "failed" and "assert 1 == 2" in (results["bad"].message or "")
    assert results["err"].status == "failed" and (results["err"].message or "").startswith(
        "error ("
    )
    assert results["skip"].status == "skipped"
    evil = tmp_path / "evil.xml"
    evil.write_text('<!DOCTYPE x [<!ENTITY e "x">]><testsuites/>')
    with pytest.raises(ValueError):
        parse_junit(evil)


def test_worker_result_matches_lld_schema() -> None:
    wr = build_worker_result(
        task_id="tsk_01JB7Q3M2X8V4R6T9W1Y5Z0A2C",
        attempt_no=1,
        worker_run_id="wrk_01JB7Q4A",
        exit_code=1,
        duration_ms=412,
        tool_name="pytest",
        tool_version="pytest 8.3.4",
        image_digest="sha256:" + "a" * 32,
        summary={"executed": 7, "passed": 5, "failed": 2},
        results_ref="evd_1",
        evidence_refs=["evd_1"],
        truncated=False,
        redactions_applied=0,
        output_bytes=120,
    )
    jsonschema.Draft202012Validator(get_schema("worker_result/1")).validate(wr)
    assert wr["summary"] == {"executed": 7, "passed": 5, "failed": 2, "skipped": 0, "errors": 0}
