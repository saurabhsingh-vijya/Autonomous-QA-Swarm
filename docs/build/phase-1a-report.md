# Phase 1a report — Boilerplate and foundations (Phase 1 "Core Foundation")

Branch `phase-1a-boilerplate` (4 commits on top of `main`, not pushed). Date: 24 October 2026.
Plan: `docs/build/phase-1a-plan.md`.

## Stack

Python 3.12 · FastAPI 0.115 · Pydantic v2 · SQLAlchemy 2.0 · Alembic · psycopg 3 · PostgreSQL 16 ·
`uv` · pytest + Hypothesis · ruff · mypy (strict) — React 18 · TypeScript 5.6 · Vite 5 · Tailwind 3 ·
React Router 6 · TanStack Query 5 · Lucide · Vitest + Testing Library · ESLint 9 · Prettier —
Docker Compose · GitHub Actions.

## What was built

| Area | Delivered |
|---|---|
| Repo layout | `backend/`, `exec/` (skeleton), `web/`, `docs/`, `Makefile`, `docker-compose.yml`, `.env.example`, `.gitignore`, `.editorconfig`, `.gitattributes`, `.pre-commit-config.yaml`, `.github/workflows/ci.yml`, `README.md` |
| Configuration | `qaswarm/config.py` pydantic-settings, `AQS_` prefix; job/task defaults from the LLD (4 h / 30 min / 90 s / 30 s / 2 retries / 30 s, 120 s ± 20 %) |
| App | Factory `create_app`; `/healthz`, `/readyz` (DB reachable or 503 problem); CORS; OpenAPI at `/api/v1/openapi.json` |
| Errors | RFC 9457 `application/problem+json` with `type`, `title`, `status`, `detail`, `instance`, `error_code`, `trace_id`, `errors[]` (JSON pointers); 500 detail never echoes exception text |
| Middleware | Correlation ID (accepts `X-Correlation-ID`, else generates, always echoes); JSON request logs; redaction filter (Authorization, passwords, tokens, GitHub/GitLab/AWS keys, JWTs, URL userinfo) |
| Auth | Dev-only header auth (`X-Dev-User`, `X-Dev-Role` = one of the 7 roles; query params accepted for SSE). `AQS_DEV_AUTH=false` → every `/api/v1` call is 401 "OIDC arrives in slice 3e". Role checks: project/repository writes need Org Admin or QA Lead; job writes need a write role; `force_new` needs QA Lead |
| Domain | Enums exactly as the LLD/data model (job, task, test, finding, patch, gate, verdict, role, severity, confidence, source class, error class). `JobStateMachine` and `TaskStateMachine` built from the LLD transition tables; terminal states have no outgoing transitions; `IllegalTransition` |
| Database | SQLAlchemy models + first Alembic migration: Organization, Project, Repository, Job, Task, TaskAttempt, AuditEvent, OutboxEvent, IdempotencyRecord. `org_id` on every tenant table, prefixed ULIDs with CHECK constraints, UTC `timestamptz`, unique task idempotency key, partial unique index for active duplicate jobs, queue indexes |
| Seed | `python -m qaswarm.db.seed` (idempotent): "Northwind Fintech (sample org)" / "Payments Platform", `is_sample = true` |
| Workflow queue | `enqueue` (ON CONFLICT DO NOTHING on idempotency key), `lease` (`FOR UPDATE SKIP LOCKED`, dependency check, 90 s TaskAttempt lease), `heartbeat` (extends lease only for the owner; first heartbeat → `running`; `LeaseLost` otherwise), `complete`, `fail(retryable=…)` with retry budget and jittered backoff, `reap_expired_leases` (E-QUEUE-001), `cancel_job_tasks`. Every task state change goes through the state machine and writes outbox + audit rows in the same transaction |
| Audit | `append_event` computes `sha256(prev_hash + canonical JSON)` per organisation chain; `verify_chain(range)` reports the first broken link. Every job and task state change writes an event |
| API | `POST/GET /projects`, `GET/PATCH/DELETE /projects/{id}` (ETag / If-Match, 412 on mismatch, soft delete); `POST /repositories` (syntactic validation: https, allow-listed host, `owner/repo`, no credentials, stored `pending_validation` with `validation_note` naming slice 1b), `GET /repositories[?project_id=]`, `GET /repositories/{id}`; `POST /jobs` (Idempotency-Key required; replay with `Idempotent-Replayed: true`; `idempotency_key_reused` 422; `job_duplicate_active` 409 with `existing_job`; `force_new` QA Lead only; job `created` → `validating` and held with `held_reason`); `GET /jobs` (cursor pagination, filters state/repository/project), `GET /jobs/{id}` (13-stage progress, task summary, ETag); `POST /jobs/{id}/cancel` (state machine; 409 on terminal); `GET /jobs/{id}/events` SSE from the outbox with `id:` and `Last-Event-ID` resume, heartbeat, `stream.end`. All 18 other contract endpoints: 501 `not_implemented` + `planned_slice`, generated from `contract_table.py` |
| Contracts | JSON Schemas for task contract v1 and worker result v1 (LLD bounds) with a schema registry |
| Frontend | App shell (sidebar groups and 15 screens with exact inventory names, org/project switcher, amber "Concept build — no repository code executed" pill, dev user chip, SCR footer). SCR-01 recent jobs + real counts; SCR-02 project CRUD dialogs and Add-repository dialog with inline problem+json errors; SCR-03 minimal job form with generated Idempotency-Key and 409 link to the existing job; SCR-04 job list with state filters and job detail with held banner, cancel dialog, live SSE event list and 13-stage timeline; other 11 screens show purpose + "Planned in slice X". Shared StatusBadge, SeverityChip, ProblemAlert, EmptyState, DataTable, LoadingState, PageHeader, Dialog. Hand-written API types in one file |
| Tooling | Makefile targets (setup, up, down, migrate, migration, seed, dev-api, dev-web, lint, typecheck, test, test-unit, test-integration, build, check, fmt); pre-commit (ruff, ruff-format, EOF/whitespace, prettier); CI with Postgres 16 service, pinned action versions; lockfiles `uv.lock` and `package-lock.json` |

