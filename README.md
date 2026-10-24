# Autonomous QA Swarm

An open-source, self-hostable QA platform in which specialized AI agents, coordinated by a
deterministic workflow engine, plan and run tests against a **pinned commit** inside **disposable
sandboxes**, correlate evidence, propose fixes for human review and independently verify them.

Two principles override everything else:

1. **Agents propose, deterministic services dispose, humans approve.** Agents never execute code,
   never hold credentials and never change a repository.
2. **No evidence, no defect.** Nothing is reported as a confirmed defect without reproducible evidence.

> **Status: concept build, slice 1a.** This repository contains the boilerplate and foundations only.
> The control plane never executes repository code (SEC-001). Nothing in this build fetches, builds
> or runs a repository; jobs are created and held at *Intake & Pinning* with the reason
> "intake arrives in slice 1b". All UI data comes from the API; the seeded organization is labelled
> "Sample data — no repository code executed".

The design is the source of truth: [`docs/design/`](docs/design/README.md). Build plan and phase
prompts: [`docs/build/`](docs/build/BUILD_PLAN.md). Phase reports: `docs/build/phase-<id>-report.md`.

## Architecture summary

| Layer | Implementation (slice 1a) |
|---|---|
| Web UI (`web/`) | React 18 + TypeScript + Vite, Tailwind, React Router, TanStack Query. App shell with the 15 screens SCR-01…SCR-15; Dashboard, Repositories & Projects, New QA Job and Live Job Execution are wired to the API. |
| API Gateway (`backend/src/qaswarm/api`) | FastAPI under `/api/v1`: RFC 9457 `problem+json` errors with `error_code`, correlation IDs, dev-only header auth, `Idempotency-Key`, cursor pagination, ETags, SSE. Every contract endpoint not built yet returns `501` with its planned slice. |
| Domain (`qaswarm.domain`) | Enums exactly as the LLD/data model define them; `JobStateMachine` and `TaskStateMachine` built from the LLD transition tables. |
| Workflow (`qaswarm.workflow`) | PostgreSQL task queue: `enqueue` (unique idempotency key), `lease` (`FOR UPDATE SKIP LOCKED`, 90 s lease), `heartbeat`, `complete`, `fail`, backoff 30 s / 120 s ± 20 %, `reap_expired_leases`. |
| Audit (`qaswarm.audit`) | Append-only, hash-chained audit events (`sha256(prev_hash + canonical JSON)`) with `verify_chain`. Every job and task state change writes one. |
| Data (`qaswarm.db`) | SQLAlchemy 2 + Alembic on PostgreSQL 16: Organization, Project, Repository, Job, Task, TaskAttempt, AuditEvent, OutboxEvent, IdempotencyRecord. |
| Execution plane (`exec/`) | Package skeleton only (`qaswarm_exec`); arrives in slice 1c. |

## Quick start (Docker Compose)

Prerequisites: Docker Desktop (or Docker Engine + Compose v2).

```bash
cp .env.example .env            # safe local defaults, no secrets
docker compose up -d --build    # postgres:16, api (migrates + seeds on start), web
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
```

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
| `POST /api/v1/repositories`, `GET /api/v1/repositories[?project_id=]`, `GET /api/v1/repositories/{id}` | **Syntactic** URL validation only: https, allow-listed host, `owner/repo` path, no credentials. Stored as `pending_validation`; full SSRF checks are slice 1b (stated in `validation_note`). |
| `POST /api/v1/jobs` | Requires `Idempotency-Key`. Same key + same body within 24 h replays the original response (`Idempotent-Replayed: true`); same key + different body → `422 idempotency_key_reused`; active job for the same repository + ref + profiles → `409 job_duplicate_active` with `existing_job` unless `force_new=true` by a QA Lead. Job is created `created` → `validating` and held. |
| `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}` | Cursor pagination; filters `state` (comma-separated), `repository_id`, `project_id`; `ETag` on detail. |
| `POST /api/v1/jobs/{id}/cancel` | Through the state machine; `409 invalid_state_transition` on terminal jobs. |
| `GET /api/v1/jobs/{id}/events` | SSE with `id:` and `Last-Event-ID` resume; dev auth also accepted as `?dev_user=&dev_role=` because `EventSource` cannot send headers. |
| Everything else in the contract | `501 not_implemented` with `planned_slice`. |

Errors are `application/problem+json` with `type`, `title`, `status`, `detail`, `instance`,
`error_code`, `trace_id` and, for validation, `errors[]` with JSON pointers.

## Phase status

| Slice | Goal | Status |
|---|---|---|
| 1a Boilerplate | Monorepo, Compose, FastAPI skeleton, DB + migrations, state machines, task queue core, audit chain, API stubs, React shell, CI | **Built** — see `docs/build/phase-1a-report.md` |
| 1b Source intake | SSRF-safe validation, DNS pinning, ref → SHA, snapshot + evidence store | Not started |
| 1c Sandbox execution | Execution Service, disposable gVisor workers, limits, cleanup | Not started |
| 1d Results and live job | pytest end-to-end, six statuses, flaky reruns, reports, results UI | Not started |
| 2a–2d, 3a–3e | See `docs/build/BUILD_PLAN.md` | Not started |

## Non-negotiable rules (from `CLAUDE.md`)

- The control plane never executes repository code.
- No secrets in code, logs, prompts, fixtures or the database; logs pass through redaction.
- No automatic commit, push or merge of user repositories; patches are proposals only.
- Stubs are honest: `501 Not Implemented` or "Not implemented in this phase" in the UI. Never fabricated results.

Proposed licence: Apache-2.0 (open decision DEC-01).
