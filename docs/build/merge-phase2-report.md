# Merge report — Phase 2 execution engine + Phases 3/5 orchestration and defects (RaOne)

Merge of `origin/feature/mvp-continue` (Phase 2: intake, scheduler, Execution Service, check
engines, evidence store, compare; by Saurabh Singh, 3 commits from base 4cf5751) into
`feature/enhancement-saurabh` (UI/UX pass, Phase 3 multi-agent orchestration, Phase 5 defect
intelligence). The two branches had built two independent job pipelines on the same tables; this
merge makes them one pipeline rather than picking a side.

## The unified pipeline

```
POST /jobs ──► created → validating (held: waiting for the scheduler)
                 │  scheduler.admit: Intake & Pinning (git ls-remote / fixtures)
                 │     pinned → queued            not pinned + inputs → queued (unpinned, warning)
                 │     policy denied → blocked    not pinned + no inputs → failed
                 ▼
            planning: Orchestrator.plan_job builds ONE DAG (JobPlan persisted, hash, HA-05)
                 ├─ Execution Service tasks (only when pinned and AQS_EXEC_TOKEN is set):
                 │     env_prepare → check:snapshot_integrity / python_syntax / pytest / secret_scan
                 ├─ agent tasks (only when inputs were supplied):
                 │     AG-02 requirements → AG-03 functional, AG-04 api
                 └─ always: AG-08 evidence (soft-depends on every check/test task) → AG-11 report
                 ▼
            running → analyzing → reporting → completed[_with_warnings]   (Orchestrator.reconcile,
            called from scheduler.advance and after every agent task; critical-path failure → failed
            with a deterministic partial report; cancel → cancelling → cancelled once workers are gone)
```

Roles: **scheduler** (`python -m qaswarm.workflow.scheduler` or `AQS_EMBEDDED_SCHEDULER=true`),
**agent runner** (`AQS_RUNNER_ENABLED`, in the API, or `python -m qaswarm.workflow.runner`),
**exec host** (`python -m qaswarm_exec` or `AQS_EMBEDDED_EXEC_WORKER=true`). The exec host
leases only `env_prepare`/`check`; the runner leases only agent task types.

## What was merged how

