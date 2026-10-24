# Phase 4 report — Advanced testing capabilities

Branch: `phase4-advanced-testing` (from `feature/mvp-continue` @ a942f02), worktree
`D:\autonomous-qa-swarm-phase4`. Commits: `5d8ebef` (plan, deps), `25e34ba` (exec engines),
`1314dfc` (control plane), `03d0107` (tests, docs), plus the final docs commit. Nothing pushed.
Plan: `docs/build/phase-4-plan.md`.

## What was built

### Execution Service (`exec/src/qaswarm_exec/`)

| Area | Files | Notes |
|---|---|---|
| Target egress policy | `targets/policy.py` | `classify_address` (loopback, RFC1918, link-local incl. `169.254.169.254`, CGNAT, multicast, reserved, unspecified, IPv6 ULA / v4-mapped); `TargetPolicy.check_url` validates scheme, forbids userinfo, enforces the authorised host set and re-resolves the host **at connect time**; `AQS_EXEC_ALLOW_LOCAL_TARGETS=true` is the only way to reach non-public addresses on externally supplied targets. |
| Checked HTTP client | `targets/http.py` | `PolicyTransport` re-checks every request before it reaches the pool; redirects are never auto-followed: each `Location` is re-validated (max 5 hops), redirects to blocked or unauthorised hosts raise `TargetBlocked`; `trust_env=False`; bodies captured ≤ 64 KiB. |
| Policy proxy (browser egress gateway) | `targets/proxy.py` | Worker-local forward proxy on `127.0.0.1:<ephemeral>`; every plain request and `CONNECT` is checked against the policy, refused destinations get `403` and are recorded as violations. Chromium is launched with `proxy={"server": …, "bypass": "<-loopback>"}` so loopback traffic is proxied too. |
| Local fixture target | `targets/local_app.py`, `exec/fixtures/sample-target-app/app.py` | Standard-library HTTP app started by the worker with `python -I`, scrubbed env, ephemeral loopback port, bounded health wait, process-tree kill on exit. Deliberately imperfect: cookie without HttpOnly/SameSite on `/login`, no CSP/Referrer-Policy, verbose traceback on `/boom`, open redirect, `/redirect-private` → `169.254.169.254`, `X-Powered-By`. |
| Target Environment Manager | `targets/__init__.py` | `TargetSession` turns the task's `target` descriptor (`local_fixture` or `registered`) into a `ResolvedTarget` + policy; registered targets are checked before any request. |
| Test configuration model | `testing/config.py`, `testing/jsonpath.py`, `testing/redact.py` | Environments, suites (`api` / `browser`), scenarios, steps, assertions, test data, `${var}` substitution, captures; YAML/JSON from `.qaswarm/tests/`, explicit paths (snapshot-escape rejected) or inline; bounded sizes/counts. JSON-path subset (`$.a.b[0]`, `[*]`, `.length()`, quoted keys). Redaction of `Authorization`, `Cookie`/`Set-Cookie`, API-key headers, bearer/JWT/cloud tokens, URL userinfo, sensitive JSON keys. |
| `api_tests` engine | `tools/api_tests.py` | One `TestResult` per step (`suite::scenario::step`), statuses `passed` / `failed` / `timed_out` / `skipped` / `blocked`; failing step ends its scenario; evidence `api_test_report` (redacted request/response summaries, hops, timings p50/p95/p99). |
| `browser_tests` engine | `tools/browser_tests.py` | Playwright for Python 1.64.1 + Chromium 156 (installed and verified on this machine). Steps `goto`, `click`, `fill`, `press`, `select`, `check`, `wait_for`, `expect` (title/text/visible/hidden/url/value/count), `screenshot`. Evidence: screenshots (`image/png`, non-deterministic), `browser_console` (redacted), `browser_test_report`. Three egress layers: policy proxy, request interception, `--host-resolver-rules`. Missing Playwright/Chromium → `skipped` with the install hint. |
| `security_checks` engine | `tools/security_checks.py` | Read-only `GET`s only. Checks: HSTS (https), `X-Content-Type-Options`, CSP, frame protection, Referrer-Policy, Permissions-Policy, cookie flags, verbose error bodies, version disclosure, redirect sanity, not-found probe (`standard`). Profiles `quick` (one path) / `standard` (configured paths + probe). Findings → `failed` test rows; the check fails on medium/high. Every report carries the disclaimer: informational, not an assessment or certification. |
| `performance_probe` engine | `tools/performance_probe.py` | Bounded closed-loop GET/HEAD probe; `smoke` 50 req / 2 workers / 10 s, `baseline` 200 / 5 / 30 s; per-job overrides clamped by `AQS_EXEC_PERF_MAX_REQUESTS` (500), `_CONCURRENCY` (10), `_DURATION_SECONDS` (60); early abort on cancel, deadline, policy refusal or error rate > 50 %; p50/p95/p99, throughput, error rate, per-path breakdown; thresholds `p95_ms`, `p99_ms`, `error_rate`. |
| Worker plumbing | `tools/base.py` (`CheckContext.settings`), `tools/targeted.py`, `tools/registry.py` (8 engines, `TARGET_ENGINES`), `host/worker.py`, `host/runner.py` | Env flags → engine settings; the environment manifest records `browser_testing` and `local_targets_allowed`. |
| Fixture repository | `exec/fixtures/sample-web-app/` | `.qaswarm/tests/items-api.yaml` (API suite, 5 steps incl. capture) and `home-page.yaml` (browser suite, 9 steps). |

