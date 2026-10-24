# RaOne — Autonomous AI-Powered QA Platform

RaOne is a local-first, multi-agent platform for software testing, defect detection, evidence
collection and independent verification. It runs fully locally by default: no mandatory cloud
services or external AI APIs. (The original concept was named "Autonomous QA Swarm"; that name
remains only in the historical design documents under `docs/design/`.)

It is an open-source, self-hostable QA platform in which specialized AI agents, coordinated by a
deterministic workflow engine, plan and run tests against a **pinned commit** inside **disposable
sandboxes**, correlate evidence, propose fixes for human review and independently verify them.

Two principles override everything else:

1. **Agents propose, deterministic services dispose, humans approve.** Agents never execute code,
   never hold credentials and never change a repository.
2. **No evidence, no defect.** Nothing is reported as a confirmed defect without reproducible evidence.

> **Status: concept build, slice 1a + phase 3 orchestration.** The control plane never executes
> repository code (SEC-001). Nothing in this build fetches, builds or runs a repository. A job
> created **with inputs** (requirement texts and/or API checks) runs a real multi-agent flow on
> deterministic adapters: requirements analysis → API checks against allow-listed local hosts →
> evidence correlation → quality gates and report. A job created without inputs is held at
> *Intake & Pinning* with the reason "intake arrives in slice 1b". Functional scenarios are recorded
> as `skipped` (no sandbox execution engine yet). All UI data comes from the API; the seeded
> organization is labelled "Sample data — no repository code executed".

The design is the source of truth: [`docs/design/`](docs/design/README.md). Build plan and phase
prompts: [`docs/build/`](docs/build/BUILD_PLAN.md). Phase reports: `docs/build/phase-<id>-report.md`.

## Architecture summary

| Layer | Implementation (phase 2) |
|---|---|
| Web UI (`web/`) | React 18 + TypeScript + Vite, Tailwind, React Router, TanStack Query. App shell with the 15 screens; Dashboard, Repositories, New QA Job, Live Job Execution (13-stage timeline, tasks, checks, evidence drawer, report), Functional Test Results and run comparison are wired to the API. The mode pill is driven by `/system/capabilities`. |
| API Gateway (`backend/src/qaswarm/api`) | FastAPI under `/api/v1`: RFC 9457 `problem+json` errors with `error_code`, correlation IDs, dev-only header auth, `Idempotency-Key`, cursor pagination, ETags, SSE. Every contract endpoint not built yet returns `501` with its planned slice. |
| Domain (`qaswarm.domain`) | Enums exactly as the LLD/data model define them; `JobStateMachine` and `TaskStateMachine` built from the LLD transition tables. |
| Agents (`qaswarm.agents`) | AG-02 Requirements Analysis, AG-03 Functional Testing (skips honestly), AG-04 API Testing (local allow-list, safe methods), AG-08 Evidence Analysis (DCS, facts vs inferences), AG-11 QA Reporting (QG-01…08, verdict). Deterministic by default; optional local Ollama adapter for AG-02 proposals (`AQS_LLM_PROVIDER=ollama`). Outputs are schema-validated and persisted with input/output hashes. |
| Planning / policy (`qaswarm.planning`, `qaswarm.policy`) | Plan DAG with hard/soft dependencies, validation and hash; deny-by-default local policy for API checks (GET/HEAD/OPTIONS to `AQS_API_ALLOWED_HOSTS` only). |
| Orchestrator + runner (`qaswarm.workflow.orchestrator`, `.runner`) | Admits jobs, persists the plan, HA-05 plan approval, dispatches leased tasks to agents, persists outputs/evidence/executions/findings/report, reconciles job state, cancellation and critical-path failure. In-process runner thread (`AQS_RUNNER_ENABLED=true`) or `python -m qaswarm.workflow.runner`. |
| Workflow (`qaswarm.workflow`) | PostgreSQL task queue: `enqueue` (unique idempotency key), `lease` (`FOR UPDATE SKIP LOCKED`, 90 s lease), `heartbeat`, `complete`, `fail`, backoff 30 s / 120 s ± 20 %, `reap_expired_leases`. |
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

Pipeline roles: the **scheduler** (`make dev-scheduler`, or `AQS_EMBEDDED_SCHEDULER=true` inside
the API) runs Intake & Pinning, builds the combined plan and advances job state; the **agent
runner** (`AQS_RUNNER_ENABLED=true`, default, inside the API, or `python -m qaswarm.workflow.runner`)
executes agent tasks; the **exec host** (`make dev-exec`, or `AQS_EMBEDDED_EXEC_WORKER=true` with
`AQS_EXEC_TOKEN`) runs repository checks. Without `AQS_EXEC_TOKEN` repository checks are not
planned and the job runs on its supplied inputs only; a job whose ref cannot be pinned but that
carries inputs runs unpinned with a recorded warning, a job with neither fails at intake.
`AQS_DEV_FIXTURE_REPOS=true` serves `https://fixtures.local/local/<name>` from `exec/fixtures`.

