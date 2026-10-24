# Autonomous QA Swarm

An open-source, self-hostable QA platform in which specialized AI agents, coordinated by a
deterministic workflow engine, plan and run tests against a **pinned commit** inside **disposable
sandboxes**, correlate evidence, propose fixes for human review and independently verify them.

Two principles override everything else:

1. **Agents propose, deterministic services dispose, humans approve.** Agents never execute code,
   never hold credentials and never change a repository.
2. **No evidence, no defect.** Nothing is reported as a confirmed defect without reproducible evidence.

> **Status: Phase 2 — real QA execution engine (slices 1b/1c-process/1d core).** Jobs are pinned
> (`git ls-remote`, SSRF-safe), planned into a task DAG, leased by the **Execution Service**
> (`exec/`, a separate process with no database access) and run as real deterministic checks:
> snapshot integrity, Python syntax, secret scan and — only when the host explicitly allows
> unsandboxed code execution — the repository's own pytest suite. Every run, check, test, log and
> evidence item is persisted; the UI shows live progress, results, previous runs and a comparison.
> The control plane still never executes repository code (SEC-001). **`SubprocessRuntime` is not a
> sandbox**; gVisor/Docker isolation is still planned (slice 1c). `GET /api/v1/system/capabilities`
> reports exactly what the running instance can do.

The design is the source of truth: [`docs/design/`](docs/design/README.md). Build plan and phase
prompts: [`docs/build/`](docs/build/BUILD_PLAN.md). Phase reports: `docs/build/phase-<id>-report.md`.

## Architecture summary

| Layer | Implementation (phase 2) |
|---|---|
| Web UI (`web/`) | React 18 + TypeScript + Vite, Tailwind, React Router, TanStack Query. App shell with the 15 screens; Dashboard, Repositories, New QA Job, Live Job Execution (13-stage timeline, tasks, checks, evidence drawer, report), Functional Test Results and run comparison are wired to the API. The mode pill is driven by `/system/capabilities`. |
| API Gateway (`backend/src/qaswarm/api`) | FastAPI under `/api/v1`: RFC 9457 `problem+json` errors with `error_code`, correlation IDs, dev-only header auth, `Idempotency-Key`, cursor pagination, ETags, SSE. Every contract endpoint not built yet returns `501` with its planned slice. |
| Domain (`qaswarm.domain`) | Enums exactly as the LLD/data model define them; `JobStateMachine` and `TaskStateMachine` built from the LLD transition tables. |
| Workflow (`qaswarm.workflow`) | PostgreSQL task queue (`FOR UPDATE SKIP LOCKED`, 90 s lease, heartbeat, 2 retries, backoff 30/120 s ± 20 %, reaping, expiry, dependent skipping) and the **scheduler** (`python -m qaswarm.workflow.scheduler`): admit → intake/pin → plan → reap → expire → propagate → advance → deadlines → confirm cancellation. |
| Audit (`qaswarm.audit`) | Append-only, hash-chained audit events (`sha256(prev_hash + canonical JSON)`) with `verify_chain`. Every job and task state change writes one. |
| Intake (`qaswarm.intake`) | `git ls-remote --symref` ref → commit SHA with DNS checks that reject private/loopback/metadata addresses; dev-only fixture repositories (`https://fixtures.local/local/<name>`). |
| Evidence (`qaswarm.evidence`) | Content-addressed store `evidence/{org}/{sha[:2]}/{sha}`; text is redacted **before** hashing; 50 MiB cap with truncation flag. |
| Data (`qaswarm.db`) | SQLAlchemy 2 + Alembic on PostgreSQL 16: Organization, Project, Repository, Job, Task, TaskAttempt, WorkerRun, CheckRun, TestExecution, EvidenceItem, Report, AuditEvent, OutboxEvent, IdempotencyRecord. |
| Execution plane (`exec/`) | `qaswarm_exec`: leases tasks over `/internal/v1/exec/*` (`X-Exec-Token`), fetches the pinned commit, runs check engines in a `SubprocessRuntime` (**not a sandbox**), uploads evidence, submits `worker_result/1` JSON (schema-validated server-side). `DockerRuntime` is declared but unavailable. See [`exec/README.md`](exec/README.md). |

## Quick start (Docker Compose)

Prerequisites: Docker Desktop (or Docker Engine + Compose v2).

