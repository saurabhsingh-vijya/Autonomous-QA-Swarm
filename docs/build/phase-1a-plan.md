# Phase 1a plan — Boilerplate and foundations

Branch: `phase-1a-boilerplate`. Source of truth: `docs/design/`. This plan covers the Phase 1 brief
("Core Foundation": shell, project CRUD, persistence, job creation and lifecycle, health, tests, README)
implemented on the Phase 1a layout from `docs/build/prompts/PHASE_1A_BOILERPLATE.md`.

## Repository layout

```
.
├── CLAUDE.md, README.md, Makefile, .env.example, .gitignore, .editorconfig, .pre-commit-config.yaml
├── docker-compose.yml            postgres:16, api, web (exec-host placeholder comment)
├── .github/workflows/ci.yml      backend (ruff, mypy, pytest + Postgres service), web (lint, test, build)
├── backend/                      uv project, FastAPI, SQLAlchemy 2, Alembic
│   ├── src/qaswarm/{api,domain,contracts,workflow,audit,db,telemetry,config.py}
│   ├── src/qaswarm/{planning,agents,policy,intake,modelgw,secrets,evidence,analysis,gates,reporting,notify,adapters}  (docstring-only)
│   ├── migrations/               Alembic
│   └── tests/{unit,integration}
├── exec/src/qaswarm_exec/        package skeleton + README (slice 1c)
└── web/                          Vite + React 18 + TS + Tailwind + React Router + TanStack Query
```

## Decisions

1. **Postgres everywhere.** No SQLite fallback: the queue uses `FOR UPDATE SKIP LOCKED` and partial unique
   indexes. Unit tests need no DB; integration tests need `AQS_TEST_DATABASE_URL` (Compose locally, service
   container in CI) and are skipped with a clear reason when it is unset.
2. **Sync SQLAlchemy + psycopg 3.** FastAPI runs sync handlers in its threadpool; the SSE endpoint is a sync
   generator that polls the outbox table. Simplest correct option for this slice.
3. **Project CRUD beyond the contract table.** The Phase 1 brief asks for view, edit and delete. The contract
   only lists `POST/GET /projects`. Added `GET/PATCH/DELETE /projects/{project_id}`; delete is a soft delete
   via `archived_at` as the data model prescribes. Recorded as a deviation for review.
4. **Jobs are associated with a project through the repository** (design: Job → Repository → Project). A job
   row also stores `project_id` denormalised for filtering. `POST /jobs` takes `repository_id`.
5. **Honest lifecycle.** `POST /jobs` creates `created` → `validating` and holds there with
   `held_reason = "intake arrives in slice 1b"`. Nothing is executed; no state is fabricated. Cancel works via
   the state machine (`validating` → `cancelling` → `cancelled` immediately, because there are no workers).
6. **Duplicate active job key** = (`repository_id`, `ref`, `profile_hash`) while no commit SHA exists
   (slice 1b will add the SHA). Partial unique index where state is non-terminal and `force_new = false`.
7. **Audit chain per organisation**: `hash = sha256(prev_hash + canonical_json(event))`, `prev_hash` of the
   first event is 64 zeros. Outbox rows (`outbox_events`) drive SSE; audit rows are written in the same
   transaction as the state change.
8. **Dev auth** (`AQS_DEV_AUTH=true`): `X-Dev-User`, `X-Dev-Role`; org is the single seeded org. Otherwise
   every `/api/v1` call returns 401 `unauthenticated` ("OIDC arrives in slice 3e"). Health endpoints are
   outside `/api/v1` and never require auth.
9. **501 stubs** are generated from one table (`qaswarm/api/contract_table.py`) that lists every endpoint in
   the API contract with its implementing slice, so the OpenAPI document shows the whole contract.
10. **Frontend** uses hand-written types in one file (`web/src/api/types.ts`) matching the backend schemas;
    `openapi-typescript` generation is a follow-up once the API stabilises.

## API shapes implemented in this slice

- `GET /healthz` → `{status:"ok"}`; `GET /readyz` → `{status:"ok", database:"reachable"}` or 503 problem.
- `POST /api/v1/projects {name, description?}` → 201; `GET /api/v1/projects` → `{items, next_cursor, limit}`;
  `GET/PATCH/DELETE /api/v1/projects/{id}`.
- `POST /api/v1/repositories {project_id, provider, url, default_branch?}` → 201 with
  `validation_status: "pending_validation"` and `validation_note`; syntactic checks only; 422
  `repository_url_rejected` with `reason` and `errors[]`. `GET /api/v1/repositories?project_id=`,
  `GET /api/v1/repositories/{id}`.
- `POST /api/v1/jobs` (requires `Idempotency-Key`) `{repository_id, ref, profiles{functional,security,performance}, force_new?}`
  → 202; replay → same body + `Idempotent-Replayed: true`; 400 `idempotency_key_required`; 422
  `idempotency_key_reused`; 409 `job_duplicate_active` with `existing_job`; 403 `insufficient_role` for
  `force_new` by non QA Lead.
- `GET /api/v1/jobs?state=&repository_id=&project_id=&limit=&cursor=`; `GET /api/v1/jobs/{id}` with `ETag`.
- `POST /api/v1/jobs/{id}/cancel {reason?}` → 202; 409 `invalid_state_transition` on terminal.
- `GET /api/v1/jobs/{id}/events` SSE with `id:` and `Last-Event-ID` resume.
- All other contract endpoints → 501 `not_implemented` with `planned_slice`.

## Risks

- Windows dev host: `make` and `uv` installed via winget; Docker Desktop required for Postgres.
- Hypothesis property test runtime kept small (max 200 examples).
- SSE through Vite proxy needs `proxy` config with no buffering; documented.