Orchestration settings: `AQS_RUNNER_ENABLED` (default `true`; start the in-process runner with the
API), `AQS_RUNNER_POLL_SECONDS`, `AQS_API_ALLOWED_HOSTS` (default `localhost,127.0.0.1`),
`AQS_LLM_PROVIDER` (`none` | `ollama`), `AQS_LLM_BASE_URL`, `AQS_LLM_MODEL`,
`AQS_LLM_TIMEOUT_SECONDS`, `AQS_LLM_RATE_LIMIT_PER_MINUTE`. With `none` every agent output is
labelled `deterministic`; nothing is ever presented as an LLM result. Hosted providers are not
supported.

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
| `POST /api/v1/jobs` | Requires `Idempotency-Key`. Same key + same body within 24 h replays the original response (`Idempotent-Replayed: true`); same key + different body → `422 idempotency_key_reused`; active job for the same repository + ref + profiles → `409 job_duplicate_active` with `existing_job` unless `force_new=true` by a QA Lead. Body accepts `inputs: {requirements: [..], api_checks: [{method,url,expected_status,priority}]}` and `require_plan_approval`. With inputs the job is planned and runs (`running`, or `awaiting_approval` for HA-05); without inputs it is held in `validating`. |
| `GET /api/v1/jobs/{id}/plan`, `POST /api/v1/jobs/{id}/plan/approval` | Persisted plan DAG with hash; approve/reject (QA Lead only, reject needs a reason and cancels the job). |
| `GET /api/v1/jobs/{id}/tasks` | Tasks with attempts and schema-validated agent outputs (adapter, model ref, hashes, tokens, duration, payload). |
| `GET /api/v1/jobs/{id}/test-executions[?status=]`, `/findings[?severity=&confidence=&status=]`, `/evidence`, `GET /api/v1/findings/{id}[/evidence|/history]` | Persisted executions (six statuses plus `blocked`); findings sorted by risk priority with DCS breakdown, facts vs inferred, rule-based root-cause hypotheses with uncertainty, affected tests, reproducibility record, cross-run history; content-addressed evidence with redacted headers. |
| `POST /api/v1/findings/{id}/triage` | `mark_false_positive`, `mark_duplicate`, `accept_risk` (expiry, HA-08), `reopen`; role-checked, reason required, `If-Match` ETag, audited. `request_reproduction` → `501` (needs sandbox). |
| `GET /api/v1/jobs/{id}/quality-gates`, `GET /api/v1/jobs/{id}/report?format=json\|html` | QG-01…QG-08 with `inconclusive`/`not_applicable` honesty, verdict, deterministic narrative, check summary; a deterministic partial report is stored when a job fails or is cancelled before AG-11 ran; `pdf`, `sarif`, `junit` → `501` (slice 2d). |
| `GET /api/v1/jobs/{id}/checks`, `/worker-runs`, `/compare?with=<job_id>` | Check runs of the Execution Service engines, worker runs, and check/test deltas between two runs (improved / regressed / unchanged / added / removed). |
| `GET /api/v1/evidence/{id}`, `/content`, `/download` | Redacted evidence objects (not for Viewer / CI roles); agent evidence is stored both inline and as an object. |
| `GET /api/v1/audit-events` | Hash-chained audit log (Org Admin, QA Lead, Security Reviewer). |
| `/internal/v1/exec/*` | Execution Service only; `X-Exec-Token` required (`503` when unset, `401` when wrong). |
| `GET /api/v1/system/agents`, `GET /api/v1/system/capabilities` | Agent registry (implemented vs planned slice, kind, adapter, LLM provider) and build capabilities. |
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
| 1b Source intake | SSRF-safe validation, DNS pinning, ref → SHA, snapshot + evidence store | **Built (phase 2)**: `git ls-remote` pinning after DNS/private-address checks, content-addressed evidence store; snapshot digest recorded by the exec host |
| 1c Sandbox execution | Execution Service, disposable gVisor workers, limits, cleanup | **Partially built (phase 2)**: `qaswarm_exec` host agent with a process runtime (not a sandbox), leases over `/internal/v1/exec/*`; gVisor/Docker isolation not built |
| 1d Results and live job | pytest end-to-end, six statuses, flaky reruns, reports, results UI | **Partially built (phase 2)**: pytest via JUnit, check runs, test executions, run comparison; flaky reruns not built |
| Phase 2 Execution engine | Scheduler, intake, template checks (`snapshot_integrity`, `python_syntax`, `secret_scan`, `pytest`), exec worker, evidence store, compare | **Built** — see `docs/build/phase-2-report.md`; merged with phases 3/5 into one pipeline (see `docs/build/merge-phase2-report.md`) |
| Phase 3 Orchestration | Orchestrator, agent roles, plan DAG, runner, persisted outputs, findings, gates, report, HA-05 | **Built (deterministic adapters)** — see `docs/build/phase-3-report.md` |
| Phase 5 Defect intelligence | Defect records with evidence, root-cause hypotheses (unverified, with uncertainty), risk priority, cross-run history, suppression carry-over, triage (HA-07/HA-08) with audit and ETag | **Built** — patches/verification stay `501` (need source + sandbox); see `docs/build/phase-5-report.md` |
| 2a–2d, 3a–3e | See `docs/build/BUILD_PLAN.md` | Not started |

## Known limitations (phase 2)

- `SubprocessRuntime` isolates by process only. Repository code (pytest) runs **only** when the exec
  host sets `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true`; otherwise the pytest check is reported
  as `skipped` with the reason, never silently.
- Check engines: `snapshot_integrity`, `python_syntax`, `secret_scan`, `pytest`. Security /
  performance / mutation profiles produce a warning and no tasks.
- Report formats `pdf`, `sarif`, `junit`, flaky reruns, reproduction runs, patch proposals, OIDC: not
  implemented (`501` / "planned slice").
- Private-network targets are rejected at intake; there is no allow-list for internal git hosts yet.

## Non-negotiable rules (from `CLAUDE.md`)

- The control plane never executes repository code.
- No secrets in code, logs, prompts, fixtures or the database; logs pass through redaction.
- No automatic commit, push or merge of user repositories; patches are proposals only.
- Stubs are honest: `501 Not Implemented` or "Not implemented in this phase" in the UI. Never fabricated results.

Proposed licence: Apache-2.0 (open decision DEC-01).
