# Phase 6 report — Hardening and release readiness

Branch `phase6-hardening` (from `feature/mvp-continue` @ 9d185ad), 7 commits, not pushed.
Date: 24 October 2026. Machine: Windows 11 Pro, no Docker, embedded PostgreSQL 16 (pgserver),
Python 3.12.15 via uv 0.13.5, Node 22. Plan: `docs/build/phase-6-plan.md`.

**Verdict: not production-ready, and this report does not claim it.** The build is stable for a
trusted-network demo and for continuing development. The two production blockers are unchanged
from the design roadmap: no sandbox runtime (slice 1c) and no real authentication (slice 3e).
Everything below distinguishes what was executed on this machine from what was not.

## 1. Tests executed (actual output)

### Backend — unit + integration against PostgreSQL 16 (final run, after all changes)

```
$ AQS_TEST_DATABASE_URL=postgresql+psycopg://qaswarm:***@127.0.0.1:59137/qaswarm_test_p6 \
  python -m uv run python -m pytest tests -q -p no:cacheprovider
211 passed, 1 warning in 26.80s
```

(Baseline at 9d185ad: `171 passed, 1 warning in 45.35s`. Phase 6 added 40 tests: 23 unit in
`tests/unit/test_phase6_hardening.py`, 5 integration in `tests/integration/test_execution_pipeline.py`,
plus parametrised cases.) The one warning is Starlette's TestClient `httpx` deprecation notice.

### Lint and types

```
$ python -m uv run ruff check src tests ../exec/src            → All checks passed!
$ python -m uv run ruff format --check src tests ../exec/src   → 100 files already formatted
$ python -m uv run python -m mypy src ../exec/src              → Success: no issues found in 89 source files
```

`uv run mypy` and `uv run uvicorn` fail on this host with *"An Application Control policy has
blocked this file"*; `python -m mypy` / `python -m qaswarm.api.serve` are the documented workaround.

### Web

```
$ npm run typecheck   → tsc --noEmit: clean
$ npm run lint        → ✖ 5 problems (0 errors, 5 warnings)   # react-refresh/only-export-components, pre-existing
$ npm run format:check→ All matched files use Prettier code style!
$ npx vitest run      → Test Files 5 passed (5) · Tests 25 passed (25)
$ npm run build       → ✓ built in 3.03s (dist/assets/index-*.js 288 kB, gzip 87 kB)
```

### Migrations

```
$ alembic upgrade head → downgrade base → upgrade head
Running downgrade c2e1f7a90d44 -> b50874965b43, phase 2: execution engine …
Running downgrade b50874965b43 -> , slice 1a foundations
Running upgrade  -> b50874965b43, slice 1a foundations
Running upgrade b50874965b43 -> c2e1f7a90d44, phase 2: execution engine …
c2e1f7a90d44 (head)
```

Run on both the main database and the test database.

### Dependency audits

```
$ python -m uv run --with pip-audit python -m pip_audit --skip-editable
No known vulnerabilities found                      # before: 16 advisories (starlette 0.46.2, pytest 8.4.2)

$ npm audit (after bumps)
12 vulnerabilities (9 moderate, 1 high, 2 critical)  # before: 14 (2 low, 5 moderate, 5 high, 2 critical)
```

Remaining npm items are all development tooling: `tinypool` via vitest ≤ 4 (fix = vitest 5, a
breaking upgrade), `esbuild` dev-server advisory via vite 5 (fix = vite 6+), `postcss-selector-parser`
via tailwindcss 3 (fix = tailwind 4), `react-router` SSR `deserializeErrors` path (this SPA has no
SSR). None ships to the browser bundle as an exploitable path; they are listed on the release
checklist for the next toolchain upgrade.

### Clean installation

```
$ UV_PROJECT_ENVIRONMENT=<temp> python -m uv sync --all-groups --frozen   → 57 packages installed, imports ok (fastapi 0.162.0)
$ cd web && npm ci                                                        → added 351 packages in 11s
```