```bash
cp .env.example .env            # safe local defaults, no secrets
# add AQS_EXEC_TOKEN=<random> to .env (python -c "import secrets; print(secrets.token_urlsafe(32))")
docker compose up -d --build    # postgres, api (migrates + seeds), scheduler, exec-host, web
```

- UI: <http://localhost:5173>
- API docs (OpenAPI): <http://localhost:8000/api/v1/docs>, document at `/api/v1/openapi.json`
- Health: <http://localhost:8000/healthz>, readiness: <http://localhost:8000/readyz>

The API container runs `alembic upgrade head` and the seed command on start. The seed creates one
organization "Northwind Fintech (sample org)" and one project "Payments Platform", both marked as
sample data.

## Local development (without the api/web containers)

Prerequisites: Python 3.12 via [`uv`](https://docs.astral.sh/uv/), Node 22+ with npm, Docker (for
Postgres), GNU make (optional; the commands are plain and listed below).

```bash
make setup          # uv sync --all-groups (backend) + npm ci (web)
make up             # or: docker compose up -d postgres
make migrate        # cd backend && uv run alembic upgrade head
make seed           # cd backend && uv run python -m qaswarm.db.seed
make dev-api        # cd backend && uv run uvicorn qaswarm.api.app:create_app --factory --reload --port 8000
make dev-web        # cd web && npm run dev      (proxies /api, /healthz, /readyz to :8000)
make dev-scheduler  # cd backend && uv run python -m qaswarm.workflow.scheduler
make dev-exec       # cd backend && uv run python -m qaswarm_exec   (needs AQS_EXEC_TOKEN)
```

Single-process alternative for a laptop: set `AQS_EMBEDDED_SCHEDULER=true` and
`AQS_EMBEDDED_EXEC_WORKER=true` (plus `AQS_EXEC_TOKEN`) and `make dev-api` runs all three roles
in one process. `AQS_DEV_FIXTURE_REPOS=true` makes `https://fixtures.local/local/sample-python-app`
(refs `main`, `fix-rounding`) available without network access.

Settings come from `AQS_*` environment variables (see `.env.example`). `AQS_DEV_AUTH=true` enables
dev-only header auth: send `X-Dev-User: <name>` and `X-Dev-Role: <one of the 7 roles>`. With
`AQS_DEV_AUTH=false` every `/api/v1` call returns `401` (OIDC arrives in slice 3e).

### PowerShell equivalents

```powershell
Copy-Item .env.example .env
docker compose up -d postgres
Set-Location backend; uv sync --all-groups; uv run alembic upgrade head; uv run python -m qaswarm.db.seed
uv run uvicorn qaswarm.api.app:create_app --factory --reload --port 8000     # terminal 1
Set-Location ..\web; npm ci; npm run dev                                       # terminal 2
```

Note for Windows: `uv run pytest` can be blocked by Windows App Control in some setups; the Makefile
and CI therefore invoke `uv run python -m pytest`, which always works.

## Checks and tests

```bash
make check          # lint + typecheck + test + web build (everything CI runs)
make lint           # ruff check + ruff format --check (backend); eslint + prettier (web)
make typecheck      # mypy (backend, strict for domain/workflow); tsc (web)
make test           # pytest (unit + integration) and vitest
make test-unit      # pytest tests/unit only (no database needed)
```

Integration tests need PostgreSQL. Set `AQS_TEST_DATABASE_URL` to a **separate** database (the
tests drop and recreate every table); with Compose:

```bash
docker exec autonomous-qa-swarm-postgres-1 psql -U qaswarm -d qaswarm -c "CREATE DATABASE qaswarm_test"
export AQS_TEST_DATABASE_URL=postgresql+psycopg://qaswarm:qaswarm-dev-only@localhost:5432/qaswarm_test
make test
```

When `AQS_TEST_DATABASE_URL` is unset, integration tests are skipped with a visible reason.
CI (`.github/workflows/ci.yml`) runs the backend job with a Postgres 16 service container and the
web job with `npm ci`, lint, format check, typecheck, tests and build.

## API in this slice

