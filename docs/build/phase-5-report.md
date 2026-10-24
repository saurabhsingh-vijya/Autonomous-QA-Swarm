# Phase 5 report — Defect intelligence and fix proposals (RaOne)

Branch `feature-branch`, commit `1fb57c7` (backend) plus the web wiring commit that follows it.
Plan: `docs/build/phase-5-plan.md`. Everything here derives from persisted QA results and
evidence; no defect count, root cause or fix outcome is invented.

## What genuinely works

### Defect record (FR-032, FR-033)

Every failed API check that AG-08 correlates is persisted as a `Finding` with:

- `title`, `description`, `severity`, `status`, `confidence`, `dcs` and `dcs_breakdown`;
- `affected_tests` (every execution in the group, by id, name, scenario and status; grouping by
  fingerprint never discards an individual result, and `test_execution_ids` keeps the links);
- `reproducibility` (`attempted: false, runs: 0, reproduced: 0`, with the note that fresh-sandbox
  reproduction arrives in slice 2b and that the recorded inputs allow a manual replay);
- `evidence_ids` to content-addressed, redacted HTTP exchanges (`GET /findings/{id}/evidence`);
- `facts` (observed, verified statements) kept apart from `inferred` (labelled inferences);
- `root_causes`: rule-based hypotheses, each with its basis, the evidence ids it rests on, an
  `uncertainty` level and `verified: false`. Rules cover missing response, 404 (plus an HTML
  "not found" page pointing at a proxy or static server), 401/403, 405, 400/422, 429, 5xx
  (plus timeout wording and 502/503/504 gateway cases) and unexpected 2xx/3xx;
- `risk_priority` and `priority_breakdown`: Severity weight × Confidence factor × Exposure
  from the design, with every factor and the formula in the record;
- `history`: earlier findings with the same fingerprint on the same repository and organisation
  (`prior_occurrences`, `times_seen_before`, `first_seen`, `recurring`);
- `status_history` (every transition with actor, role, time and reason) and `triage`.

The DCS is not inflated by recurrence: a repeat across jobs is a recorded fact, not a reproduction
in a fresh sandbox, so single-run findings stay at 63 (Probable). Nothing can reach Confirmed in
this build, and the report says so.

### Same defect across runs

Fingerprints are stable, so the second job on the same repository links to the first:
`history.recurring = true`, `prior_occurrences[0]` names the earlier finding and job, a
"Seen before" fact is appended, and `GET /findings/{id}/history` lists all occurrences newest
first. A different repository never sees that history. The report's residual-risk section
states how many open findings recur.

Suppression carry-over (FR-037 semantics): a prior `false_positive` on the same fingerprint
within 90 days makes the new record `false_positive` with confidence `rejected`, the reason
recorded in `inferred`, priority 0, excluded from gates but still visible and reopenable. A prior
`fix_verified` would make the new record `reopened` (implemented; cannot occur yet).

### Explainable prioritisation

`GET /jobs/{id}/findings` sorts by risk priority then DCS and accepts comma-separated
`severity`, `confidence` and `status` filters. The report carries `findings_by_priority` and
`finding_summary.open` / `excluded`.

### Triage (FR-037, HA-07, HA-08)

`POST /findings/{id}/triage` with `If-Match` (ETag `"<id>:v<version>"`, enforced when sent):

| Action | Role | Rules |
|---|---|---|
| `mark_false_positive` | QA Lead (functional) / Security Reviewer (security) | reason required; confidence → `rejected` |
| `mark_duplicate` | QA Lead, QA Engineer | `duplicate_of` must name a finding in the org; evidence of both kept |
| `accept_risk` | QA Lead | reason and future `expires_at` required; `Approval` row HA-08 written; security findings refused with 501 (dual approval not built) |
| `reopen` | QA Lead, QA Engineer | from false_positive, duplicate, accepted_risk, not_reproducible, fix_verified; confidence recomputed from DCS |
| `request_reproduction` | any | `501` naming slice 2b (no sandbox) |

Illegal transitions return `409 invalid_state_transition`; stale ETags `412 etag_mismatch`;
missing reasons `422`. Every success bumps the version, appends to `status_history` and writes a
hash-chained audit event (`finding.<action>`); the chain verifies in the tests.

### Reporting (AG-11)

Findings in `false_positive`, `duplicate` or `not_reproducible` are excluded from QG-01/QG-02
and counted as `excluded`; accepted-risk and recurring findings are listed in residual risk.

## Patch proposals and verification: not implemented, stated honestly

