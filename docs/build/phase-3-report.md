# Phase 3 report — Multi-agent QA orchestration (RaOne)

Branch `feature-branch`. Builds on slice 1a and the UI/UX pass. All orchestration is local-first:
deterministic adapters by default, no external AI, no cloud dependency.

## What genuinely works

A single `POST /api/v1/jobs` with `inputs` (requirements and/or API checks) now triggers a real
orchestration flow:

1. **AG-01 Orchestrator** (deterministic, `qaswarm.workflow.orchestrator`) admits the job
   (`created → validating → queued → planning`), runs the local policy over every configured
   check, builds the plan DAG with `qaswarm.planning`, validates it (acyclic, known agents,
   resolvable dependencies), persists a `JobPlan` with its hash, and enqueues one `Task` per node
   with hard and soft dependencies through the existing PostgreSQL queue. Plan approval (HA-05)
   holds the job in `awaiting_approval` when requested; a QA Lead approves or rejects through
   `POST /jobs/{id}/plan/approval` (rejection requires a reason and cancels the job).
2. An in-process **runner** (`qaswarm.workflow.runner`, started with the API when
   `AQS_RUNNER_ENABLED=true`, also runnable as `python -m qaswarm.workflow.runner`) leases tasks
   (`FOR UPDATE SKIP LOCKED`, 90 s lease, heartbeat), dispatches them to the registered agent for
   their task type, and reaps expired leases.
3. Each agent receives an `AgentTaskInput` (structured input, upstream outputs, config; SHA-256 of
   the input is stored for reproducibility) and returns an `AgentResult` validated against the
   agent's pydantic output model. The orchestrator persists:
   `AgentOutput` (adapter, agent kind, model ref, schema, validation status, input/output hashes,
   tokens, duration, payload), `EvidenceItem` (content-addressed, headers redacted),
   `TestExecution`, `Finding` (with DCS breakdown, verified facts vs inferred notes) and `Report`.
4. After every task the orchestrator reconciles the job: `running → analyzing → reporting →
   completed | completed_with_warnings`, `failed` on a critical-path task failure (dependent tasks
   are `skipped`), `cancelled` on cancellation (remaining tasks `cancelled`).

### Agent roles implemented

| Agent | Kind (as labelled in the API/UI) | What it does in this build |
|---|---|---|
| AG-01 Orchestrator | deterministic | Plan, enqueue, dispatch, reconcile, cancel, approval gate |
| AG-02 Requirements Analysis | deterministic, optional local LLM | Turns supplied requirement texts and API checks into traceable scenarios (`REQ-…`, `SCN-…`, P0/P1/P2, oracle). With `AQS_LLM_PROVIDER=ollama` it may add proposals; proposals without a known requirement ref or priority are dropped and counted (`dropped_llm_proposals`) |
| AG-03 Functional Testing | deterministic | Records every functional/manual scenario as `skipped` with the reason "no sandbox execution engine in this build (slice 1c)". It never reports a pass |
| AG-04 API Testing | deterministic | Executes configured HTTP checks against hosts on the local allow-list (`AQS_API_ALLOWED_HOSTS`, default localhost/127.0.0.1) with safe methods only; other checks are `blocked` with the policy reason; records `passed`/`failed`/`timed_out`/`infrastructure_error`, duration and redacted HTTP-exchange evidence |
| AG-08 Evidence Analysis | deterministic | Groups failures by fingerprint (category, location, signature), scores them with the single-run DCS rules (Probable at most, since nothing is reproduced yet), separates verified facts from inferences |
| AG-11 QA Reporting | deterministic | Builds the report from persisted records; evaluates QG-01/02/03/04/08; QG-05/06/07 are `not_applicable` with the slice that measures them; verdict logic from the design; narrative is a labelled deterministic template |

Not implemented (listed as planned in `GET /system/agents`): AG-05, AG-06, AG-07, AG-09, AG-10.

### Deterministic adapters vs LLM

- Default `AQS_LLM_PROVIDER=none`: every agent runs its deterministic logic and every
  `AgentOutput.adapter` is `deterministic` with `model_ref = null`. The UI labels this; nothing is
  presented as an LLM.
- `AQS_LLM_PROVIDER=ollama` (`AQS_LLM_BASE_URL`, `AQS_LLM_MODEL`, timeout, per-minute rate limit):
  `OllamaAdapter` handles timeouts (retryable), HTTP 429/5xx (retryable), malformed or non-JSON
  output (retryable `E-MODEL-003`) and a local rate limiter; only AG-02 uses it today, and only
  for additional scenario proposals that are validated before use. Hosted providers are not
  implemented and refused by configuration.

### Human approval

- Plan approval HA-05 is implemented (QA Lead only, audited, bound to the plan hash).
- Mutating HTTP methods are refused by the local policy with a message that they need target
  authorization (HA-01), which is not available yet; no code changes are applied by any agent.

## Endpoints added or un-stubbed

