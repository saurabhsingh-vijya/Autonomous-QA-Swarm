# Phase 1a — Boilerplate and foundations

You are the lead engineer building **Autonomous QA Swarm**. Follow `CLAUDE.md` in the repo root at all times. This session builds **slice 1a only**: the project skeleton and foundations that every later phase builds on. Do not build source intake, sandbox execution, scanners or LLM agents yet.

## 0. Read first (in this order, only these)

1. `CLAUDE.md`
2. `docs/build/BUILD_PLAN.md` (slice 1a row)
3. `docs/design/05-architecture/04-component-architecture.md` — module structure (`qaswarm.*`, `qaswarm_exec.*`)
4. `docs/design/05-architecture/03-low-level-design.md` — job and task state machines (transition tables), task queue (enqueue, lease with `SELECT … FOR UPDATE SKIP LOCKED`, heartbeat, reaper, backoff), error code catalogue
5. `docs/design/07-data-model/01-data-model-and-erd.md` — entities and integrity rules
6. `docs/design/08-api-specifications/01-api-contracts.md` — conventions, problem+json, Idempotency-Key, pagination, endpoint table
7. `docs/design/02-prd-frd/03-ui-screen-inventory.md` and the images in `docs/design/mockups/` — screen names and layout for the UI shell
8. `docs/design/05-architecture/05-technology-options.md` — only if you need to confirm a library choice

Then write your plan to `docs/build/phase-1a-plan.md` and continue.

## 1. Repository layout to create

```text
.
├── CLAUDE.md                      (exists)
├── README.md                      quick start, architecture summary, phase status table
├── Makefile                       setup, dev, up, down, migrate, lint, typecheck, test, check, fmt
├── .env.example                   every AQS_* setting with safe defaults, no secrets
├── .gitignore, .editorconfig, .pre-commit-config.yaml
├── docker-compose.yml             postgres:16, api, web (and a placeholder comment for exec-host)
├── .github/workflows/ci.yml       backend lint+types+tests (with Postgres service), web lint+test+build
├── backend/
│   ├── pyproject.toml             uv-managed; ruff, mypy, pytest config
│   ├── alembic.ini, migrations/
│   ├── src/qaswarm/
│   │   ├── api/                   app factory, routers (health, repositories, jobs), deps, errors, middleware
│   │   ├── domain/                enums, state machines, pydantic models (no I/O)
│   │   ├── contracts/             JSON Schemas: task contract v1, worker result v1 (from the LLD), schema registry
│   │   ├── workflow/              queue: enqueue, lease, heartbeat, complete/fail, reaper, backoff
│   │   ├── audit/                 hash-chained audit events + verify
│   │   ├── db/                    SQLAlchemy models, session, repositories (data access)
│   │   ├── telemetry/             JSON logging, correlation-ID middleware, redaction filter
│   │   └── config.py              pydantic-settings (AQS_ prefix)
│   └── tests/unit, tests/integration
├── exec/
│   └── src/qaswarm_exec/          package skeleton only (README stating it arrives in slice 1c)
└── web/                           Vite + React + TS + Tailwind + React Router + TanStack Query
```

Keep the other `qaswarm.*` modules from the component architecture as empty packages with a one-line module docstring saying which slice implements them. Do not add placeholder logic to them.

## 2. Backend — what to implement

**Configuration and app**
- `config.py` using pydantic-settings: database URL, CORS origins, log level, `AQS_DEV_AUTH` (default `false`), job defaults (wall clock 4 h, task 30 min, lease 90 s, heartbeat 30 s, retries 2, backoff 30 s / 120 s with ±20% jitter).
- App factory, `/healthz` (liveness) and `/readyz` (DB reachable).
- Error handling: every error returns RFC 9457 `application/problem+json` with `type`, `title`, `status`, `detail`, `instance`, `error_code`.
- Middleware: correlation ID (accept `X-Correlation-ID` or generate one; echo it back), structured JSON logs, a redaction filter for tokens, passwords and `Authorization` headers.
- Dev-only auth: if `AQS_DEV_AUTH=true`, read `X-Dev-User` and `X-Dev-Role` (one of the 7 roles in the design) and attach a principal. Otherwise every `/api/v1` call returns `401` with a problem body stating that OIDC arrives in slice 3e. Write a test for both modes.

**Domain and state machines (most important part of this slice)**
- Enums exactly as the LLD and data model define them: job states, task states, test execution statuses, finding statuses, patch statuses, gate result values, verdicts, roles, severities and confidence levels.
- `JobStateMachine` and `TaskStateMachine` built from the LLD transition tables. `transition(current, event)` returns the new state or raises `IllegalTransition`. Terminal states have no outgoing transitions.
- Table-driven unit tests covering every allowed transition, plus a Hypothesis property test that random event sequences never reach a state outside the defined set and never leave a terminal state.

**Database**
- SQLAlchemy 2 models and the first Alembic migration for: Organization, Project, Repository, Job, Task, TaskAttempt, AuditEvent, IdempotencyRecord. Include `org_id` on tenant tables (row-level security comes later), ULID prefixed IDs, UTC timestamps, the indexes and unique constraints the data model specifies (for example a unique task idempotency key).
- Seed command (`make seed`) that creates one org and project named "Northwind Fintech (sample org)" / "Payments Platform", clearly marked as sample data.