The brief makes patches optional "when the repository and relevant source are available". No
repository source is fetched (intake is slice 1b) and no sandbox exists (slice 1c), so there is
nothing to diff against and nowhere to run regression tests in isolation. AG-09 and AG-10 remain
planned; `GET /jobs/{id}/patches`, `POST /patches/{id}/review`, `POST /patches/{id}/verifications`
and `GET /verifications/{id}` return `501` with `planned_slice: "3d"`, and the UI shows that text
instead of a form. No diff, no before/after test result and no "successful fix" is shown anywhere.

## Verification

Commands (backend from `backend/`, with `AQS_TEST_DATABASE_URL` set):

```
uv run python -m pytest -q      → 166 passed
make check                      → ruff clean, mypy "no issues found in 69 source files",
                                  166 backend tests passed, web lint/format/typecheck clean,
                                  web tests passed, vite build OK (exit 0)
```

New tests: `tests/unit/test_defect_rules.py` (7: risk priority matches the design's worked
examples; hypotheses cite evidence and state uncertainty; suppression/reopen carry-over incl.
90-day expiry; near-duplicate rule; AG-08 full record without discarding executions; triage
transition table; no rejected→rejected transition) and
`tests/integration/test_defect_intelligence.py` (4: real failing check → persisted record with
evidence, hypotheses, priority, ETag, then a second run linked by history and a third repository
isolated; triage role/reason/ETag/409/audit chain/HA-08 approval; suppression carry-over and
duplicate marking; patches still 501).

Live demonstration against a running API with the runner (port 8011, dev auth), repository
`https://github.com/raone-demo/phase5`, checks `GET /healthz` (expect 200) and
`GET /api/v1/statements` (expect 200, route does not exist):

```
QJ-1003 completed_with_warnings
   FND-0002 candidate medium probable dcs 63 prio 2.4
   title: GET http://localhost:8011/api/v1/statements responds 200: expected HTTP 200, observed 404
   affected: ['GET http://localhost:8011/api/v1/statements responds 200']
   repro: attempted False  "Not reproduced: fresh-sandbox reproduction runs arrive in slice 2b…"
   evidence: ['evd_01M5PC2F4P0ZAJK7407RNX7M1F']
   facts: ['Observed HTTP 404 where 200 was expected.', 'Observed in 1 execution(s) of this job; not yet reproduced in a fresh run.']
   hypotheses: [('The route is not registered at this path, or the contract path differs…', 'medium')]
   history: recurring False seen before 0 []
QJ-1004 completed_with_warnings
   FND-0003 candidate medium probable dcs 63 prio 2.4
   facts: [..., 'Seen before: 1 earlier job(s) on this repository, most recently FND-0002 in job QJ-1003 (candidate).']
   history: recurring True seen before 1 ['FND-0002@QJ-1003']
report residual: ['1 finding(s) recur from earlier jobs on this repository and are still unresolved.']
by priority: [('FND-0003', 2.4)]
```

## Known gaps and deferred items

- Reproduction runs, Confirmed findings, conflict reconciliation (`disputed` stays false: only
  one agent produces findings), flaky register and precision history (stability component fixed
  at the "fewer than 20 triaged results" credit of 8).
- Near-duplicate suggestions exist as a rule (`suggested_duplicates`) but are not surfaced in
  the API because only one signature family (`status:X!=Y`) exists today.
- Dual approval for accepting risk on security findings (no security findings yet).
- Patch proposal, review and independent verification (slice 3d) as explained above.
- Exposure is fixed at `external` (1.0) for API checks; code-level exposure needs source intake.

## UI (phase 5 wiring)

- **SCR-11 Defect Evidence & Investigation**: status filter chips (All / Open / Rejected /
  Accepted risk) call the API filter; the detail card shows, in order, description, verified facts
  vs inferred notes, likely root causes (uncertainty chip, basis, evidence links that open the
  drawer, and the line "rule-based and unverified; none changes the score"), priority with the
  formula line, DCS meter and breakdown, reproducibility card, affected tests, "Seen before"
  history from `/history` (or "Not seen before on this repository"), status timeline, and the
  triage panel with only the legal actions for the current status (reason dialog for false
  positive, duplicate target from history, expiry for accept risk, reopen). "Request
  reproduction" is disabled with "Needs a fresh sandbox (slice 2b)"; the patch panel states that
  proposals need repository source and a sandbox (slice 3d). Toasts: past tense on success,
  "Finding changed since you read it" on 412, the problem detail on 403.
- **SCR-14 Reports**: "Findings by priority" table with open/excluded counts.
- **Dashboard**: "Open findings" tile (candidate + reopened) with recorded/confirmed note.

Web checks: lint clean, format check clean, typecheck clean, `vitest` 7 files / 67 tests passed,
`vite build` OK. Gaps: the acting role is the app's fixed dev role ("QA Lead"); buttons are not
hidden per role, the API's 403 is shown instead; accept-risk expiry is sent as local midnight of
the chosen date.