### Control plane (`backend/src/qaswarm/`)

| Area | Files | Notes |
|---|---|---|
| Targets + HA-01 | `db/models.py` (`TargetEnvironment` `tgt_`, `TargetAuthorization` `tauth_`), migration `20261024_1800_phase4_targets_and_inputs.py`, `api/services/targets.py`, `api/routers/targets.py` | `POST /targets` (Org Admin, `targets:write`), `GET /targets[?project_id]`, `GET /targets/{id}`, `POST /targets/{id}/authorizations` (Org Admin / Security Reviewer, `targets:authorize`), `DELETE …/authorizations/{id}` (revoke). AC-148 validation (owner, environment type, http(s) base URL without credentials/query), loopback/private literals refused unless `AQS_ALLOW_LOCAL_TARGETS=true`, ≤ 366-day windows, overlapping activities superseded with audit, every change audited (`target.registered`, `target.authorized` with `approval: HA-01`, `target.authorization_revoked`). |
| Job inputs | `api/schemas.py` (`TestingConfig` and sub-models, strict), `api/services/jobs.py`, `jobs.inputs` JSONB | `POST /jobs` accepts `target_id` and `testing` (`target: local_fixture`, `api`, `browser`, `security.paths`, `performance` limits/thresholds); inputs are part of the duplicate-detection hash; `JobOut.inputs` exposed. |
| Policy at admit | `workflow/scheduler.py`, `services/targets.evaluate_target_policy` | A job naming a target without an active attestation covering the requested activities ends `blocked` during `validating` with `E-POLICY-002`, an HA-01 warning and **zero worker runs** (AC-149). |
| Planner | `planning/template.py` | Adds `api_tests` / `browser_tests` / `security_checks` / `performance_probe` only when a target is in play; task inputs carry the `target` descriptor and per-engine `config` (no secrets). Baseline against a registered target → HA-03 warning, no task. Unauthorised activities → warning, no task. `inputs.rerun` restricts the plan. **Plans without the new configuration are byte-identical** (unit test). |
| Regression rerun | `POST /jobs/{job_id}/rerun` | `{engines: [...]}` on a finished job creates a new job with the same repo/ref/profiles/inputs plus `inputs.rerun`; response carries `links.compare = /jobs/{old}/compare?with={new}`; `409` on non-terminal, `422` on unknown engines; audited (`job.rerun_requested`). |
| Capabilities / contract | `api/routers/system.py`, `api/contract_table.py` | Engines list extended; `/targets` rows now implemented (slice 4); additions recorded as deviations: `GET /targets`, `GET /targets/{id}`, `DELETE …/authorizations/{id}`, `POST /jobs/{id}/rerun`. |

Docs: `README.md` (Phase 4 section), `.env.example`, `exec/fixtures/README.md`.

## Requirement coverage