**Workflow queue core**
- `enqueue(task)` honouring the unique idempotency key (no duplicate tasks).
- `lease(worker_id, task_types)` using `SELECT … FOR UPDATE SKIP LOCKED`, creating a TaskAttempt with a 90 s lease.
- `heartbeat`, `complete`, `fail(retryable=…)` with retry budget and backoff, `reap_expired_leases()`.
- Integration tests against real PostgreSQL (the Compose service locally, the service container in CI): two concurrent leasers never get the same task; an expired lease becomes `failed_retryable` then `retry_scheduled`; a third transient failure ends `failed`.

**Audit log**
- `append_event(...)` computes `hash = SHA-256(prev_hash + canonical JSON of event)`; `verify_chain(range)` detects tampering. Test that editing one stored row is detected.
- Every job and task state change writes an audit event.

**API endpoints in this slice** (paths and shapes from the API contracts doc)
- `POST /api/v1/projects`, `GET /api/v1/projects`
- `POST /api/v1/repositories`: **syntactic validation only** (https scheme, allow-listed host, `owner/repo` path shape, no credentials in the URL). Store with status `pending_validation`. Full SSRF/DNS checks are slice 1b; state this in the response's `validation_note`.
- `GET /api/v1/repositories/{repository_id}`
- `POST /api/v1/jobs`: requires the `Idempotency-Key` header. Same key within 24 h returns the stored original response. An active job with the same repository + ref + profile hash returns `409` with `existing_job`, unless `force_new=true` and the role is QA Lead. The job is created in state `created`, moved to `validating`, then held there with reason "intake arrives in slice 1b" (no execution).
- `GET /api/v1/jobs` (cursor pagination, filters for state and repository), `GET /api/v1/jobs/{job_id}`
- `POST /api/v1/jobs/{job_id}/cancel`: valid only through the state machine; `409` on terminal jobs.
- `GET /api/v1/jobs/{job_id}/events`: Server-Sent Events stream of state changes from the audit/outbox table, with `id:` for resume.
- Every other endpoint in the API contract table: register the route and return `501` problem+json with `error_code: not_implemented` and the slice that will implement it. Generate the list from the contract table so nothing is missed.
- Make sure the OpenAPI document at `/api/v1/openapi.json` reflects all of the above.

## 3. Frontend — what to implement

- App shell matching the mockups: left sidebar with the 15 screens (SCR-01…SCR-15) grouped as in the mockups, a top bar with an org/project switcher, and a visible amber pill "Concept build — no repository code executed".
- One route per screen using the exact screen names from the UI inventory. Each page shows its title, a one-line purpose and a "Planned in slice X" empty state, except:
  - **Dashboard (SCR-01)**: recent jobs from `GET /api/v1/jobs`, with loading, empty and error states.
  - **Repositories & Projects (SCR-02)**: list repositories plus an "Add repository" dialog that calls the API and shows validation errors from problem+json.
  - **New QA Job (SCR-03)**: minimal form (repository, ref, profiles) that posts with a generated Idempotency-Key and navigates to the job page.
  - **Jobs / Live Job Execution (SCR-04)**: job detail with state badge and a live SSE event list.
- Shared components: StatusBadge (one colour per state, consistent with the mockups), SeverityChip, ProblemAlert, EmptyState, DataTable.
- API client typed from the backend OpenAPI document (`openapi-typescript`) or hand-written types kept in one file.
- Vitest + React Testing Library tests for StatusBadge mapping, the Add-repository form error display and the routing of all 15 screens.

## 4. Tooling and CI

- `make setup`, `make up` (Compose), `make migrate`, `make seed`, `make dev`, `make lint`, `make typecheck`, `make test`, `make check` (everything CI runs). Use plain commands so they also work from Git Bash or WSL on Windows; document the PowerShell equivalents in the README.
- Pre-commit: ruff, ruff-format, end-of-file fixer, trailing whitespace, prettier for web.
- GitHub Actions `ci.yml`: backend job (uv sync, ruff, mypy, pytest with a Postgres 16 service), web job (npm ci, lint, test, build). Pin action versions.
- Pin dependency versions in lockfiles (`uv.lock`, `package-lock.json`).

## 5. Out of scope for 1a (do not build; list under "Deferred" in the report)

Git network access, cloning or ref resolution · Docker worker execution · any running of repository code · scanners · LLM or Model Gateway calls · OIDC login · evidence store · reports · quality gates · performance, mutation and patch features.

## 6. Definition of done

- [ ] `docker compose up` brings up postgres, api and web; `make migrate && make seed` succeeds; the UI loads at http://localhost:5173 and shows the seeded project.
- [ ] `make check` passes locally with the actual output pasted into the report.
- [ ] State machine tests cover every transition in the LLD tables; illegal transitions are rejected.
- [ ] Concurrency test proves no double leasing; retry and backoff behaviour tested.
- [ ] Idempotency tests: same key returns the original response; duplicate active job returns `409`.
- [ ] Audit chain tamper test passes.
- [ ] All unimplemented endpoints return `501` with the planned slice; none return fake data.
- [ ] CI workflow file present and valid (run `act` or explain that it could not be run locally).
- [ ] `docs/build/phase-1a-report.md` written: built items, requirement IDs covered (full/partial), commands, real check results, known gaps, deferred list, suggested slice 1b adjustments.

Work on branch `phase-1a-boilerplate` with small commits. Do not push. When done, stop and give me a short summary plus the path to the report.