The baseline run also created `backend/.venv` from scratch (`Creating virtual environment … Installed 54 packages`).

## 2. Build and startup

- `python -m qaswarm.api.serve --port 8020` with `AQS_EMBEDDED_SCHEDULER=true`,
  `AQS_EMBEDDED_EXEC_WORKER=true`, `AQS_DEV_FIXTURE_REPOS=true`,
  `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true`: ready in 4–6 s; `/readyz` →
  `{"status":"ok","version":"0.1.0","database":"reachable"}`.
- Startup logged six `configuration:` warnings (dev auth, sample DB password, unsandboxed
  execution, embedded worker, embedded scheduler, fixture repos); the same list is returned by
  `GET /api/v1/system/capabilities` with the 17 `501` endpoints.
- Web production build served with `vite preview --port 5176` proxied to the API; Dashboard and
  Live Job Execution rendered with zero console errors.
- **Not executed:** `docker compose up` (no Docker on this machine). The compose file and
  `backend/Dockerfile` were updated (git installed, exec package via the `embedded` extra,
  `AQS_EXEC_TOKEN` required, evidence volume) but are unverified.

## 3. Verified user workflows (live API, dedicated database `qaswarm_p6`)

Script output (abridged; full logs were captured during the run):

```
[capabilities] GET /api/v1/system/capabilities -> 200 {"execution_enabled": true, "repository_code_execution_allowed": true, "sandbox": "process (no gVisor/Docker on this build)"}
[exec no token] POST /internal/v1/exec/lease -> 401        [exec wrong token] -> 401
[no auth] GET /api/v1/projects -> 401                      [query-param auth on non-SSE] -> 401
[viewer create project] POST /api/v1/projects -> 403       [create project] -> 201
[reject url] http://github.com/a/b -> 422 scheme_not_https · https://10.0.0.1/a/b -> 422 host_not_allow_listed
[reject url] https://user:pw@github.com/a/b -> 422 credentials_in_url · https://evil.example/a/b -> 422 host_not_allow_listed
[repository] POST /api/v1/repositories -> 201 {"validation_status": "pending_validation"}
[job without Idempotency-Key] -> 400
[create job] -> 202 {"display_id": "QJ-1001", "state": "validating"}
[replay same key] -> 202 {"replayed": "true", "same_id": true}
[duplicate active] -> 409 {"error_code": "job_duplicate_active", "existing": "QJ-1001"}
  state validating → running (1.5 s) → analyzing (6.1 s) → reporting (7.6 s) → completed_with_warnings (10.6 s)
[job 1 final] commit 4e5f10ff… snapshot 29dd5382… task_summary {"succeeded": 5} check_summary {"failed": 3, "passed": 2} test_summary {"failed": 2, "passed": 5}
[checks] env_prepare passed · snapshot_integrity passed · pytest failed "2 test(s) failed: tests.test_money::test_rounds_half_even, …" (executes_repository_code=true)
         python_syntax failed "scripts/legacy_report.py:4 '(' was never closed" · secret_scan failed "aws-access-key-id in config/settings_example.py:8"
[test-executions] -> 200 X-Test-Counts: failed=2,passed=5 (7 rows)
[evidence] 10 items, kinds environment_manifest/junit_xml/log/scanner_report/source_inventory
[secret scan evidence (masked)] "match": "AKIA****(sha256:1a5d44a2)"
[viewer evidence] -> 403          [evidence download] nosniff, attachment, X-Content-SHA256
[worker-runs] 5 × isolation=process outcome=succeeded destroyed=true
[report json] partial=false summary tasks/checks/tests as above · [report html] text/html, CSP default-src 'none'; style-src 'unsafe-inline' · [report pdf] -> 501
[audit events] -> 200 (job.state_changed, worker_run.destroyed, task.state_changed …) · [audit as viewer] -> 403
[job 2 fix-rounding] completed_with_warnings check_summary {"passed": 5} test_summary {"passed": 7}
[compare] check_deltas {"unchanged": 2, "improved": 3} test_deltas {"unchanged": 5, "improved": 2}
[cancel job 3 while running with 1 live worker run] -> 202 cancelling → cancelled after 4.0 s; worker run outcome "cancelled", destroyed
[cancel terminal job] -> 409 · [partial report] partial=true
[sse] 24 events: check.completed, job.held, job.pinned, job.state_changed, task.enqueued, task.state_changed, stream.end
[jobs list] cursor pagination page 1 (2) → page 2 (1) · unknown state filter -> 400 · unknown job -> 404
```