## Requirement coverage

| ID | Coverage |
|---|---|
| FR-005 Create QA job with profiles | Partial: creation, profiles enum validation (functional/security/performance), 202 + links. Approvals (HA-02/03/05) and policy evaluation not yet (2b/2c). AC-015 Viewer → 403 done |
| FR-006 Idempotent job creation and duplicate prevention | Full for this slice: AC-016 (400 without key), AC-017 (replay within 24 h, row count unchanged), AC-018 (409 with link; `force_new` QA Lead only, others 403). Duplicate key uses `ref` until commit SHA exists (1b) |
| FR-010 Real-time job progress via event stream | Partial: SSE with monotonic ids, replay with `Last-Event-ID`, no log tail (1d), delivery latency not measured |
| FR-011 Cancel job with guaranteed worker cleanup | Partial: cancel through state machine, 409 on terminal; worker destruction is 1c (there are no workers yet, so `cancelling` → `cancelled` is immediate and audited as `workers_destroyed: 0`) |
| FR-012 Job and task timeouts with bounded retries | Partial: lease expiry → `failed_retryable` → `retry_scheduled`, 2 retries, backoff 30/120 s ± 20 %, third transient failure → `failed` + `infrastructure_error` (all tested). Task wall-clock and job deadline enforcement loops are 1c/1d |
| FR-047 Job history with search and filters | Partial: list with state/repository/project filters and cursor pagination; verdict/initiator/date filters later |
| FR-054 Audit trail | Partial: hash-chained append-only events for every state change and every create/update/archive; tamper detection tested. `GET /audit-events` is 501 (1d); no DB-level revoke of UPDATE/DELETE grants yet |
| FR-001 Register repository | Partial (syntactic only, explicitly labelled): AC-001 non-https 422 done; AC-002 DNS/private-address checks are 1b; AC-003 201 with id and provider done, default branch not resolved |
| FR-041 No automatic commit/push/merge | Satisfied by construction: no code path touches a repository |
| FR-051 Settings | Not started (settings screen placeholder) |
| NFR-013 Portability | Partial: Docker Compose single host verified; Kubernetes not started |
| NFR-014 Observability | Partial: structured JSON logs with correlation id, job/task ids on audit rows; OpenTelemetry export not started |
| SEC-001, SEC-008 | Control plane executes nothing; redaction on logs. Prompt/evidence redaction later |