`GET /jobs/{id}/plan`, `POST /jobs/{id}/plan/approval`, `GET /jobs/{id}/tasks` (attempts and
outputs), `GET /jobs/{id}/test-executions`, `GET /jobs/{id}/findings`, `GET /findings/{id}`,
`GET /findings/{id}/evidence`, `GET /jobs/{id}/evidence`, `GET /jobs/{id}/quality-gates`,
`GET /jobs/{id}/report?format=json|html`, `GET /system/agents`. `POST /jobs` accepts `inputs`
and `require_plan_approval`. Job detail exposes `stages` derived from real task states,
`task_summary`, `warnings`, `report_available`, `plan_available`.

## Tests

Backend: 151 tests (`uv run python -m pytest -q`: `151 passed`), including new
`tests/unit/test_agents_and_planner.py` (11 tests: registry labels, deterministic requirements
agent and hashing, LLM proposal filtering, functional agent skip, API agent allow/block/redact,
policy deny-by-default, evidence grouping and fact/inference split, reporting never passes
unmeasured gates and applies hard blockers, planner validation and cycle detection, LLM adapter
malformed/timeout/rate-limit handling) and `tests/integration/test_orchestration.py` (6 tests:
full flow with persisted outputs/executions/evidence/findings/report and every read endpoint,
job without inputs is held honestly, failed agent retried twice then job `failed` with
dependants `skipped`, plan approval gate with role checks and rejection, cancellation mid-run,
agent registry endpoint).

Live run against a real API process (port 8010, runner enabled): job QJ-1002 went
`running → completed_with_warnings` with five succeeded tasks (all adapters `deterministic`),
executions `passed` (GET /healthz), `failed` (GET /nope → 404), `blocked`
(https://example.com, not allow-listed), `skipped` (functional, no engine); one finding
FND-0001 (medium, probable, DCS 63); gates QG-03 failed → verdict `NOT_READY`; HTML report
rendered.

`make check`: ruff, mypy (66 files), 151 backend tests, web lint/format/typecheck, web tests and
build all passed (web results from the UI/UX pass: 35 tests; the Phase 3 UI wiring is reported
in the section below once verified).

## Honest limitations

- No repository is fetched or executed; agents work on supplied inputs only (intake in 1b,
  sandbox in 1c). The functional agent therefore produces only `skipped` records.
- API checks run from the control plane against local allow-listed hosts, a deliberate deviation
  from the design's sandbox-based API testing, bounded by the deny-by-default local policy.
- Findings cannot reach Confirmed: reproduction runs (slice 2b) do not exist, so DCS tops out in
  the Probable band.
- Evidence lives in the database (content-addressed); the object store and signed URLs are 1b.
- QG-05/06/07 are reported `not_applicable`; QG-04 is `inconclusive` whenever planned scenarios
  were not executed (which is always true for functional scenarios in this build).
- The runner is in-process and single-worker by default; the queue already supports concurrent
  runners (tested with four threads).

## UI (phase 3 wiring)

All data on the screens below comes from the endpoints above; nothing is animated or estimated.

- **SCR-03 New QA Job**: new Inputs step (requirements, API checks limited to GET/HEAD/OPTIONS
  with a per-row policy warning, quick-add of RaOne's own health endpoint, "Require plan
  approval (HA-05)"); the review step states which agents will run or that a job without inputs
  is held.
- **SCR-04 Live Job Execution**: stage rail with the real stage statuses, plan panel with
  approve/reject shown only while `awaiting_approval` (reject needs a reason), tasks table with
  attempts and schema-validated outputs (adapter chip `deterministic` / `llm_assisted`, model
  ref, hashes, duration), execution and finding summaries, agent warnings, "Open HTML report"
  only when `report_available`.
- **SCR-05 Agent Collaboration Graph**: registry from `GET /system/agents` (implemented vs
  planned slice, kind, adapter, provider `none` shown as "No LLM provider configured"); the
  selected job's plan DAG rendered as SVG from `/plan` + `/tasks` (hard edges solid, soft
  dashed, colours from persisted task states).
- **SCR-06 / SCR-07 Functional and API results**: tables from `/test-executions`, functional
  rows show the skipped reason, API rows show method/URL/expected/observed with an evidence
  drawer (redacted headers, body excerpt).
- **SCR-11 Defect Evidence**: findings with DCS meter and breakdown, verified facts vs inferred
  notes, evidence drawer; triage stated as not available (slice 2b at the time of this phase).
- **SCR-14 Reports**: gates QG-01…QG-08 with result badges, verdict banner (or "Pending"),
  test summary, coverage, residual risk, narrative with its source label, HTML/JSON export;
  release decision stated as not available.
- **Dashboard**: tiles read the newest finished job's executions, findings and verdict, or say
  "No data yet".

Web checks after the wiring: lint 0 errors, format check clean, typecheck clean, `vitest`
6 files / 53 tests passed, `vite build` OK. Known gaps: evidence on the API results screen is
matched by id from the job's evidence list (no per-execution endpoint); the defects drawer shows
the first evidence item of a finding; agent permissions still come from the static catalogue.
