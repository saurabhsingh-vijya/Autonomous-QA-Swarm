# Phase 6 plan — Hardening and release readiness

Branch `phase6-hardening` (cut from `feature/mvp-continue` @ 9d185ad, Phase 2 execution engine).
Source of truth: `docs/design/`. No new product features; stabilise, verify, document.

## Baseline (measured at 9d185ad, Windows 11, no Docker, embedded PostgreSQL 16)

| Suite | Result |
|---|---|
| backend `pytest tests` (unit + integration) | 171 passed |
| `ruff check`, `ruff format --check` | clean |
| `mypy src ../exec/src` | clean (88 files) — `uv run mypy` launcher is blocked by Windows App Control; `uv run python -m mypy` works |
| web `tsc`, `eslint` | clean, 5 react-refresh warnings |
| web `vitest` | 25 passed |
| web `vite build` | ok |
| `alembic upgrade head → downgrade base → upgrade head` | ok |

## Findings to fix in this phase (ordered by severity)

| # | Severity | Finding | Fix |
|---|---|---|---|
| H1 | High | Fixture ref path traversal: `Path(refs_dir) / ref` with a ref such as `/etc` or `/Users` resolves outside the fixtures directory (`pathlib` replaces the base on an absolute segment). Affects `qaswarm.intake.resolvers.FixtureRefResolver` (control plane reads the tree) and `qaswarm_exec.host.source.FixtureSourceFetcher` (worker copies and scans it). Dev-only feature, still a real read primitive. | Reject refs starting with `/`, containing `\\` or `:`, and verify the resolved path stays under `<fixtures>/<name>/refs` |
| H2 | High | Cancellation can hang forever: `confirm` waits for every `WorkerRun.destroyed_at`; a worker that dies (or an API restart with the embedded worker) never reports destruction, so the job stays `cancelling`. | Scheduler marks worker runs whose task attempt has had no heartbeat for longer than the lease TTL as destroyed with outcome `presumed_dead` (audited); reaper closes runs of expired leases |
| H3 | High | Log/evidence redaction misses JSON-shaped secrets (`"password": "…"`, `"token": "…"`), private-key blocks, Slack / Anthropic / OpenAI keys, `Bearer` outside an `Authorization` header. | Extend `telemetry.logging._REDACTION_PATTERNS`, keep order deterministic, add tests |
| H4 | High (dev deps) | npm audit: vitest 2.1.3 → tinypool prototype-pollution RCE (critical), vite ≤5.4.20, postcss ≤8.5.22, react-router-dom ≤6.30.2, eslint. pip-audit: starlette 0.46.2 (8 advisories), pytest 8.4.2. | Bump within major versions; re-lock; re-run suites |
| M1 | Medium | Intake `git ls-remote` and worker `git fetch` follow HTTP redirects (`http.followRedirects=initial`), so a host passing the DNS check can redirect to an internal address. | `-c http.followRedirects=false` on both |
| M2 | Medium | No security response headers; evidence download serves a worker-supplied media type. HTML report served without CSP. | `X-Content-Type-Options: nosniff`, `Referrer-Policy`, `X-Frame-Options`, CSP on HTML report; `Cache-Control: no-store` on API |
| M3 | Medium | No startup diagnostics: dev auth on, fixture repos on, unsandboxed code execution, embedded worker, exec token unset, default database password are silent. | `Settings.startup_warnings()` logged at startup and exposed in `/system/capabilities.warnings` |
| M4 | Medium | Dev auth accepts `dev_user` / `dev_role` query parameters on every endpoint (only the SSE endpoint needs it). | Accept query-parameter credentials only for `/events` |
| L1 | Low | `safe_extract_tar` containment uses `str.startswith` (prefix confusion). | `Path.is_relative_to` |
| L2 | Low | Stale copy in the web shell ("intake arrives in slice 1b", "syntactic validation only (slice 1a)"). The Phase 2 sibling session owns web polish; recorded here as a hand-over, not changed in this branch to avoid merge conflicts. | Note in shared folder + report |

## Verification plan

1. All suites after each commit (`python -m uv run python -m pytest tests -q`, ruff, mypy, vitest, tsc, eslint, vite build).
2. Migration round-trip again after dependency bumps.
3. Live run: `alembic upgrade head` → seed → uvicorn with embedded scheduler + worker + fixture repos → create project, repository, job → wait for `completed_with_warnings` → `GET /checks`, `/test-executions`, `/evidence`, `/report?format=html`, second job on `fix-rounding` → `/compare`; cancel a job; duplicate submission; idempotent replay; viewer 403; exec API without token (401/503).
4. Web: `npm run build` + `vite preview` against the live API in the browser pane; confirm Dashboard/JobDetail numbers equal API numbers.
5. Clean install: fresh `uv sync` into a temporary `UV_PROJECT_ENVIRONMENT`, fresh `npm ci` (already exercised by the baseline run which created `.venv` from scratch).

## Deliverables

- Code fixes above with tests (`tests/unit/test_phase6_hardening.py`, additions to integration tests).
- `README.md` rewritten for the current build (prerequisites, Windows-without-Docker path, configuration table, tests, troubleshooting, architecture, known limitations).
- `docs/build/RELEASE-CHECKLIST.md`.
- `docs/build/phase-6-report.md` with real command output.

## Out of scope (deferred, recorded in the report)

Sandbox runtime (gVisor/Docker, slice 1c), OIDC (3e), findings/gates/agents (2a–2d), rate limiting, OpenTelemetry export, Kubernetes manifests.