| Area | Decision |
|---|---|
| Data model | One `TestExecution`, one `EvidenceItem`, one `Report` class each (union of both schemas): agent executions carry `scenario_id`, `test_type`, `meta`, `tool`, `evidence_id`; exec executions carry `node_id`, `file`, `check_run_id`, `commit_sha`. Evidence has both `storage_key` (object store) and inline `content`; agent evidence is written to the store **and** kept inline. Report has `partial` and `generator`. Phase 2's `WorkerRun`, `CheckRun` kept as is. |
| Migrations | Linear chain `b508… (1a) → c2e1f7a90d44 (phase 2) → 4a32de149091 (phase 3, rewritten as deltas on top of phase 2) → 7c1e5d2a9b40 (phase 5)`. Verified `upgrade head`, `downgrade base`, `upgrade head` on a fresh database. **Existing dev databases created from the old phase 3 chain must be recreated** (`DROP SCHEMA public CASCADE; CREATE SCHEMA public;` then `alembic upgrade head`). Tests use `metadata.create_all` and are unaffected. |
| Job creation | Phase 2's asynchronous admission (held for the scheduler). Phase 3's synchronous `Orchestrator.admit` was removed; its planning moved to `Orchestrator.plan_job`, called by `scheduler.plan`. |
| Intake | Phase 2's `run_intake` gained `allow_unpinned`: a non-policy intake failure on a job **with inputs** records a warning + `source.unpinned` audit event and queues the job without a commit (agents still run on the supplied inputs). Policy denials always block; jobs without inputs still fail at intake. |
| Planner | New `qaswarm.planning.combined.build_job_plan` joins Phase 2's template plan and Phase 3's agent plan; `validate_plan` knows the exec task types. Plan hash and HA-05 approval unchanged. |
| Job state | Phase 3's `reconcile` is the single state advancer (testing stages → analyzing → reporting → completed; critical failure → failed + partial report). Phase 2's `_advance_one` now only tracks `current_stage` and delegates. Reaping, task wall-clock expiry, dependency skipping, deadlines and worker-destruction confirmation stay Phase 2's. |
| Agents | AG-08 now also correlates failed check runs (`code.syntax`, `security.secret`, `integrity.snapshot`, located by file without line numbers) and failed pytest executions (`test.failure`, by file + normalised message) into findings with evidence links and rule-based hypotheses; AG-11's report carries `summary.{tasks,checks,tests}` and the `checks` list and narrates checks. |
| Reports | AG-11 writes the full report. Phase 2's `reporting.basic.build_report` writes the **partial** report for failed/cancelled jobs (`generator = basic-partial`); the report endpoint serves both (HTML via the matching renderer) and returns `501` for pdf/sarif/junit. |
| API | One owner per path: `/jobs/{id}/tasks`, `/test-executions` (with `X-Test-Counts`), `/evidence`, `/report` live in the results router with `{items}` bodies and the union of both field sets; Phase 2's `/checks`, `/worker-runs`, `/compare`, `/evidence/{id}[/content|/download]`, `/audit-events`, `/internal/v1/exec/*` kept. `/system/capabilities` is the union of both (execution flags, engines, agent runner, LLM provider, limits). Job detail: `warnings` is a `string[]`, plus `check_summary`, `test_summary`, `report_available`, `plan_available`, stage statuses incl. `not_planned`. |
| Stages | Union: intake from `commit_sha`, planning from the persisted plan / AG-02 task / awaiting approval, every other stage from its tasks, `not_planned` for stages without an engine. |
| Build/dev | Makefile (lint/mypy include `exec/src`, `dev-scheduler`, `dev-exec`), `.env.example` (both setting groups), `docker-compose.yml` rebuilt cleanly (the incoming file was corrupted to 33 k lines): postgres, api (runner on), scheduler, exec-host (profile `exec`, needs `AQS_EXEC_TOKEN`), web. |
| Web | Our UI (tokens, component library, Phase 3/5 screens) is the base; Phase 2's checks table, compare-runs screen, worker runs, capability pill and pytest results were ported onto it; Phase 2's parallel `JobDetail`/`FunctionalResults` rewrites were dropped. See the "Web" section below. |

## Verification (backend)

```
ruff check src tests ../exec/src   → All checks passed!
ruff format --check                → clean
mypy src ../exec/src               → Success: no issues found in 105 source files
python -m pytest tests -q          → 209 passed   (171 unit + 38 integration; both branches' suites)
alembic upgrade head / downgrade base / upgrade head on a fresh DB → 4 up, 4 down, 4 up, clean
```

Test adjustments made for the unified behaviour (all stated in the diffs): Phase 2's pipeline
tests drive the agent runner alongside the worker, expect 6 tasks per job (4 exec + evidence +
report), `{items}` bodies, `not_planned` stages, AG-11's report with a verdict, and
`completed_with_warnings` (QG-04 is inconclusive when no scenarios were supplied — never a silent
"completed"). Phase 3/5 tests drive the scheduler with a stub resolver that cannot reach the
fake GitHub URLs, exercising the unpinned path.

## Live run (merged API on port 8012, embedded scheduler + exec worker + agent runner, fixture repo `sample-python-app`, code execution allowed for the demo)

Job QJ-1001 (ref `main`, with requirements + 2 API checks):

```
checks   {'failed': 3, 'passed': 2}   tests {'failed': 3, 'passed': 6, 'skipped': 2}
  env_prepare passed · snapshot_integrity passed
  pytest failed: 2 test(s) failed: tests.test_money::test_rounds_half_even, …
  python_syntax failed: scripts/legacy_report.py:4 '(' was never closed
  secret_scan failed: 1 potential secret(s) found (1 high): aws-access-key-id in config/settings_example.py
findings (phase 5 on phase 2 data, each with evidence and an unverified hypothesis):
  FND-0004 code.syntax      high   dcs 63 prio 4.2  scripts/legacy_report.py
  FND-0005 security.secret  high   dcs 63 prio 4.2  config/settings_example.py
  FND-0001 test.failure     medium dcs 63 prio 2.4  tests.test_money::test_rounds_half_even (AssertionError 2.67 == 2.68)
  FND-0002 test.failure     medium dcs 63 prio 2.4  tests.test_money::test_rejects_sub_minor_unit_amount (DID NOT RAISE)
  FND-0003 api.contract     medium dcs 63 prio 2.4  GET /api/v1/statements → 404
verdict NOT_READY | Blocking gate(s) failed: QG-03.
```

