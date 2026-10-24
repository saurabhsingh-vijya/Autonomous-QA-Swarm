# Phase 2 report — Real QA Execution Engine

Branch `feature/mvp-continue` (from `origin/feature-branch` 4cf5751). Plan: `phase-2-plan.md`.
Everything below was run on 2026-10-24 on Windows 11 (no Docker, no gVisor), Python 3.12.15 via uv,
Node 24, embedded PostgreSQL 16 (pgserver). Numbers are pasted from the actual runs.

## What was built (verified)

| Brief item | Implementation | Verified by |
|---|---|---|
| 1 Worker / execution service | `exec/` package `qaswarm_exec`: `ExecWorker` leases over `/internal/v1/exec/*` with `X-Exec-Token`, fetches the pinned commit (`GitSourceFetcher` / `FixtureSourceFetcher`), runs engines in `SubprocessRuntime`, uploads evidence, submits `worker_result/1`. Runs standalone (`python -m qaswarm_exec`) or embedded (`AQS_EMBEDDED_EXEC_WORKER=true`). | integration tests, live run |
| 2 Test-runner interface | `tools/base.py` (`CheckEngine.run(ctx) -> CheckResult`), registry, `planning/template.py` plans one task per engine; `env_prepare` is a critical first task. | unit tests |
| 3 Real deterministic checks | `snapshot_integrity` (SHA-256 of a deterministic tar), `python_syntax` (`ast.parse`), `secret_scan` (8 rules, masked evidence), `pytest` (runs the repository's suite via JUnit XML; refused → `skipped` unless `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true`). | unit tests on the fixture repo, live run |
| 4 Outcomes | `CheckOutcome` passed / failed / skipped / error; tests keep the six design statuses. | tests |
| 5 Timestamps, duration, logs, failure messages, evidence | `CheckRun` rows carry `started_at`, `ended_at`, `duration_ms`, `failure_message`, `summary`, `log_evidence_id`, `evidence_ids`. Evidence is content-addressed and redacted before hashing. | API responses below |
| 6 Persistence | Alembic revision `c2e1f7a90d44`: `worker_run`, `check_run`, `test_execution`, `evidence_item`, `report`, `job.snapshot_sha256`, `job.warnings`. Upgrade / downgrade / upgrade verified. | `alembic` run |
| 7 UI progress and results | SCR-04 Live Job Execution: 13-stage derived timeline, task table with attempts, checks table with evidence drawer, SSE event feed, report link; SCR-06 Functional Test Results; capability-driven mode pill. | browser run |
| 8 Inspect previous runs and compare | Jobs list shows commit; job detail lists previous runs of the same repository; `/jobs/{id}/compare?with=` + `CompareRuns` screen (improved / regressed / unchanged / added / removed). | live run QJ-1002 vs QJ-1001 |
| 9 Worker failures, retries, duplicates | Lease TTL + heartbeat, reaping and expiry in the scheduler, retry budget 2 with backoff, `E-EXEC-004` for invalid results, lease-lost handling in the worker, duplicate `POST /jobs` via `Idempotency-Key` and `409 job_duplicate_active`. | integration tests |
| 10 Automated tests | 171 backend tests (unit + integration), 25 web tests. | below |

## Test results (actual)

```
backend: python -m uv run python -m pytest tests -q
171 passed, 1 warning in 33.19s
ruff check src tests ../exec/src   → All checks passed!
ruff format --check                → 99 files already formatted
mypy src ../exec/src               → Success: no issues found in 88 source files

web: npm run typecheck → clean; npm run lint → 0 errors, 5 pre-existing react-refresh warnings
npx vitest run → Test Files 5 passed (5) · Tests 25 passed (25)
npm run build  → ✓ built in 3.93s (dist/assets/index-*.js 288 kB, gzip 87 kB)
```

Migration check: `alembic upgrade head`, `downgrade base`, `upgrade head` on the dev database — clean.

Note: while the Phase 4 and Phase 6 sessions ran their suites against the same `qaswarm_test`
database one run showed `1 failed, 148 passed, 22 errors`; rerun alone it is 171 passed. Each
parallel session now has its own test database.

## Live run (API + embedded scheduler + embedded worker, Vite dev server)

Started with `AQS_DEV_FIXTURE_REPOS=true`, `AQS_EXEC_TOKEN` set, code execution **not** allowed.

1. `GET /api/v1/system/capabilities` →
   `{"execution_enabled": true, "repository_code_execution_allowed": false, "sandbox": "process (no gVisor/Docker on this build)", "engines": ["snapshot_integrity","python_syntax","secret_scan","pytest"]}`
2. UI → Repositories → Add `https://fixtures.local/local/sample-python-app` (provider other) → 201.
3. UI → New QA job (`main`, Func Std, Sec Quick) → 202 → job `QJ-1001`. Within ~10 s:
   `validating → queued → planning → running → analyzing → reporting → completed_with_warnings`,
   commit `4e5f10ffe9f4…`, snapshot `29dd53829f27…`, 5 tasks succeeded, checks:
   - env_prepare **passed** (fixture, 8 files, 3442 bytes)
   - snapshot_integrity **passed** (expected == actual SHA-256)
   - pytest **skipped** — "Engine executes repository code and no sandbox runtime is available; refused."
   - python_syntax **failed** — `scripts/legacy_report.py:4 '(' was never closed`
   - secret_scan **failed** — `aws-access-key-id in config/settings_example.py:8`
   35 SSE events received live (`task.state_changed`, `check.completed`, `job.state_changed`, `stream.end`).
4. Evidence content for the secret finding is masked:
   `config/settings_example.py:8 aws-access-key-id AKIA****(sha256:1a5d44a2)`.
5. `POST /jobs` for ref `fix-rounding` → `QJ-1002`, completed_with_warnings, commit `1f8faf4925…`.
6. `GET /jobs/QJ-1002/compare?with=QJ-1001` → `check_deltas {"improved": 2, "unchanged": 3}`
   (python_syntax and secret_scan improved); rendered on `/jobs/:id/compare/:other`.
7. `GET /jobs/{id}/report?format=html` → HTML report; `format=pdf` → `501` "planned for slice 2d".
8. `POST /internal/v1/exec/lease` with a wrong token → `401`.
9. `GET /api/v1/audit-events` → hash-chained events including the scheduler's state changes.

Warnings shown for the job (from `job.warnings`): "Security profile: only secret detection runs in
this build; SAST, dependency and IaC scanners arrive in slice 2a."

## Defects found and fixed during verification

- Invalid worker result returned `422` but the failed attempt was rolled back with the request
  (`get_db` rollback) → the task stayed `leased`. Fixed: commit before raising.
- Worker crashed with `LeaseLostError` when the job was cancelled before `create_worker_run`.
  Fixed: run creation inside the guarded block; no destroy when no run started.
- Fixture URL `../etc` resolved to fixture `etc` (not a policy error). Fixed: dot segments rejected
  in both the control plane and the exec fetcher.
- Completed jobs showed unplanned stages as `not_run` instead of `skipped · not in plan`.
- Compare delta was labelled from the `with` job's side, so a fixed run showed "regressed". Fixed:
  delta describes the base job relative to `with`.
- UI and `validation_note` still said "slice 1a / arrives in slice 1b". Updated.

## Not implemented / honest limitations

- **No sandbox.** `SubprocessRuntime` is process isolation only. gVisor / Docker runtime is
  declared (`DockerRuntime.available() == False`) and not usable in this build.
- Flaky-test reruns, SAST / dependency / IaC scanners, performance and mutation engines, agents,
  patch proposals, PDF / SARIF / JUnit report export, OIDC: `501` or warning, as before.
- The embedded scheduler and worker are single-node conveniences; multi-worker fairness was not
  load-tested.
- `git ls-remote` intake was unit-tested with a stubbed `git`; a real public GitHub pin was not run
  from this machine (no outbound network in the sandboxed shell).

## Files of note

`docs/build/phase-2-plan.md`, `backend/migrations/versions/20261024_1200_phase2_execution_engine.py`,
`backend/src/qaswarm/{intake,evidence,planning,reporting}/`, `backend/src/qaswarm/workflow/scheduler.py`,
`backend/src/qaswarm/api/{routers/exec_internal.py,services/execution.py,services/results.py}`,
`exec/src/qaswarm_exec/`, `exec/fixtures/sample-python-app/`, `web/src/screens/{JobDetail,FunctionalResults,CompareRuns}.tsx`,
`.claude/skills/qa-swarm-dev/SKILL.md`, `docker-compose.yml` (scheduler + exec-host), `.env.example`.