Crash and restart (`AQS_LEASE_TTL_SECONDS=20`, backoff `[2,4]` to keep the demo short):

```
[killing API while a task is leased/running] {"task": "env_prepare", "state": "leased"}
[api restarted] … running → analyzing (23.3 s) → reporting → completed_with_warnings (27.3 s)
[final] tasks: pytest succeeded on attempt 2 with last_error_code E-QUEUE-001; worker_runs include one "presumed_dead"
[reaper audit] {"outcome": "presumed_dead", "reason": "no heartbeat within the lease TTL; worker presumed gone"}
```

UI check (production build in the browser pane): Dashboard tiles Projects 2 / Repositories 1 /
Active jobs 0 and the three recent jobs equal `GET /projects`, `/repositories`, `/jobs`; the job
detail's task (5 succeeded), check (3 failed / 2 passed) and test (2 failed / 5 passed) summaries
and the 13-stage timeline equal `GET /jobs/{id}`. No hard-coded numbers; the "Agent pool /
Quality gates" tile shows "—  Not implemented in this phase".

## 4. Defects found and fixed

| # | Severity | Defect | Fix (commit) |
|---|---|---|---|
| 1 | High | Fixture ref path traversal: `Path(refs_dir) / "/etc"` escaped the fixtures directory on the control plane (`FixtureRefResolver`) and the worker (`FixtureSourceFetcher`), which would then hash, copy and scan arbitrary directories. Dev-only feature, real read primitive. | Reject `/`-prefixed, `//`, `-`-prefixed refs; verify `resolve()` stays under `<fixture>/refs` (f5335c9) |
| 2 | High | Cancellation could hang forever: `confirm` waited for every worker run to report destroyed; a crashed worker never does. | `TaskQueue.reap_orphaned_worker_runs`: no heartbeat for one lease TTL → `presumed_dead`, audited; called from the scheduler's reap step (51d61e7). Verified by the restart test. |
| 3 | High | Redaction missed `"password": "…"` JSON/YAML shapes, `AQS_*_TOKEN=…`, `X-Exec-Token`, `Bearer` outside `Authorization`, private-key blocks, Slack/Anthropic/OpenAI/`github_pat_` tokens. | Extended, ordered pattern list; 13 parametrised cases (f5335c9) |
| 4 | High | After upgrading FastAPI to 0.162, `POST /repositories` right after `POST /projects` answered 404: FastAPI ≥ 0.118 runs the `get_db` commit after the response unless `scope="function"`. Observed live, not in TestClient. | Every `Depends(get_db)` uses `scope="function"`; unit test guards the pattern (b65357e) |
| 5 | High (deps) | starlette 0.46.2 (8 advisories), pytest 8.4.2, vitest 2.1.3 (tinypool RCE), vite 5.4.10, postcss 8.4.47, react-router-dom 6.26.2, eslint 9.13. | Bumped and re-locked; CI/Dockerfile pin uv 0.13.5 for the new lock format (ee12ef7) |
| 6 | Medium | `git ls-remote` / `git fetch` followed HTTP redirects → a vetted host could redirect to an internal address. | `-c http.followRedirects=false` on both (f5335c9) |
| 7 | Medium | No security headers; evidence download served with worker-supplied media types; HTML report without CSP. | `SecurityHeadersMiddleware` + report CSP (f5335c9) |
| 8 | Medium | Dev-auth query parameters accepted on every endpoint. | Only on `…/events` (f5335c9) |
| 9 | Medium | No startup diagnostics for dangerous configuration. | `Settings.startup_warnings()` logged and exposed in `/system/capabilities` with the `501` list (51d61e7) |
| 10 | Medium | Docker image lacked `git` and the exec package, so `AQS_EMBEDDED_EXEC_WORKER` in Compose could not work. | Dockerfile from repo root, `embedded` extra (66c843b) — unverified, no Docker |
| 11 | Low | `safe_extract_tar` containment by string prefix; backslashes/drive letters in member names. | `Path.is_relative_to`, reject `:` and `\` (f5335c9) |
| 12 | Low | `uvicorn`/`mypy` launchers and `_multiprocessing` blocked by Windows App Control. | `python -m qaswarm.api.serve`, Makefile uses `python -m mypy`; documented (b65357e) |

Reviewed and found sound (no change): role checks on every router (`require_role` for writes,
evidence, audit; `get_principal` elsewhere), org scoping on every row lookup (`org_id` filters in
jobs/repositories/projects/evidence/audit), idempotency keys (per principal, 24 h, body-hash
reuse check), double result submission for one attempt (second → `409 lease_lost`, nothing
persisted; now tested), lease ownership checks on every worker call, worker-result schema
validation (invalid → attempt failed E-EXEC-004, retried within budget), task wall-clock
enforcement on both sides, HTML report escaping, evidence immutability and integrity check on
read, pytest gate (`executes_repository_code` refused unless opted in), secret-scan masking.

## 5. Known defects and limitations (open)

- **Shared-database interference.** Two processes (or two test runs) on one database truncate
  each other's data; seen when sibling sessions shared `qaswarm_test`. Not a code defect; now
  documented. Workers also share one task queue across every API connected to the same database.
- **Worker id reuse.** Every embedded worker is `exec-embedded`; two embedded workers on one
  database are indistinguishable in `worker_runs`. Set `AQS_EXEC_WORKER_ID` for separate hosts.
- **Dashboard counts** come from the first page of each list (limit 20 for jobs). Correct for the
  demo; a `count` endpoint is needed for large organizations.
- **Stale UI copy** (owned by the Phase 2 web-polish session; left untouched here to avoid merge
  conflicts): "syntactic validation only (slice 1a)" on the Repositories tile, "Phase 1a" /
  "only slice 1a behaviour is implemented" footers, the empty-state text "intake arrives in slice
  1b", and the sample-org banner "no repository code executed", which is no longer literally true
  when `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true`. The header pill does say
  "repository code runs UNSANDBOXED (dev only)".
- **Repository dependencies are not installed** before `pytest` (slice 1c), so real repositories
  usually end with `error` on collection — honest, but not useful yet.
- `GET /jobs/{id}/test-executions` has no cursor (limit only); `X-Test-Counts` gives totals.

## 6. Security risks that remain

| Risk | Status |
|---|---|
| Process runtime is **not a sandbox** (SEC-003/004): no network, FS, CPU or memory isolation | Blocker. `pytest` refused by default; opt-in only on disposable hosts. |
| No authentication beyond dev headers (SEC-009/010) | Blocker. `AQS_DEV_AUTH=false` makes the API unusable, `true` makes every caller an admin. |
| DNS rebinding between the intake check and `git ls-remote` (TM-07) | Residual; redirects now disabled. Mitigate with egress filtering on the API host. |
| No rate limiting on `/api/v1` or `/internal/v1/exec` | Open. |
| Exec token is a single shared secret, no rotation, no per-worker identity | Open (design: mTLS/SPIFFE later). |
| Audit table not protected at the database level | Open (`revoke UPDATE/DELETE`). |
| Evidence retention / deletion not implemented | Open. |
| Single organization bound to the first row | Open until OIDC/RBAC. |

## 7. Placeholders and deterministic adapters

- **Planner:** deterministic template (`qaswarm.planning.template`), no LLM, no plan approval.
  Deep security and any performance profile produce a warning, not tasks.
- **Analysis/reporting:** `analyzing` and `reporting` are pass-through stages; `verdict` is
  always `null`; HTML report says "Verdict: not evaluated". No findings, DCS, gates.
- **Runtime:** `SubprocessRuntime` (`isolation = "process"`); `DockerRuntime` reports unavailable.
- **Engines:** four deterministic engines; `pytest` is the only one executing repository code.
- **501 endpoints** (from `GET /system/capabilities.not_implemented`):

| Endpoint | Planned slice |
|---|---|
| `POST /api/v1/repositories/{repository_id}/validate` | 1b |
| `POST /api/v1/targets`, `POST /api/v1/targets/{target_id}/authorizations` | 2b |
| `GET /api/v1/jobs/{job_id}/plan`, `POST /api/v1/jobs/{job_id}/plan/approval` | 2c |
| `GET /api/v1/jobs/{job_id}/findings` | 2a |
| `GET /api/v1/findings/{finding_id}`, `POST …/triage`, `GET …/evidence` | 2b |
| `GET /api/v1/jobs/{job_id}/performance-runs` | 3b |
| `GET /api/v1/jobs/{job_id}/mutation-runs` | 3c |
| `GET /api/v1/jobs/{job_id}/patches`, `POST /api/v1/patches/{patch_id}/review`, `POST …/verifications`, `GET /api/v1/verifications/{verification_id}` | 3d |
| `GET /api/v1/jobs/{job_id}/quality-gates`, `POST /api/v1/jobs/{job_id}/release-decision` | 2d |
| `GET /api/v1/jobs/{job_id}/report?format=pdf|sarif|junit` | 2d |

## 8. Recommended deployment steps (trusted network only, today)

1. PostgreSQL 16 with a dedicated user and password; `alembic upgrade head`; `python -m qaswarm.db.seed`.
2. API: `AQS_ENVIRONMENT=staging`, `AQS_DEV_AUTH=true` only behind a network boundary that is
   itself authenticated, `AQS_EXEC_TOKEN` ≥ 32 random chars, `AQS_EVIDENCE_DIR` on a volume,
   `AQS_CORS_ORIGINS` = UI origin. Start with `python -m qaswarm.api.serve` (or uvicorn where it
   runs); check the startup log for `configuration:` warnings.
3. Scheduler: one `python -m qaswarm.workflow.scheduler` process, supervised.
4. Workers: `python -m qaswarm_exec` on disposable hosts with `git`, no database route, outbound
   limited to Git hosts; `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION` stays `false` unless the host
   is throwaway.
5. Web: `npm run build`, serve `dist/` behind the same origin with `/api`, `/healthz`, `/readyz`
   proxied to the API.
6. Monitor `/readyz`, the JSON logs (`worker runs presumed dead`), and jobs stuck in `cancelling`.
7. Go through `docs/build/RELEASE-CHECKLIST.md`; sections 3 and 4 contain the blockers.

## 9. Deferred / future work

- Slice 1c sandbox runtime (Docker/gVisor), dependency-fetch phase, egress policy — the single
  most important item.
- Slice 3e OIDC + RBAC, then per-org principals and rate limiting.
- Web: stale copy listed above; count endpoints; vitest 5 / vite 6 / tailwind 4 upgrade.
- Compose end-to-end run and Kubernetes manifests on a machine with Docker.
- Evidence retention job, DB-level audit protection, exec token rotation.
- `POST /repositories/{id}/validate` (1b) so registration can resolve the default branch without
  creating a job.

## 10. Commands

```bash
make check                 # lint + typecheck + tests + web build
make migrate-roundtrip     # alembic up/down/up
make audit                 # pip-audit + npm audit
make dev-api | make scheduler | make exec-host | make dev-web
```

Commits on `phase6-hardening`: 5df41db plan · f5335c9 security · 51d61e7 workflow/config ·
ee12ef7 deps · b65357e api session scope + serve · 66c843b docs/config · (this report).