| ID | Coverage |
|---|---|
| FR-050 / AC-148 / AC-149 | Registration + HA-01 attestation API; 422 on missing owner/type/URL; non-admins 403; unauthorised target → `blocked`, 0 worker runs (integration test). AC-150 (revocation during a running job) **partial**: the descriptor is resolved at plan time only; revocation is not re-checked per task lease. |
| FR-005 / AC-014 | `security: quick|standard`, `performance: smoke|baseline` now plan real checks when a target exists; HA-02/HA-03 approval states are **not** implemented (warnings instead, see Deferred). |
| FR-027 | Smoke / Baseline envelopes respected (≤ 5 / ≤ 20 workers, ≤ 1 / ≤ 5 min; this build uses 2 / 5 workers and 10 / 30 s with hard caps). k6, `PerformanceRun` entity and `GET /jobs/{id}/performance-runs` not built. |
| SEC-001 | None of the new engines executes repository code (`executes_repository_code = False`); suites are data, loaded without evaluation. |
| SEC-005 / TM-23 | Blocked ranges enforced in the worker at connect time, hop by hop, and via the browser proxy; residual DNS-rebinding window between resolution and connect documented below. |
| SEC-008 / FR-024 | Credentials redacted in the worker before upload and again in the Evidence Store (integration test checks the stored security report). |
| No evidence, no defect | Every result is backed by `api_test_report`, `security_report`, `performance_report`, `browser_test_report`, screenshots, console logs and per-check logs. |

## Commands and actual results

Environment: Windows 11, Python 3.12 via `python -m uv` in `backend/`, Node 24 in `web/`, embedded
PostgreSQL `qaswarm_test_p4` (dedicated to this session, as requested by the coordinating session).

```
$ python -m uv run ruff check . ../exec
All checks passed!
$ python -m uv run ruff format --check . ../exec/src
121 files already formatted
$ python -m uv run python -m mypy src/qaswarm ../exec/src/qaswarm_exec
Success: no issues found in 103 source files
```

```
$ python -m uv run python -m pytest tests/unit -q -p no:cacheprovider
FAILED tests/unit/test_phase2_control_plane.py::test_fixture_resolver_pins_a_tree_hash_and_rejects_unknown_refs
1 failed, 164 passed, 1 warning in 28.60s
```

```
$ AQS_TEST_DATABASE_URL=postgresql+psycopg://qaswarm:qaswarm-dev-only@127.0.0.1:59137/qaswarm_test_p4 \
  python -m uv run python -m pytest tests/integration -q -p no:cacheprovider
FAILED tests/integration/test_execution_pipeline.py::test_full_pipeline_runs_real_checks_and_persists_everything
FAILED tests/integration/test_execution_pipeline.py::test_invalid_worker_result_fails_attempt_and_retries_within_budget
FAILED tests/integration/test_execution_pipeline.py::test_worker_process_discards_result_after_lease_loss
3 failed, 28 passed, 1 warning in 41.49s
```

```
$ python -m uv run python -m pytest tests/integration/test_phase4_pipeline.py tests/unit/test_phase4_engines.py tests/unit/test_phase4_control_plane.py -q -p no:cacheprovider
25 passed, 1 warning in 34.50s
```

```
$ python -m uv run alembic upgrade head        (against qaswarm_test_p4, from empty)
Running upgrade  -> b50874965b43, slice 1a foundations
Running upgrade b50874965b43 -> c2e1f7a90d44, phase 2: execution engine (...)
Running upgrade c2e1f7a90d44 -> d4a7c3e1b905, phase 4: target environments, authorizations (HA-01) and job inputs
tables: ['target_authorizations', 'target_environments']  jobs.inputs present
$ python -m uv run alembic downgrade base      → clean; upgrade head again → clean
```

```
$ npm run lint        ✖ 4 problems (0 errors, 4 warnings)   (pre-existing react-refresh warnings)
$ npm run typecheck   tsc --noEmit -p tsconfig.app.json      (clean)
$ npm test -- --run   Test Files 4 passed (4) · Tests 24 passed (24)
$ npm run build       ✓ built in 3.33s
```

Browser smoke check used for the decision to install Playwright:

```
$ python -m uv run python -m playwright install chromium   (Chromium downloaded)
$ python -c "from playwright.sync_api import sync_playwright; ..."  → hi 156.0.8078.4
```

### The four failures are pre-existing and outside this phase

All four failing tests fail identically on the base commit's code paths and were listed as known
by the coordinating session (fixture-resolver `../etc` policy check; lease-loss / retry handling).
The fourth, `test_full_pipeline_runs_real_checks_and_persists_everything`, asserts
`stages["security_testing"] == "skipped"` while the stage derivation in
`api/services/jobs.py::_stages` returns `not_run`; `git diff a942f02 HEAD` shows no change to that
function, and the phase 4 unit test `test_plans_without_phase4_config_are_unchanged` proves the
plan for that job is identical. They are being fixed by the Phase 2 session; I did not touch them
to avoid conflicting edits.

