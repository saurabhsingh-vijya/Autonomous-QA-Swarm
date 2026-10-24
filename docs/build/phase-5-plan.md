# Phase 5 plan — Defect intelligence and fix proposals (RaOne)

Builds on Phase 3 orchestration. Everything below works only from persisted QA results and
evidence; no repository source and no sandbox exist in this build, so patch proposals and
isolated verification are explicitly **not** implemented (see "Out of scope, stated honestly").

## Design inputs

- FR-032…FR-037 (`docs/design/03-requirements/01-functional-requirements.md`): DCS components
  and partial credit, fingerprint dedup (exact → `duplicate`, near → suggested only), triage
  lifecycle with mandatory reasons, cross-job recurrence.
- `docs/design/11-quality-gates-and-reporting/01-evidence-and-defect-analysis.md`: DCS partial
  credit rules, fingerprint normalisation, decision trail, "same defect across jobs" rule.
- `docs/design/11-quality-gates-and-reporting/02-quality-gates-and-release-readiness.md`: Risk
  Priority = severity weight × confidence factor × exposure (sorting aid, not a gate).
- API contract: `POST /findings/{id}/triage` (actions `mark_false_positive`, `accept_risk`,
  `mark_duplicate`, `reopen`, `request_reproduction`; `If-Match`; 403/409/412/422).

## What will be built

### Backend

1. **Defect record** (`findings` table, new columns with server defaults):
   `description`, `affected_tests` (names + execution ids), `reproducibility`
   (`{"runs": 0, "reproduced": 0, "attempted": false, "note": ...}` until slice 2b),
   `root_causes` (list of `{hypothesis, basis, supporting_evidence, uncertainty}`),
   `risk_priority` + `priority_breakdown` (explainable), `history` (prior occurrences on the
   same repository: finding id, job, date, status; consecutive count), `duplicate_of`,
   `status_history`, `triage` (reason, actor, role, time, expiry), `disputed` (always false
   here; conflict reconciliation needs two agents on one fingerprint).
2. **`qaswarm.defects.intelligence`** (deterministic, no LLM): root-cause hypotheses from
   observed status, response body excerpt and headers, each with evidence references and an
   explicit uncertainty level; risk priority with breakdown; cross-run history lookup by
   `(org_id, fingerprint)` on jobs of the same repository; suppression carry-over (a prior
   `false_positive` on the same fingerprint within 90 days makes the new record
   `false_positive` with the reason recorded, never silently dropped); `fix_verified` → new
   record `reopened` (cannot occur yet, implemented for the lifecycle rule).
3. **AG-08** keeps grouping by fingerprint without discarding executions (every execution id and
   name stays linked); evidence excerpts are passed upstream so hypotheses cite them. DCS stays
   honest: single-run reproducibility 15, no inflation from recurrence (recurrence is a fact in
   the record, not a reproduction in a fresh sandbox).
4. **`qaswarm.defects.triage`**: finding lifecycle transitions (table from the data model),
   role rules (false positive: QA Lead for functional, Security Reviewer for security;
   duplicate: QA Lead or QA Engineer; accept risk: QA Lead with expiry, HA-08; reopen: QA
   Lead/QA Engineer), mandatory reasons, version bump, audit event, `Approval` row for HA-08.
   `request_reproduction` returns `501` naming slice 2b (no sandbox).
5. **API**: `POST /findings/{id}/triage` (removed from stubs; `If-Match` optional but enforced,
   ETag on finding reads), `GET /jobs/{id}/findings` sorted by risk priority with filters
   `severity`, `confidence`, `status`; finding responses carry the new fields; `GET
   /findings/{id}/history` lists prior and later occurrences.
6. **Reporting (AG-11)**: findings ordered by risk priority; `false_positive`, `duplicate`,
   `not_reproducible` excluded from gates and counted separately; residual risk mentions
   suppressed and accepted-risk findings.
7. **Tests**: unit (intelligence rules, priority math, triage transitions/roles), integration
   (real failing check → persisted finding with evidence; second job → history linked and
   consecutive count 2; triage false positive → audit event, version bump, ETag 412, 403 for
   wrong role; suppression carry-over on a third run; duplicate marking).

### Web (after the Phase 3 UI agent finishes, same screens)

SCR-11: triage actions with reason dialogs (role-aware), "Seen before" history panel, root
cause hypotheses with uncertainty labels and evidence links, priority breakdown, affected tests;
SCR-14: findings ordered by priority with status chips.

## Out of scope, stated honestly

- Patch proposals (AG-09), patch review (HA-06) and independent verification (AG-10): require
  repository source and a sandbox (slices 1b/1c/3d). Endpoints stay `501` with the slice.
- Reproduction runs (FR-035): need the sandbox; `request_reproduction` returns `501`.
- Near-duplicate suggestions (AC-101): only one signature family exists (`status:X!=Y`), so
  token similarity is implemented but will rarely trigger; shown as suggestion only.
- Flaky register / precision history: stability component stays at the "fewer than 20 triaged
  results" partial credit (8).

## Risks

- Alembic migration on `findings` with existing rows: all new columns get server defaults.
- Cross-run lookup must stay per repository and org (no leakage across projects).