## Commands

```bash
cp .env.example .env
docker compose up -d --build            # postgres + api (migrate + seed) + web → http://localhost:5173
make setup && make up && make migrate && make seed && make dev-api   # local alternative (+ make dev-web)
make check                               # ruff, ruff format, eslint, prettier, mypy, tsc, pytest, vitest, vite build
```

Integration tests need `AQS_TEST_DATABASE_URL` pointing at a separate database (see README).

## Actual check results (local, Windows 11, Docker Desktop 29.7, uv 0.13.5, Node 24.18)

```
cd backend && uv run ruff check . && uv run ruff format --check .
All checks passed!
62 files already formatted
cd web && npm run lint && npm run format:check
✖ 4 problems (0 errors, 4 warnings)        # react-refresh/only-export-components, non-blocking
All matched files use Prettier code style!
cd backend && uv run mypy
Success: no issues found in 52 source files
cd web && npm run typecheck                 # clean
cd backend && uv run python -m pytest -q
128 passed, 1 warning in 28.14s             # 1 warning is a starlette TestClient deprecation
cd web && npm test -- --run
Test Files  3 passed (3) · Tests  21 passed (21)
cd web && npm run build
✓ built in 9.87s   (dist/assets/index-*.js 268.29 kB │ gzip: 82.38 kB)
MAKE EXIT: 0
```

Backend tests: 74 unit (state machines table-driven for every LLD row, Hypothesis property tests
that random event sequences never leave the defined set and never leave a terminal state, enums,
contract table, URL validation, redaction, backoff, auth modes, 501 stubs, OpenAPI) and 54
integration against PostgreSQL (project CRUD + persistence across a fresh app instance, validation
problem+json, repository registration/rejection, idempotent and duplicate-safe job creation, cancel
through the state machine, SSE replay/resume/end, every unimplemented contract endpoint returns 501,
queue: idempotent enqueue, 4 concurrent leasers × 20 tasks with no double lease, heartbeat and lost
lease, expired lease → retry_scheduled → third failure → failed, dependency gating and cancel, audit
chain tamper and deletion detection).

Docker Compose: `docker compose up -d --build` started postgres, api and web; `GET /readyz` returned
`database: reachable`, `GET /api/v1/projects` through both the API port and the Vite proxy returned
the seeded sample project; the api container log shows the migration and `seeded org=… project=…`.

Manual API smoke (curl against the local server): 401 without dev headers, 422
`repository_url_rejected` for `http://10.0.4.12/…`, 202 job creation held at `intake_and_pinning`,
replay with `idempotent-replayed: true`, 409 `job_duplicate_active`, 501 with `planned_slice: 2d`,
SSE frames `job.state_changed` and `job.held` with monotonic ids.

CI workflow: present and syntactically valid; **not executed locally** (`act` is not installed).
It mirrors `make check` plus `alembic upgrade head` and a downgrade/upgrade round-trip.

## Definition of done (from the Phase 1a prompt)

