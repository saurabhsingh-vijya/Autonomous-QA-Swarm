# Phase 4 plan — Advanced testing capabilities

Branch: `phase4-advanced-testing` (from `feature/mvp-continue` @ a942f02). Source of truth:
`docs/design/`. This phase extends the Phase 2 check-engine architecture with API, browser,
safe security and bounded performance checks against **explicitly configured, authorised
targets**, a reusable test configuration model, richer evidence, and a regression rerun endpoint.
Existing plans and engines stay byte-for-byte the same when none of the new configuration is
present.

## Decisions

1. **Targets are explicit.** A check that talks to a network target needs either a registered
   `TargetEnvironment` with an unexpired `TargetAuthorization` (`POST /targets`,
   `POST /targets/{id}/authorizations`, HA-01, FR-050) referenced by `target_id` on the job, or the
   worker-started **local fixture target** (`exec/fixtures/sample-target-app`, bound to
   `127.0.0.1` on an ephemeral port, the Phase 4 stand-in for the design's ephemeral in-sandbox
   target). A job that names a target without a valid attestation ends `blocked` during
   `validating` with 0 worker runs (AC-149).
2. **Egress policy in the worker** (`qaswarm_exec.targets.policy`): externally supplied target
   hosts that resolve to loopback, RFC1918, link-local (incl. `169.254.169.254`), CGNAT, IPv6
   ULA/loopback or unspecified addresses are refused unless `AQS_EXEC_ALLOW_LOCAL_TARGETS=true`.
   The address is re-resolved and re-checked by the HTTP transport immediately before every
   connection; redirects are followed manually (max 5) and every hop is re-checked and must stay
   on the authorised host set. The browser engine adds Chromium `--host-resolver-rules` so only the
   target host resolves, plus request/response interception. Residual DNS-rebinding risk between
   resolution and connect is documented, not hidden.
3. **Redaction everywhere.** `qaswarm_exec.testing.redact` masks `Authorization`, `Cookie`,
   `Set-Cookie`, `X-API-Key`, `Proxy-Authorization`, bearer/JWT/token-shaped values and URL
   userinfo in request/response summaries, console logs and failure messages *before* evidence
   leaves the worker; the Evidence Store's redaction still runs on top.
4. **Test configuration model** (`qaswarm_exec.testing.config`): `Environment` (base URL,
   headers, variables), `TestSuite` (kind `api` | `browser`, scenarios, test data),
   `Scenario` (steps), `Step` (request or browser action), `Assertion` (`status`, `header`,
   `json_path`, `body_contains`, `response_time_ms`, `text`, `title`, `visible`, `url`).
   Suites come from the repository snapshot (`.qaswarm/tests/*.yaml|yml|json`), from explicit
   paths, or inline in the job input `testing.api.inline` / `testing.browser.inline`.
   Values support `${var}` substitution from environment variables, test data and captured
   values (`capture: {name: "$.json.path"}`). Loading is validating and bounded (sizes, counts).
5. **New engines** (registered in `tools/registry.py`, outcome vocabulary unchanged):
   - `api_tests` — declarative HTTP steps, status/header/JSON-path/body/response-time assertions,
     one `TestResult` per step (`suite::scenario::step`), response-time recording, evidence
     `api_test_report` (redacted request/response summaries, timings).
   - `browser_tests` — Playwright for Python + Chromium (installed and verified on this machine:
     Playwright 1.64.1, Chromium 156). Steps `goto`, `click`, `fill`, `press`, `wait_for`, `expect`,
     `screenshot`. Evidence: screenshots (`image/png`), console log (`browser_console`),
     per-step timings. If Playwright or the browser is unavailable the check ends `skipped` with
     the reason.
   - `security_checks` — read-only, non-destructive GETs only: security headers (HSTS on https,
     X-Content-Type-Options, X-Frame-Options / CSP frame-ancestors, CSP, Referrer-Policy,
     Permissions-Policy), cookie flags (Secure/HttpOnly/SameSite), redirect sanity (same host,
     bounded hops, no downgrade), verbose error bodies (stack traces, framework banners on a
     not-found probe path and on configured paths), `Server` / `X-Powered-By` disclosure.
     Profiles `quick` (headers + cookies on `/`) and `standard` (+ redirect sanity, error-body
     probe, configured paths). Findings are informational results, **not** a certification.
   - `performance_probe` — bounded closed-loop probe with hard caps: profile `smoke`
     (≤ 50 requests, concurrency 2, ≤ 10 s) and `baseline` (≤ 200 requests, concurrency 5,
     ≤ 30 s), every limit configurable per job but clamped by worker caps
     (`AQS_EXEC_PERF_MAX_REQUESTS=500`, `AQS_EXEC_PERF_MAX_CONCURRENCY=10`,
     `AQS_EXEC_PERF_MAX_DURATION_SECONDS=60`, output cap). Reports p50/p95/p99, throughput, error
     rate; fails only when configured thresholds are exceeded or the error rate is ≥ 50 %.
     Baseline (HA-03 in the design) is planned only against the worker-local fixture target in
     this build; against registered targets it produces a warning, not a task.
