# RaOne — Autonomous AI-Powered QA Platform

(Originally "Autonomous QA Swarm"; `qaswarm` package names and `AQS_` settings are kept.)

An open-source, self-hostable QA platform in which specialized AI agents, coordinated by a
deterministic workflow engine, plan and run tests against a **pinned commit** inside **disposable
sandboxes**, correlate evidence, propose fixes for human review and independently verify them.

Two principles override everything else:

1. **Agents propose, deterministic services dispose, humans approve.** Agents never execute code,
   never hold credentials and never change a repository.
2. **No evidence, no defect.** Nothing is reported as a confirmed defect without reproducible evidence.

> **Status: Phase 2 execution engine + Phase 3 agent orchestration + Phase 4 target-facing
> engines + Phase 5 defect intelligence, hardened in Phase 6. Not production-ready.**
> What works: register a repository, create a job (optionally with requirement texts, API checks,
> a target and a testing scope), Intake & Pinning (`git ls-remote` → commit SHA), one combined
> plan (Execution Service checks + agent tasks), an Execution Service that fetches the pinned
> snapshot and runs deterministic checks, deterministic agents (requirements analysis, API checks
> against allow-listed local hosts, evidence correlation, quality gates and report), findings with
> evidence, root-cause hypotheses, priority, cross-run history and triage, JSON/HTML reports, run
> comparison, live SSE progress and a hash-chained audit trail. What does **not** exist yet: a
> sandbox runtime (checks run in a plain subprocess on the worker host), OIDC login, reproduction
> runs, patch proposals, a hosted Model Gateway (only an optional local Ollama adapter). Every
> missing endpoint answers `501` with its planned slice; see [Known limitations](#known-limitations),
> `docs/build/phase-6-report.md`, `docs/build/phase-3-report.md`, `docs/build/phase-5-report.md`
> and `docs/build/merge-phase2-report.md`.

The design is the source of truth: [`docs/design/`](docs/design/README.md). Build plan and phase
prompts: [`docs/build/`](docs/build/BUILD_PLAN.md). Phase reports: `docs/build/phase-<id>-report.md`.
Release gate: [`docs/build/RELEASE-CHECKLIST.md`](docs/build/RELEASE-CHECKLIST.md).

## Architecture

```
 browser ──► web (React/Vite, :5173) ──proxy /api──► API (FastAPI, :8000) ──► PostgreSQL 16
                                                        │  ▲                      ▲
                                      scheduler role ───┘  │ /internal/v1/exec    │
                                      (ticks: admit,       │ X-Exec-Token         │ no DB access
                                       plan, reap,         │                      │
                                       advance, confirm)   ▼                      │
                                              Execution Service (qaswarm_exec) ───┘
                                              fetch pinned commit → check engines → evidence
```

| Layer | Package | What it does in this build |
|---|---|---|
| Web UI | `web/` (React 18, TypeScript, Vite, Tailwind, TanStack Query) | Dashboard, Repositories & Projects, New QA Job, Live Job Execution (13-stage timeline, tasks, checks, evidence viewer, SSE), Functional Results, Compare Runs. Every number comes from the API; unbuilt screens say so. |
| API | `backend/src/qaswarm/api` | `/api/v1`: projects, repositories, jobs (idempotent create, cancel, SSE), tasks, checks, test executions, evidence, report, compare, audit events, capabilities. RFC 9457 `problem+json`, correlation IDs, ETags, cursor pagination, security headers. Dev header auth only. |
| Domain / workflow | `qaswarm.domain`, `qaswarm.workflow` | Enums and state machines exactly as the design defines them; PostgreSQL task queue (`FOR UPDATE SKIP LOCKED`, leases, heartbeats, retries with jittered backoff, reaper, dead-worker detection). |
| Intake | `qaswarm.intake` | URL validation (https, allow-listed host, no credentials), DNS resolution with private-address rejection, `git ls-remote` with redirects disabled. Never clones. |
| Planning / reporting | `qaswarm.planning`, `qaswarm.reporting` | One combined plan per job: the deterministic template plan (Execution Service checks, target engines) joined with the agent DAG (requirements → functional/API → evidence → report); plan persisted with a hash, optional HA-05 approval. Deterministic partial report for failed/cancelled jobs. |
| Agents (phase 3) | `qaswarm.agents` | AG-02 Requirements Analysis, AG-03 Functional Testing (skips honestly), AG-04 API Testing (local allow-list, safe methods), AG-08 Evidence Analysis (findings from API checks, failed check engines and failed pytest tests; DCS; facts vs inferences; rule-based root-cause hypotheses with uncertainty), AG-11 QA Reporting (QG-01…QG-08, verdict). Deterministic by default; optional local Ollama adapter for AG-02 proposals. Outputs are schema-validated and persisted. |
| Orchestrator + runner | `qaswarm.workflow.orchestrator`, `.runner` | Plans jobs for the scheduler, dispatches leased agent tasks, persists outputs/evidence/executions/findings/report, reconciles job state (single state advancer), HA-05 approval, cancellation. In-process runner thread (`AQS_RUNNER_ENABLED=true`) or `python -m qaswarm.workflow.runner`. |
| Defects (phase 5) | `qaswarm.defects` | Risk priority with breakdown, cross-run history by fingerprint, suppression carry-over, triage lifecycle (HA-07/HA-08) with audit and ETags. |
| Evidence / audit | `qaswarm.evidence`, `qaswarm.audit` | Content-addressed files under `AQS_EVIDENCE_DIR`, redacted before hashing, capped at 50 MiB; append-only hash-chained audit events. |
| Execution Service | `exec/src/qaswarm_exec` | Leases tasks over HTTP, fetches the pinned commit (`git fetch --depth 1`, hooks/LFS/submodules off, safe tar extract) or a dev fixture, runs engines `snapshot_integrity`, `python_syntax`, `secret_scan` (no code execution) and `pytest` (executes repository code; refused unless explicitly allowed), uploads evidence, submits a schema-validated result, always reports its worker run destroyed. No database access. |

Key documents: `docs/design/05-architecture/03-low-level-design.md` (state machines, task contract,
worker result schema), `docs/design/08-api-specifications/01-api-contracts.md` (API),
`docs/design/10-security-and-threat-model/03-sandboxed-execution.md` (sandbox rules this build
does not yet meet).

## Prerequisites

| Need | Version | Notes |
|---|---|---|
| Python | 3.12.x | Managed by `uv` (`uv python install 3.12`); the project is pinned to `>=3.12,<3.13`. |
| [`uv`](https://docs.astral.sh/uv/) | ≥ 0.13 | The lockfile format needs a current uv. `pip install uv` works on Windows. |
| Node.js + npm | Node 22 (24 in the web Docker image) | `npm ci` reproduces `package-lock.json`. |
| PostgreSQL | 16 | Via Docker Compose, a native install, or an embedded server (see Windows notes). |
| git | any recent | Needed on the API host (`git ls-remote`) and on every worker host (`git fetch`). |
| Docker Desktop / Engine + Compose v2 | optional | Only for the Compose path. Nothing else requires Docker. |

## Quick start A — Docker Compose

```bash
cp .env.example .env
echo "AQS_EXEC_TOKEN=$(python -c 'import secrets;print(secrets.token_urlsafe(32))')" >> .env
docker compose up -d --build    # postgres:16, api (migrates + seeds), scheduler, exec-host, web
```

- UI: <http://localhost:5173> · API docs: <http://localhost:8000/api/v1/docs>
- Health: <http://localhost:8000/healthz> · readiness: <http://localhost:8000/readyz>

Compose runs the API, one scheduler and one Execution Service container (`exec-host`, built from
`exec/`, no database access) and serves the dev fixture repositories
(`https://fixtures.local/local/sample-python-app`, refs `main` and `fix-rounding`). The `pytest`
engine is refused in `exec-host` unless you set `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true`
there; the container is not a sandbox either.

The Compose path was **not executed** during Phase 6 (the build machine has no Docker); the CI
workflow and the Windows path below were. Treat it as untested until the release checklist says
otherwise.

## Quick start B — local processes (Linux, macOS, Windows; no Docker required)

```bash
make setup                       # cd backend && uv sync --all-groups ; cd web && npm ci
# PostgreSQL: docker compose up -d postgres   OR   any PostgreSQL 16 with a database "qaswarm"
export AQS_DATABASE_URL=postgresql+psycopg://qaswarm:qaswarm-dev-only@localhost:5432/qaswarm
export AQS_DEV_AUTH=true AQS_EXEC_TOKEN=change-me-to-a-long-random-string
export AQS_DEV_FIXTURE_REPOS=true AQS_EMBEDDED_SCHEDULER=true AQS_EMBEDDED_EXEC_WORKER=true
make migrate && make seed
make dev-api                     # python -m qaswarm.api.serve --port 8000  (terminal 1)
make dev-web                     # vite dev server on :5173, proxies /api to :8000 (terminal 2)
```

Separate roles instead of the embedded ones (closer to the production shape):

```bash
make dev-scheduler               # python -m qaswarm.workflow.scheduler
AQS_EXEC_TOKEN=... AQS_EXEC_FIXTURES_DIR=../exec/fixtures make dev-exec
```

### Windows PowerShell (verified on Windows 11 without Docker)

```powershell
Copy-Item .env.example .env
Set-Location backend
python -m uv sync --all-groups
$env:AQS_DATABASE_URL = "postgresql+psycopg://qaswarm:qaswarm-dev-only@127.0.0.1:5432/qaswarm"
$env:AQS_DEV_AUTH = "true"; $env:AQS_EXEC_TOKEN = "change-me-to-a-long-random-string"
$env:AQS_DEV_FIXTURE_REPOS = "true"; $env:AQS_EMBEDDED_SCHEDULER = "true"; $env:AQS_EMBEDDED_EXEC_WORKER = "true"
python -m uv run alembic upgrade head
python -m uv run python -m qaswarm.db.seed
python -m uv run python -m qaswarm.api.serve --port 8000          # terminal 1
Set-Location ..\web; npm ci; npm run dev                             # terminal 2
```

Without Docker you need a PostgreSQL 16 server. Any install works; an embedded server such as
`pgserver` (pip) is enough for development: point `AQS_DATABASE_URL` at it and create the
`qaswarm` database (and a separate `qaswarm_test` for the integration tests).

## Configuration

All settings are `AQS_*` environment variables (or `.env`, see `.env.example`). Secrets have no
defaults. The API logs a `configuration:` warning at startup for every unsafe or incomplete
setting and returns the same list in `GET /api/v1/system/capabilities` (`warnings`), together
with the endpoints that are still `501` (`not_implemented`).

| Variable | Default | Meaning |
|---|---|---|
| `AQS_DATABASE_URL` | local dev URL with the sample password | SQLAlchemy URL. A warning is logged while it contains `qaswarm-dev-only`. |
| `AQS_ENVIRONMENT` | `dev` | Deployment label. Outside `dev`/`test`, enabled dev flags produce a loud warning. |
| `AQS_DEV_AUTH` | `false` | `true`: header auth `X-Dev-User` / `X-Dev-Role` (any caller picks any role; local only). `false`: every `/api/v1` call is `401` because OIDC is not built yet (slice 3e). |
| `AQS_EXEC_TOKEN` | unset | Shared secret for `/internal/v1/exec/*`. Unset → that surface answers `503` and no task ever runs. Use ≥ 16 random characters. |
| `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION` | `false` | Lets the `pytest` engine run repository code in the process runtime. **Not a sandbox.** |
| `AQS_EMBEDDED_SCHEDULER` / `AQS_EMBEDDED_EXEC_WORKER` | `false` | Run the scheduler / one worker inside the API process (development). |
| `AQS_EXEC_CONTROL_PLANE_URL` | `http://127.0.0.1:8000` | Where the embedded worker calls back. |
| `AQS_DEV_FIXTURE_REPOS` / `AQS_FIXTURES_DIR` | `false` / `../exec/fixtures` | Serve `https://fixtures.local/<owner>/<name>` from a directory (deterministic offline demo). |
| `AQS_GIT_HOST_ALLOWLIST` | `["github.com","gitlab.com"]` | Hosts accepted at repository registration. |
| `AQS_INTAKE_DNS_CHECK` | `true` | Resolve the host and reject private, loopback, link-local, CGNAT and reserved addresses before `git ls-remote`. |
| `AQS_EVIDENCE_DIR` | `./data/evidence` | Evidence object store root (persistent volume in production). |
| `AQS_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed browser origins. |
| `AQS_RUNNER_ENABLED` / `AQS_RUNNER_POLL_SECONDS` | `true` / `1.0` | Agent runner inside the API process (phase 3); or run `python -m qaswarm.workflow.runner`. |
| `AQS_API_ALLOWED_HOSTS` | `["localhost","127.0.0.1"]` | Hosts the API Testing agent may call with GET/HEAD/OPTIONS; everything else is recorded `blocked`. |
| `AQS_LLM_PROVIDER` (`none` \| `ollama`), `AQS_LLM_BASE_URL`, `AQS_LLM_MODEL`, `AQS_LLM_TIMEOUT_SECONDS`, `AQS_LLM_RATE_LIMIT_PER_MINUTE` | `none` | Optional local model for AG-02 proposals. With `none` every agent output is labelled `deterministic`; hosted providers are not supported. |
| Job/task limits | LLD defaults | `AQS_JOB_WALL_CLOCK_SECONDS` 4 h, `AQS_TASK_WALL_CLOCK_SECONDS` 30 min, `AQS_LEASE_TTL_SECONDS` 90, `AQS_HEARTBEAT_SECONDS` 30, `AQS_TASK_MAX_RETRIES` 2, `AQS_BACKOFF_SECONDS` `[30,120]` ± 20 %. |

Execution Service process (`python -m qaswarm_exec`): `AQS_EXEC_TOKEN`, `AQS_EXEC_CONTROL_PLANE_URL`,
`AQS_EXEC_FIXTURES_DIR`, `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION`, `AQS_EXEC_WORKER_ID`,
`AQS_EXEC_WORKSPACE_ROOT`, `AQS_EXEC_HEARTBEAT_SECONDS`.

## Using the API

Dev auth: send `X-Dev-User: <name>` and `X-Dev-Role: <one of the seven roles>` (e.g. `QA Lead`,
`QA Engineer`, `Viewer`). Query parameters `dev_user`/`dev_role` are accepted **only** on the SSE
endpoint, because `EventSource` cannot send headers.

```bash
H='-H "X-Dev-User: me" -H "X-Dev-Role: QA Lead" -H "Content-Type: application/json"'
curl -s $H -X POST localhost:8000/api/v1/projects -d '{"name":"Demo"}'
curl -s $H -X POST localhost:8000/api/v1/repositories -d '{"project_id":"prj_…","provider":"other","url":"https://fixtures.local/local/sample-python-app"}'
curl -s $H -H "Idempotency-Key: $(uuidgen)" -X POST localhost:8000/api/v1/jobs -d '{"repository_id":"rep_…","ref":"main","profiles":{"functional":"standard","security":"quick","performance":"none"}}'
curl -s $H localhost:8000/api/v1/jobs/job_…                      # state, stages, task/check/test summaries
curl -s $H localhost:8000/api/v1/jobs/job_…/checks               # per-engine outcomes
curl -s $H "localhost:8000/api/v1/jobs/job_…/report?format=html" # self-contained HTML
curl -s $H "localhost:8000/api/v1/jobs/job_…/compare?with=job_…"
curl -s $H -X POST localhost:8000/api/v1/jobs/job_…/cancel -d '{"reason":"stop"}'
# phase 3/5: agent inputs, plan, findings, gates
curl -s $H -H "Idempotency-Key: $(uuidgen)" -X POST localhost:8000/api/v1/jobs -d '{"repository_id":"rep_…","ref":"main","inputs":{"requirements":["Health endpoint must respond"],"api_checks":[{"method":"GET","url":"http://localhost:8000/healthz","expected_status":200,"priority":"P0"}]}}'
curl -s $H localhost:8000/api/v1/jobs/job_…/plan                 # persisted DAG (checks + agents)
curl -s $H localhost:8000/api/v1/jobs/job_…/findings             # defect records, sorted by risk priority
curl -s $H localhost:8000/api/v1/jobs/job_…/quality-gates        # QG-01…QG-08 and verdict
curl -s $H -X POST localhost:8000/api/v1/findings/fnd_…/triage -d '{"action":"mark_false_positive","reason":"fixture route"}'
```

A job **with** `inputs` whose ref cannot be pinned still runs its agent tasks (recorded as
unpinned with a warning); a job with neither inputs nor a pinnable ref fails at intake. Without
`AQS_EXEC_TOKEN` repository checks are not planned and only the agent tasks run.

Outcomes: a check ends `passed | failed | skipped | error` (`error` = tool or infrastructure
failure, never the code under test); tests use the six design statuses; a job ends
`completed`, `completed_with_warnings`, `failed`, `cancelled`, `timed_out` or `blocked`.

## Checks and tests

```bash
make check            # lint + typecheck + unit/integration tests + web build (what CI runs)
make test-unit        # pytest tests/unit — no database needed
make test             # pytest (unit + integration) and vitest
make migrate-roundtrip# alembic upgrade head → downgrade base → upgrade head
make audit            # pip-audit (backend) and npm audit (web)
```

Integration tests need PostgreSQL. Set `AQS_TEST_DATABASE_URL` to a **separate** database (the
tests drop and recreate every table); unset, they are skipped with a visible reason. Never point
two test runs at the same database at once.

```powershell
$env:AQS_TEST_DATABASE_URL = "postgresql+psycopg://qaswarm:qaswarm-dev-only@127.0.0.1:5432/qaswarm_test"
Set-Location backend; python -m uv run python -m pytest tests -q
python -m uv run ruff check src tests ..\exec\src; python -m uv run python -m mypy src ..\exec\src
Set-Location ..\web; npm run typecheck; npm run lint; npx vitest run; npm run build
```

## Troubleshooting

| Symptom | Cause / fix |
|---|---|
| `An Application Control policy has blocked this file` when running `uv run mypy`, `uv run uvicorn`, `uv run pytest` | Windows App Control blocks the `.exe` launchers in `.venv\Scripts`. Use `uv run python -m mypy`, `python -m qaswarm.api.serve`, `uv run python -m pytest`. |
| `ImportError: DLL load failed while importing _multiprocessing` on `python -m uvicorn` | Same policy blocks the extension for uv-managed Pythons. `python -m qaswarm.api.serve` detects this and runs a single uvicorn process without reload/workers. |
| `503 dependency_unavailable` from `/internal/v1/exec/*`; jobs sit in `running` with tasks `pending` | `AQS_EXEC_TOKEN` is unset or no worker is running. Set the token on both sides and start a worker (`make dev-exec`) or `AQS_EMBEDDED_EXEC_WORKER=true`. |
| Jobs stay `validating` with reason "waiting for the scheduler" | No scheduler: `make dev-scheduler` or `AQS_EMBEDDED_SCHEDULER=true`. |
| `pytest` check is `skipped` with "refused" | Expected: code execution needs `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true` on the worker, and that is only acceptable on a disposable host. |
| `503 No organization exists yet` | Run `make seed`. |
| `422 repository_url_rejected` | Only `https://`, allow-listed hosts (`AQS_GIT_HOST_ALLOWLIST`), `owner/repo` paths, no credentials, no IP literals, no ports. `fixtures.local` needs `AQS_DEV_FIXTURE_REPOS=true`. |
| `409 job_duplicate_active` | An equivalent job (repository + ref + profiles) is still active. Use it, or a QA Lead sends `force_new: true`. |
| A job stays `cancelling` | The scheduler confirms once every worker run is destroyed; a crashed worker is presumed dead after one lease TTL (default 90 s) and the job then ends `cancelled`. |
| Transient 404/409 during tests | Another process is using the same test database. Each test run (and each developer) needs its own `AQS_TEST_DATABASE_URL`. |
| `vite preview` unreachable at `127.0.0.1` | It binds `localhost` (IPv6 `::1` on some hosts); use `http://localhost:<port>`. |

Logs are JSON lines with `correlation_id`, `job_id`, `task_id`; every `problem+json` error
carries the same id as `trace_id`. Secrets (tokens, passwords, keys, JWTs, URL credentials,
private-key blocks) are redacted in logs and in evidence before storage.

## Phase 4: advanced testing capabilities

Four target-facing check engines run **only** against an explicitly configured, authorised target
(branch `phase4-advanced-testing`, details in `docs/build/phase-4-report.md`):

| Engine | What it does | Planned when |
|---|---|---|
| `api_tests` | Declarative HTTP suites (`.qaswarm/tests/*.yaml`, explicit paths or inline): method, headers, body, status / header / JSON-path / body / response-time assertions, captures, response-time recording | `testing.api` on the job |
| `browser_tests` | Playwright + Chromium steps (`goto`, `click`, `fill`, `press`, `expect`, `screenshot`); screenshots and the console log become evidence; ends `skipped` with the reason when Playwright/Chromium is missing | `testing.browser` on the job |
| `security_checks` | Read-only hygiene checks: security headers, cookie flags, redirect sanity, verbose error bodies, version disclosure. **Informational, not a security assessment or certification.** | `profiles.security` = `quick` / `standard` **and** a target |
| `performance_probe` | Bounded closed-loop GET probe (`smoke` ≤ 50 requests / 2 workers / 10 s, `baseline` ≤ 200 / 5 / 30 s, clamped by worker caps); p50/p95/p99, throughput, error rate | `profiles.performance` = `smoke` / `baseline` **and** a target |

Targets: `POST /api/v1/targets` (Org Admin) registers a non-production base URL;
`POST /api/v1/targets/{id}/authorizations` (Org Admin or Security Reviewer) records the HA-01
attestation (activities + time window). A job naming `target_id` without a valid attestation ends
`blocked` with zero worker runs. For local development set `"testing": {"target": "local_fixture"}`
and the worker starts `exec/fixtures/sample-target-app` on an ephemeral loopback port.
`POST /api/v1/jobs/{id}/rerun` `{"engines": [...]}` reruns selected checks of a finished job as a
new job and links to `GET /jobs/{old}/compare?with={new}`. Plans without this configuration are
unchanged.

Egress guardrails (worker): hosts resolving to loopback, RFC1918, link-local (incl.
`169.254.169.254`), CGNAT or other non-public ranges are refused at connect time, redirects are
re-checked hop by hop and must stay on the authorised host, browser traffic goes through a
worker-local policy proxy, and `Authorization`, cookies and tokens are redacted from all evidence.
`AQS_EXEC_ALLOW_LOCAL_TARGETS=true` (worker) plus `AQS_ALLOW_LOCAL_TARGETS=true` (control plane)
enable controlled local testing of registered loopback/private targets. Performance caps:
`AQS_EXEC_PERF_MAX_REQUESTS` (500), `AQS_EXEC_PERF_MAX_CONCURRENCY` (10),
`AQS_EXEC_PERF_MAX_DURATION_SECONDS` (60). Browser engine install:
`uv sync --all-groups` (pulls `qaswarm-exec[browser]`) then `python -m playwright install chromium`.

## Known limitations

- **No sandbox.** Checks run in a subprocess with a scrubbed environment, a wall clock, an output
  cap and process-tree kill, but no network, file-system, CPU or memory isolation
  (SEC-003/SEC-004 not met). `pytest` is therefore refused by default. gVisor/Docker workers are
  slice 1c.
- **No real authentication.** Dev header auth or nothing; OIDC and RBAC are slice 3e. Do not expose
  the API beyond a trusted network.
- **Single organization.** The principal is bound to the first organization in the database.
- **Deterministic adapters only.** Agents AG-02/03/04/08/11 run deterministic logic (optional
  local Ollama for AG-02 proposals); no hosted Model Gateway. Findings are single-run (DCS 63,
  Probable at most): no reproduction runs, no flaky register, no patch proposals or independent
  verification, no mutation testing. Functional scenarios derived from supplied requirements are
  recorded `skipped`; only the repository's own pytest suite executes (when allowed). Unbuilt
  contract endpoints answer `501 not_implemented` with their `planned_slice`.
- **Repository dependencies are not installed** before `pytest`; suites that need them end
  `error` with the log attached, never `passed`.
- **Intake residual risk.** DNS is checked before `git ls-remote`, redirects are disabled, but a
  DNS answer can still change between the check and the connection (rebinding).
- **Compose path and Kubernetes are unverified** on the Phase 6 machine (no Docker).
- Rate limiting, OpenTelemetry export and the DB-level revoke of `UPDATE`/`DELETE` on audit tables
  are not implemented.

## Non-negotiable rules (from `CLAUDE.md`)

- The control plane never executes repository code (SEC-001).
- No secrets in code, logs, prompts, fixtures or the database; logs pass through redaction.
- No automatic commit, push or merge of user repositories; patches are proposals only.
- Stubs are honest: `501 Not Implemented` or "Not implemented in this phase" in the UI. Never
  fabricated results.

Proposed licence: Apache-2.0 (open decision DEC-01).