Job QJ-1003 (ref `fix-rounding`, same inputs): 10 tasks succeeded (5 exec + 5 agent), checks
all passed, pytest 7 passed, the API-contract finding recurs with `history.times_seen_before = 2`
(linked to QJ-1001/QJ-1002), evidence kinds `environment_manifest, log ×5, source_inventory,
junit_xml, scanner_report ×2, http_exchange ×2`, `/evidence/{id}/content` serves the fetch log,
`GET /jobs/QJ-1003/compare?with=QJ-1001` → `check_deltas {'unchanged': 2, 'improved': 3}`,
`test_deltas {'unchanged': 9, 'improved': 2}`; HTML report 200. No ERROR lines in the API log.

## Honest limitations after the merge

- The process runtime is still not a sandbox; pytest runs only with
  `AQS_EXEC_ALLOW_UNSANDBOXED_CODE_EXECUTION=true` on a disposable host.
- Findings from check runs and pytest are single-run (DCS 63, Probable at most); reproduction
  runs, flaky register and patch proposals remain unbuilt.
- Functional scenarios derived from supplied requirements are still recorded as `skipped`; only
  the repository's own pytest suite executes.
- `AG-03`/`AG-05` ids on check tasks come from Phase 2's template (they label which role the
  engine serves); those agents' own logic does not run for check tasks.
- The agent runner is a single in-process thread by default; multi-runner fairness was not
  load-tested.

## Web

Our UI is the base; Phase 2's features were ported onto it against the merged API, and its
parallel `JobDetail` / `FunctionalResults` rewrites and `*.phase2.ts` API layer were dropped
(one API layer in `api/types.ts`, `client.ts`, `hooks.ts`).

- AppShell mode pill from `/system/capabilities`: execution off (agent checks on supplied inputs
  only) / on, deterministic checks only / on, repository code runs UNSANDBOXED (dev only).
- Job detail: repository checks table (outcome badges, failure message, log evidence opening the
  evidence drawer with `/evidence/{id}/content`), worker runs, snapshot digest, "Previous runs of
  this repository" with Compare links, exec tasks labelled with their engine, warnings as a list.
- Compare runs screen (`/jobs/:jobId/compare/:otherId`) with check and test deltas.
- Results screen: pytest executions (node id, file, commit) plus agent scenarios with job-wide
  counts from `X-Test-Counts`, and a repository checks section; API tab unchanged.
- Reports: partial reports (failed/cancelled jobs) rendered with their checks/tests and
  limitations; full reports show `summary.checks`.
- Settings: execution card (token state, runtime, unsandboxed flag, engines, embedded roles,
  fixtures). Defects: locations rendered for API, pytest and check-engine findings.

Web checks: format check clean, lint 0 errors, typecheck clean, `vitest` 9 files / 86 tests
passed (was 67), `vite build` OK. Not done: a browser smoke of the merged UI against the live
API (the backend live run above was driven over HTTP).

## Second merge: `feature/enhancement-saurabh` into `origin/feature/mvp-continue` (phases 4 and 6)

The remote branch had moved on by 14 commits (Phase 4 targets/engines/reruns, Phase 6 hardening).
Both sides were kept: one `Job.inputs` document carries phase 3 (`requirements`, `api_checks`) and
phase 4 (`target_id`, `testing`, `rerun`) keys; the combined planner passes the resolved target to
the template planner; the scheduler runs the HA-01 refusal check, then intake with the unpinned
fallback; the phase 3 migration now follows the phase 4 one (chain `1a → phase 2 → phase 4 →
phase 3 → phase 5`); capabilities are the union of both models; the results router adopts the
function-scoped `get_db` rule. Backend after the merge: ruff and mypy clean, 274 tests passed
(Chromium installed for the browser engine tests). Web checks were not re-run on this merge
(no web conflicts; the remote's 14 commits touched only `web/package.json` and its lock file).
