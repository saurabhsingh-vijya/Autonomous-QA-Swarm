# Phase 2 plan — Real QA execution engine

Branch: `feature/mvp-continue` (from `feature-branch` @ 4cf5751). Source of truth: `docs/design/`.
This phase turns the held job lifecycle of slice 1a into a real pipeline: intake pins a commit,
the scheduler plans a task DAG, an **Execution Service** leases tasks and runs deterministic checks,
results and evidence are persisted, the UI shows progress, results, history and run comparison.

It covers BUILD_PLAN slices **1b (minimal intake)**, **1c (execution service, process runtime)**
and **1d (results, report, live job UI)** as far as this machine allows (no Docker, no gVisor).

## What exists and is kept

Queue (`qaswarm.workflow.queue`: lease / heartbeat / complete / fail / reaper / cancel), job and
task state machines, audit chain, outbox + SSE, idempotent `POST /jobs`, projects/repositories
API, the React shell and the four wired screens. All 128 backend and 21 web tests stay green.

## Design decisions

1. **Control plane still never executes repository code (SEC-001).** Intake uses
   `git ls-remote` only (ref → SHA). Fetching and reading the source happens in the Execution
   Service (`qaswarm_exec`), a separate process that talks to the control plane through a
   narrow internal HTTP API (`/internal/v1/exec/*`, shared token `AQS_EXEC_TOKEN`) and never
   touches the database.
2. **Runtime honesty.** `qaswarm_exec.runtime.SubprocessRuntime` runs tool processes in a
   disposable temp workspace with wall-clock, output-size and environment limits, and kills the
   process tree on timeout. It is **not** a sandbox: no network isolation, no cgroups. The worker
   run records `isolation: "process"`. Engines that execute repository code (pytest) run only when
   `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true`; otherwise they end **skipped** with the reason
   recorded. `DockerRuntime` exists as an interface and reports "not available" on this build.
3. **Check engines behind one interface** (`qaswarm_exec.tools.CheckEngine`): `engine_id`,
   `executes_repository_code`, `tool_version()`, `run(ctx) -> CheckResult`. Phase 2 engines:
   `snapshot_integrity` (tarball sha256 + inventory), `python_syntax` (`ast.parse`, no execution),
   `secret_scan` (pattern scan, redacted evidence) and `pytest` (JUnit XML → the six design
   test statuses). New engines register in `tools/registry.py`; nothing else changes.
4. **Outcome vocabulary.** A check run ends `passed | failed | skipped | error` (phase prompt).
   Individual tests use the design's `TestExecutionStatus`. `error` means the tool or
   infrastructure failed, never the code under test.
5. **Deterministic template plan** (`qaswarm.planning.template`): `env_prepare` → checks per
   profile. Task idempotency keys make re-planning a no-op. No LLM, no approvals in this phase
   (Deep / above-Smoke profiles produce no tasks and a warning).
6. **Scheduler role** (`python -m qaswarm.workflow.scheduler`): admits `validating` jobs (intake),
   plans `queued` jobs, skips dependents of failed tasks, advances `running → analyzing →
   reporting → completed[_with_warnings]`, fails the job on a critical-path failure, enforces task
   and job deadlines, reaps leases and confirms cancellation once every worker run has ended.
   For local dev it can run embedded in the API process (`AQS_EMBEDDED_SCHEDULER=true`), and so
   can one exec worker (`AQS_EMBEDDED_EXEC_WORKER=true`).
7. **Evidence** is content-addressed on the local filesystem (`AQS_EVIDENCE_DIR`), key layout
   `evidence/{org_id}/{sha256[0:2]}/{sha256}` (LLD), redacted **before** hashing, immutable.
8. **Fixture repositories** (`exec/fixtures/`, `AQS_DEV_FIXTURE_REPOS=true`) give deterministic,
   offline, hermetic runs for tests and the local demo: URL `https://fixtures.local/<name>`,
   refs are directories, the "commit SHA" is a tree hash. Clearly labelled dev-only.
9. **Cancel with workers.** `POST /jobs/{id}/cancel` moves to `cancelling` and cancels tasks; if
   no worker run is alive it confirms immediately (unchanged behaviour), otherwise the scheduler
   confirms after the exec worker reports the run destroyed.

## Files

Backend: `domain/enums.py` (+CheckOutcome), `db/models.py` (+WorkerRun, CheckRun, TestExecution,
EvidenceItem, Report; Job.snapshot_sha256), migration `20261024_phase2`, `intake/` (resolvers,
URL/DNS checks), `planning/template.py`, `workflow/queue.py` (+timeout, skip dependents),
`workflow/scheduler.py`, `evidence/store.py`, `reporting/basic.py`, `api/routers/exec_internal.py`,
`api/routers/jobs.py` (+tasks, checks, test-executions, evidence, report, compare),
`api/routers/audit.py`, `api/routers/system.py` (capabilities), schemas, contract table.

Exec: `qaswarm_exec/host/{worker,client,source}.py`, `runtime/{base,subprocess_runtime,docker_runtime}.py`,
`tools/{base,registry,snapshot_integrity,python_syntax,secret_scan,pytest_runner}.py`,
`results/{junit,worker_result}.py`, `__main__.py`, `fixtures/sample-python-app/`.

Web: types/hooks/client additions, `JobDetail` (stages from tasks, tasks, checks, evidence
viewer), `FunctionalResults` (SCR-06), `CompareRuns`, Jobs list columns, capability pill.

Docs: this plan, `phase-2-report.md`, README, `.env.example`, `docker-compose.yml`
(scheduler + exec-host services), Makefile targets, `.claude/skills/qa-swarm-dev/SKILL.md`.

## Risks

- Windows process-tree kill and path handling in the subprocess runtime (tested).
- `git ls-remote` needs network; tests use the fixture resolver so they stay offline.
- Scope: findings, DCS, gates and agents stay out (slices 2a–2d); reported as deferred.