| Endpoint | Notes |
|---|---|
| `GET /healthz`, `GET /readyz` | Liveness; readiness checks the database. |
| `POST/GET /api/v1/projects`, `GET/PATCH/DELETE /api/v1/projects/{id}` | Edit/view/delete go beyond the contract table (Phase 1 brief); delete archives (`archived_at`). |
| `POST /api/v1/repositories`, `GET /api/v1/repositories[?project_id=]`, `GET /api/v1/repositories/{id}` | Syntactic validation on create (https, allow-listed host, `owner/repo`, no credentials); the first job pins it with `git ls-remote` after DNS/SSRF checks and sets `validation_status` to `valid` / `validation_failed`. |
| `POST /api/v1/jobs` | Requires `Idempotency-Key`. Same key + same body within 24 h replays the original response (`Idempotent-Replayed: true`); same key + different body → `422 idempotency_key_reused`; active job for the same repository + ref + profiles → `409 job_duplicate_active` with `existing_job` unless `force_new=true` by a QA Lead. Job is created `created` → `validating`, held until the scheduler pins it, then `queued` → `planning` → `running` → `reporting` → `completed` / `completed_with_warnings` / `failed`. |
| `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}` | Cursor pagination; filters `state` (comma-separated), `repository_id`, `project_id`; `ETag` on detail. |
| `POST /api/v1/jobs/{id}/cancel` | Through the state machine; `409 invalid_state_transition` on terminal jobs. |
| `GET /api/v1/jobs/{id}/events` | SSE with `id:` and `Last-Event-ID` resume; dev auth also accepted as `?dev_user=&dev_role=` because `EventSource` cannot send headers. |
| `GET /api/v1/jobs/{id}/tasks`, `/checks`, `/test-executions[?status=]`, `/evidence`, `/worker-runs` | Persisted execution data (test-executions also returns per-status counts in `X-Test-Counts`). |
| `GET /api/v1/jobs/{id}/report?format=json\|html` | Composed from stored checks/tests; `pdf`, `sarif`, `junit` → `501` (slice 2d). |
| `GET /api/v1/jobs/{id}/compare?with=<job_id>` | Check and test deltas (improved / regressed / unchanged / added / removed). |
| `GET /api/v1/evidence/{id}`, `/content`, `/download` | Redacted evidence; not for Viewer / CI roles. |
| `GET /api/v1/audit-events` | Hash-chained audit log (Org Admin, QA Lead, Security Reviewer). |
| `GET /api/v1/system/capabilities` | What this instance can do: execution on/off, sandbox name, whether repository code may run, engines. |
| `/internal/v1/exec/*` | Execution Service only; `X-Exec-Token` required (`503` when unset, `401` when wrong). |
| Everything else in the contract | `501 not_implemented` with `planned_slice`. |

Errors are `application/problem+json` with `type`, `title`, `status`, `detail`, `instance`,
`error_code`, `trace_id` and, for validation, `errors[]` with JSON pointers.

## Phase status

| Slice | Goal | Status |
|---|---|---|
| 1a Boilerplate | Monorepo, Compose, FastAPI skeleton, DB + migrations, state machines, task queue core, audit chain, API stubs, React shell, CI | **Built** — see `docs/build/phase-1a-report.md` |
| 1b Source intake | SSRF-safe validation, DNS pinning, ref → SHA, snapshot + evidence store | **Built** (phase 2) |
| 1c Sandbox execution | Execution Service, leases, limits, cleanup | **Partly built** (phase 2): process runtime, no gVisor/Docker isolation yet |
| 1d Results and live job | pytest end-to-end, six statuses, reports, results UI, compare | **Built** (phase 2) except flaky reruns; see `docs/build/phase-2-report.md` |
| 2a–2d, 3a–3e | See `docs/build/BUILD_PLAN.md` | Not started |

## Known limitations (phase 2)

- `SubprocessRuntime` isolates by process only. Repository code (pytest) runs **only** when the exec
  host sets `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true`; otherwise the pytest check is reported
  as `skipped` with the reason, never silently.
- Check engines: `snapshot_integrity`, `python_syntax`, `secret_scan`, `pytest`. Security /
  performance / mutation profiles produce a warning and no tasks.
- Report formats `pdf`, `sarif`, `junit`, flaky reruns, agents, patch proposals, OIDC: not
  implemented (`501` / "planned slice").
- Private-network targets are rejected at intake; there is no allow-list for internal git hosts yet.

## Non-negotiable rules (from `CLAUDE.md`)

- The control plane never executes repository code.
- No secrets in code, logs, prompts, fixtures or the database; logs pass through redaction.
- No automatic commit, push or merge of user repositories; patches are proposals only.
- Stubs are honest: `501 Not Implemented` or "Not implemented in this phase" in the UI. Never fabricated results.

Proposed licence: Apache-2.0 (open decision DEC-01).