6. **Planner profiles** (`qaswarm.planning.template`): unchanged output without new config.
   With a target in play (job `target_id` or a `testing` block): `security: quick|standard` adds
   `security_checks`, `performance: smoke|baseline` adds `performance_probe`,
   `testing.api` adds `api_tests`, `testing.browser` adds `browser_tests`. Task inputs carry the
   resolved `target` descriptor (`local_fixture` or `registered` with base URL and allowed hosts)
   and the per-engine configuration; secrets never appear in task inputs.
7. **Job inputs.** `POST /jobs` accepts optional `target_id` and `testing` (strict schema).
   Stored in a new `jobs.inputs` JSONB column and included in the duplicate-detection hash.
8. **Regression rerun.** `POST /jobs/{job_id}/rerun` `{ "engines": [...] }` creates a new job
   for the same repository, ref, profiles and inputs, restricted to the selected engines
   (`env_prepare` always runs), records `inputs.rerun = {of_job, engines}` and returns the new job
   plus a `compare` link to `GET /jobs/{new}/compare?with={old}`. Added to the contract table's
   `ADDITIONAL` list as a deviation for review.
9. **Honesty.** `GET /system/capabilities` lists the new engines; browser availability is
   reported by the worker in the environment manifest and the check summary.

## Files

Exec (`exec/src/qaswarm_exec/`): `targets/policy.py`, `targets/http.py`, `targets/local_app.py`,
`testing/{config,jsonpath,redact}.py`, `tools/{api_tests,browser_tests,security_checks,performance_probe}.py`,
`tools/base.py` (+`settings` on `CheckContext`), `tools/registry.py`, `host/{worker,runner}.py`
(flags, manifest), `exec/fixtures/sample-target-app/app.py`, `exec/fixtures/sample-web-app/`
(suites in `.qaswarm/tests/`), `exec/pyproject.toml` (pyyaml, optional `browser` extra).

Backend (`backend/src/qaswarm/`): `db/models.py` (+TargetEnvironment, TargetAuthorization,
Job.inputs), migration `20261024_1800_phase4_targets_and_inputs.py`, `api/schemas.py`,
`api/routers/targets.py`, `api/services/targets.py`, `api/routers/jobs.py` (+rerun),
`api/services/jobs.py`, `planning/template.py`, `workflow/scheduler.py` (target policy at
admit, plan with target), `api/contract_table.py`, `api/routers/system.py`, `config.py`.

Tests: `tests/unit/test_phase4_engines.py` (policy, redaction, config loader, JSON path, API engine
against the fixture app, security + perf engines, browser engine, negative cases: assertion
failure, blocked target, redirect to a private host, timeout), `tests/integration/test_phase4_pipeline.py`
(targets API, blocked job, full pipeline with API/browser/security/perf checks against the local
fixture target, rerun + compare).

## Risks

- Playwright/Chromium is installed here; CI images need `python -m playwright install chromium`
  (documented). The engine degrades to `skipped` with a reason.
- Windows: fixture app subprocess start/stop and ephemeral-port readiness (polled health check,
  bounded).
- Shared embedded Postgres with another session: integration tests run one process at a time.
- Out of scope (Deferred): HA-02/HA-03 approval flow, DAST/ZAP, k6, PerformanceRun entity and
  `GET /jobs/{id}/performance-runs`, findings promotion, target egress gateway.
