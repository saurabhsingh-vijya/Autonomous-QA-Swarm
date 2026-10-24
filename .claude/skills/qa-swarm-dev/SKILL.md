---
name: qa-swarm-dev
description: How to develop, run and test the Autonomous QA Swarm monorepo (backend control plane, exec host agent, web UI) — the execution-engine architecture, the non-negotiable rules, the exact commands that work on Windows without Docker, and the phase plan/report convention. Load whenever editing backend/, exec/ or web/ in this repo.
---

# Autonomous QA Swarm — developer skill

## Rules that override everything (from `CLAUDE.md`)
- `docs/design/` is the source of truth; cite the FR/SEC/NFR id when you deviate and record it in `docs/DECISIONS.md`.
- **SEC-001:** the control plane (`backend/`) never fetches, builds or runs repository code. Only the Execution Service (`exec/`) does, and only through a runtime.
- No secrets in code, logs, fixtures or the database. Evidence text passes `telemetry.logging.redact_text` **before** hashing. Fixture "secrets" are documented example keys only (e.g. the AWS docs key).
- Never claim something works unless you ran it. Unbuilt endpoints return `501` with `planned_slice`; unbuilt UI says "Not implemented in this phase".
- Phases: write `docs/build/phase-<id>-plan.md` first, `docs/build/phase-<id>-report.md` with real output last. Commit per step on the phase branch; never push unless asked. Commits end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`.

## Architecture in one screen
```
web (React/Vite :5173) ──/api/v1──▶ backend FastAPI (:8000) ──▶ PostgreSQL 16
                                        │  scheduler role (admit→pin→plan→reap→expire→propagate→advance→deadlines→confirm)
                                        │  /internal/v1/exec/*  (X-Exec-Token)
                                        ▼
                               exec host agent qaswarm_exec (no DB)
                               lease → fetch pinned commit → SubprocessRuntime → engines → evidence → worker_result/1
```
- A **job** is pinned at intake (`intake/resolvers.py`: `git ls-remote --symref`, DNS/SSRF checks in `intake/hosts.py`), planned by `planning/template.py` into tasks (`env_prepare` critical + one `check` task per engine), leased from the PostgreSQL queue (`workflow/queue.py`: `FOR UPDATE SKIP LOCKED`, 90 s lease, 30 s heartbeat, 2 retries, backoff 30/120 s).
- **Check engines** (`exec/src/qaswarm_exec/tools/`): `snapshot_integrity`, `python_syntax`, `secret_scan`, `pytest`. Outcomes `passed | failed | skipped | error`. `pytest` executes repository code, so the worker refuses it (→ `skipped`) unless `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true`.
- **Persistence** (`db/models.py`): `WorkerRun`, `CheckRun`, `TestExecution`, `EvidenceItem` (content-addressed under `AQS_EVIDENCE_DIR/{org}/{sha[:2]}/{sha}`), `Report`. Results are validated against `worker_result/1` JSON schema; invalid → attempt failed `E-EXEC-004` (retryable) and `422`.
- **Stages** in the UI are derived (`api/services/jobs.py::_stages`) from tasks + job state, 13 stages; stages not in the plan show `skipped · not in plan`.
- Dev fixtures: `https://fixtures.local/local/<name>` with `AQS_DEV_FIXTURE_REPOS=true`; refs are directories under `exec/fixtures/<name>/refs/`, commit SHA = deterministic tree hash. Sample: `sample-python-app` (`main` has a rounding bug, a syntax error and a doc-example key; `fix-rounding` is clean).

## Commands that actually work here (Windows 11, no Docker)
Backend (`cd backend`): `uv` is installed as a pip module → always `python -m uv …`.
```bash
# embedded Postgres (pgserver) — see D:\autonomous-qa-swarm-local-backup\pg\run_pg.py; URLs:
#   postgresql+psycopg://qaswarm:qaswarm-dev-only@127.0.0.1:59137/qaswarm  (+ qaswarm_test)
python -m uv sync --all-groups
AQS_TEST_DATABASE_URL=<test url> AQS_DEV_AUTH=true python -m uv run python -m pytest tests -q
python -m uv run ruff check src tests ../exec/src && python -m uv run ruff format --check src tests ../exec/src
python -m uv run mypy src ../exec/src
AQS_DATABASE_URL=<url> python -m uv run alembic upgrade head
# single process: API + scheduler + exec worker
AQS_DATABASE_URL=<url> AQS_DEV_AUTH=true AQS_EXEC_TOKEN=dev-exec-token AQS_DEV_FIXTURE_REPOS=true \
AQS_EMBEDDED_SCHEDULER=true AQS_EMBEDDED_EXEC_WORKER=true \
python -m uv run uvicorn qaswarm.api.app:create_app --factory --port 8000
```
Web (`cd web`): `npm ci`, `npm run typecheck`, `npm run lint`, `npx vitest run`, `npm run build`, `npm run dev` (:5173, proxies `/api` to :8000). Dev auth headers: `X-Dev-User`, `X-Dev-Role` (SSE: `?dev_user=&dev_role=`).

Always-use-`python -m pytest` (not bare `pytest`) — Windows App Control blocks the shim.

## Adding things
- **New check engine:** subclass in `exec/src/qaswarm_exec/tools/`, register in `tools/registry.py`, add it to `planning/template.py::ENGINE_STAGES`, set `executes_repository_code` honestly, add a unit test in `backend/tests/unit/test_phase2_engines_and_runtime.py`.
- **New API endpoint:** router in `api/routers/`, service in `api/services/`, schema in `api/schemas.py`, mark it in `api/contract_table.py` (contract endpoints) or `ADDITIONAL`, test in `tests/integration/`.
- **New migration:** `python -m uv run alembic revision --autogenerate -m "…"`, then verify `upgrade head` + `downgrade base` + `upgrade head`.
- **New web screen:** component in `web/src/screens/`, remove `plannedSlice` from its `registry.ts` entry, route in `App.tsx`, title in `App.test.tsx::TITLE_BY_ID`.

## Gotchas
- `get_db` rolls back on exceptions: if a request must persist state *and* fail (e.g. invalid worker result), `session.commit()` before raising `Problem`.
- The worker may lose its lease before a run starts (`LeaseLostError` from `create_worker_run`); it must exit quietly and skip destroy.
- Fixture URL paths reject `.`/`..` segments (policy error, not "unknown fixture").
- `exec/tools/__init__.py` must not import `registry` (circular import via `results.junit`).
- On Windows `os.killpg`/`start_new_session` do not exist: `subprocess_runtime.py` uses `creationflags` + `getattr` guards; keep it that way.