- [x] `docker compose up` brings up postgres, api and web; migrate + seed succeed; UI loads at :5173 with the seeded project.
- [x] `make check` passes locally (output above).
- [x] State machine tests cover every transition in the LLD tables; illegal transitions rejected; property tests.
- [x] Concurrency test proves no double leasing; retry and backoff tested.
- [x] Idempotency tests: same key returns the original response; duplicate active job returns 409.
- [x] Audit chain tamper test passes (edit and delete both detected).
- [x] All unimplemented endpoints return 501 with the planned slice; none return fake data.
- [x] CI workflow file present; could not be run locally (no `act`).
- [x] This report.

Phase 1 brief acceptance: app starts with documented commands; project create/retrieve/edit/delete
tested; project data survives a new app instance (and the Compose DB volume); job creation
associated with a project through its repository; invalid requests return problem+json; health
endpoint responds; tests executed with real results above; UI reads only backend data.

## Known gaps and deviations

- **Project edit/view/delete endpoints** (`GET/PATCH/DELETE /projects/{id}`) are not in the API
  contract table; added for the Phase 1 brief. Delete is a soft delete (`archived_at`). Needs a
  contract review in slice 1b or a decision to keep them.
- **Job states queued/running/completed/failed** exist in the enum and state machine, but no job
  reaches them in this slice: there is no intake (1b) or execution (1c). Jobs are honestly held in
  `validating` with `held_reason`. The 13-stage timeline is derived from real state (only "held" or
  "not run" is ever shown).
- **Duplicate-job key** uses (`repository_id`, `ref`, `profile_hash`) because no commit SHA exists
  yet; the design says commit SHA. Slice 1b must switch to the SHA after pinning.
- **Row-level security** is not enabled; tenant scoping is by `org_id` in every query only.
- **Rate limits, `RateLimit-*` headers, `Deprecation`/`Sunset`** not implemented.
- **`If-Match` is optional** on cancel and PATCH (enforced when sent). The contract makes it
  mandatory with `400 if_match_required`; deferred so the UI could stay simple in 1a.
- **Audit table grants**: no DB role without UPDATE/DELETE yet; immutability relies on the chain.
- **SSE** polls the outbox once per second; fine for 1a, should use LISTEN/NOTIFY in 1d.
- **Frontend types** are hand-written, not generated from OpenAPI.
- **Windows quirks**: `uv run pytest` may be blocked by Windows App Control; `python -m pytest` is
  used everywhere. `uv sync` occasionally fails to replace `qaswarm-0.1.0.dist-info` on OneDrive;
  re-running succeeds.
- 4 ESLint `react-refresh/only-export-components` warnings remain (constants exported next to components).

## Deferred (out of scope for 1a, per the prompt)

Git network access, cloning, ref resolution, DNS pinning and private-address rejection (1b);
Docker worker execution, sandbox limits, worker cleanup, orphan reaper (1c); running any
repository code, test result taxonomy ingestion, flaky reruns, log tail on SSE, reports, audit
events endpoint (1d); scanners (2a); evidence store, DCS, triage (2b); Model Gateway and agents
(2c); quality gates and release decision (2d); performance, mutation, patches (3b–3d); OIDC and
RBAC from an identity provider (3e).

## Suggested adjustments for slice 1b

1. Decide whether `GET/PATCH/DELETE /projects/{id}` join the API contract (update
   `docs/design/08-api-specifications/01-api-contracts.md` and `contract_table.py`).
2. Replace the ref-based duplicate index with the commit-SHA-based one once pinning exists; keep a
   ref-based pre-check for the 409 before resolution.
3. Implement `POST /repositories/{id}/validate` and move `validation_status` to `valid` /
   `validation_failed` with the SSRF corpus from the 1b exit check.
4. Add a scheduler role (reaper loop every 30 s, job deadline check) as a separate process entry
   point; the queue functions are ready.
5. Introduce LISTEN/NOTIFY for the outbox so SSE latency meets the 2 s target.