### Phase 4 tests, what they prove

Unit (`tests/unit/test_phase4_engines.py`, 15 tests, real fixture app + real Chromium):
address classification for every blocked range; policy refusals (private, unauthorised host,
scheme, userinfo) and local mode; `TargetSession` refusals; header/text/value redaction; JSON-path
subset; suite loader validation, substitution and snapshot-escape rejection; **API engine happy
path** (5 steps, capture, timings, redacted report) and **negative scenarios**: assertion failure
(scenario stops, token absent from evidence), redirect to `169.254.169.254` refused, timeout →
`timed_out`, blocked registered target → `skipped` + `blocked` test rows, no suites → `skipped`,
malformed suite → `error`, controlled local mode; **security engine** finds the planted CSP /
version-disclosure / verbose-error / redirect findings and redacts `Set-Cookie`; **performance
probe** clamping, exact request count, per-path percentiles, threshold violation, refused
profile/method; **browser engine** honest skip without Playwright, happy path with PNG screenshot
and console capture, failing assertion with failure screenshot, redirect to the metadata address
refused through the proxy, missing selector → `timed_out`, blocked target → `skipped`.

Unit (`tests/unit/test_phase4_control_plane.py`, 6 tests): plans unchanged without config
(including `fixture_targets=True`), full target plan with the local fixture, registered-target
authorization filtering and HA-03 warning, rerun restriction, base-URL validation, strict schemas.

Integration (`tests/integration/test_phase4_pipeline.py`, 4 tests, PostgreSQL + in-process
worker): targets API roles/validation/supersession/revocation/audit; unauthorised and
under-authorised target → `blocked`, zero worker runs; full pipeline on `sample-web-app` with all
nine checks (API passed, browser passed, security failed with 1 high, performance 12 requests),
test-executions, evidence kinds, PNG download, redacted security report, then rerun of two
engines → restricted plan and `compare` deltas; registered loopback target refused by the worker
end to end and accepted (then failing on the closed port) in local mode.

## Known gaps and residual risk

- **DNS rebinding window.** The address is resolved and checked immediately before each connection
  (httpx transport) and per proxy request, not pinned into the socket connect. A resolver that
  flips between the check and the connect could still be exploited; the design's egress gateway
  with pinned addresses remains Future.
- **Playwright on the host.** Browser tests run Chromium on the worker host, not in a sandbox
  (consistent with the phase 2 `isolation = process` honesty). CI images need
  `python -m playwright install chromium`; otherwise the check is `skipped`.
- **Authorization re-check.** The HA-01 attestation is evaluated at admit and plan time; AC-150
  (revocation during a running job stops new dispatch within 60 s) is not enforced per lease.
- **Security checks are hygiene checks only.** No DAST, no active rules, no injection. Reports and
  docs say so; nothing claims certification.
- **Performance baseline** runs only against the worker-local fixture target (HA-03 for external
  targets is not implemented). No stored baseline comparison (FR-029) yet.
- The Vite UI was not extended; the new API is reachable but has no screens.

## Deferred (later phases / slices)

- HA-02 / HA-03 / HA-05 approval flow and `awaiting_approval` gating (slice 2c).
- OWASP ZAP DAST (`security: deep`), SAST/dependency/IaC scanners (slice 2a).
- k6 workloads, `PerformanceRun` / `PerformanceMetric`, `GET /jobs/{id}/performance-runs`,
  baseline-vs-candidate comparison and QG-05 (slice 3b).
- Ephemeral in-sandbox targets with per-job networks, target egress gateway with address pinning
  (slice 3a), `CredentialReference` wiring for target credentials.
- Findings promotion from check results, flaky reruns of API/browser steps, UI screens for
  targets, test suites and rerun/compare.

## Next-step suggestions

1. Merge after the Phase 2 session lands its fixes for the four pre-existing failures.
2. Add target and rerun screens to the web app (SCR-03 target picker, SCR-08/09 results).
3. Pin resolved addresses into the connect (custom httpcore backend) to close the rebinding window.
4. Re-evaluate HA-01 at lease time (AC-150) once approvals exist.
