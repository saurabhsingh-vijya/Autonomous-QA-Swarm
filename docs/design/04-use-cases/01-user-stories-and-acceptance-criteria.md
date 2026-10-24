# User Stories and Acceptance Criteria

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document records the proposed user stories for Autonomous QA Swarm, grouped by feature F-01 to F-15. Each story names a persona from [Personas and user journeys](../01-product-vision/04-personas-and-user-journeys.md), gives two to four measurable Given/When/Then acceptance criteria and traces to requirements and acceptance criteria in [Functional requirements](../03-requirements/01-functional-requirements.md). Negative and edge stories (blocked targets, duplicate jobs, invalid agent output, flaky tests, reviewer-only false-positive marking) are included deliberately, because the platform's value depends on how it behaves when things go wrong. Every story is **Proposed**; Phase 1–3 stories are **Planned (MVP)**, later ones **Future**. No story is **Implemented / Verified**; that label will only be applied once code exists and the traced acceptance tests pass.

## Conventions

Priority follows the traced requirement (P0 MVP-critical, P1 MVP-important, P2 later). Roles that are not personas (Org Admin, CI Service Account) are named by their RBAC role. References to Northwind Fintech, QJ-1042 or FND-0193 are sample data and illustrative only. Thresholds are proposed defaults, configurable per project.

## F-01 Repository & Source Intake

### US-001 Register a repository by URL

As PER-02 Marco (Automation QA Engineer), I want to register a repository by HTTPS URL, so that I can run QA jobs on it without manual setup.

- **Given** a reachable HTTPS URL on an allowed host, **when** Marco submits it on SCR-02, **then** the repository is saved as "Valid" with its default branch resolved within 30 s.
- **Given** a registered repository, **when** a snapshot is created, **then** a SHA-256 checksum is stored and no repository code runs on the control plane.
- **Priority:** P0 · Planned (MVP), Phase 1
- **Traces to:** FR-001 (AC-001–AC-003), FR-004 (AC-010–AC-012)

### US-002 Reject unsafe repository URLs (negative)

As PER-02 Marco, I want URLs that resolve to private or internal addresses to be rejected, so that the platform cannot be used to probe internal networks.

- **Given** an `http://` URL, an RFC1918 IP literal or a host resolving to a cloud metadata address, **when** submitted, **then** the API returns `422` with a problem+json reason and no outbound fetch is made.
- **Given** DNS answers that change between validation and fetch, **when** the fetch occurs, **then** the pinned DNS result is used and a private address is still rejected.
- **Priority:** P0 · Planned (MVP), Phase 1
- **Traces to:** FR-001 (AC-001–AC-003)

### US-003 Pin a ref to an immutable commit

As PER-04 Daniel (Developer), I want my branch, tag or PR ref pinned to a commit SHA at job start, so that every result refers to exactly the code tested.

- **Given** ref `release/2.8`, **when** a job is created, **then** the resolved SHA (sample `7c9e2a1f4b`) is recorded and every task uses only that SHA, even if the branch moves later.
- **Given** a private repository, **when** accessed, **then** only a credential reference is stored and the raw token appears in 0 database rows, logs or reports.
- **Priority:** P0 · Planned (MVP), Phase 1–2
- **Traces to:** FR-002 (AC-004–AC-006), FR-003 (AC-007–AC-009)

## F-02 QA Job Configuration & Launch

### US-004 Launch a QA job with profiles

As PER-01 Priya (Manual QA Engineer), I want to launch a job by choosing profiles in a wizard, so that I can start testing without writing configuration files.

- **Given** a valid repository, **when** Priya reaches the Review step of SCR-03, **then** the policy summary, required approvals and estimated duration and budget are shown before submission.
- **Given** a scope limited to selected paths and a 2 h job limit, **when** the job runs, **then** no task runs outside those paths and the job ends `timed_out` at the limit.
- **Priority:** P0 · Planned (MVP), Phase 1
- **Traces to:** FR-005 (AC-013–AC-015), FR-007 (AC-019–AC-021)

### US-005 Prevent duplicate jobs (negative)

As a CI Service Account, I want retried submissions to return the original job, so that an unreliable CI network does not start duplicate jobs.

- **Given** a `POST /jobs` reusing an `Idempotency-Key` from the last 24 h, **when** resent, **then** the original response is returned and no job is created.
- **Given** an active job for the same repository, commit SHA and profile hash, **when** a request with a new key arrives, **then** the API returns `409` with a link to the existing job.
- **Given** `force_new=true`, **when** sent by a QA Lead, **then** a new job is created and audited; any other role receives `403`.
- **Priority:** P0 · Planned (MVP), Phase 1
- **Traces to:** FR-006 (AC-016–AC-018)

### US-006 Block jobs against unauthorized targets (negative)

As PER-05 Sofia (Application Security Engineer), I want jobs against a target without a valid authorization attestation to be blocked, so that we never test systems we are not permitted to test.

- **Given** an external target with no active TargetAuthorization (HA-01), **when** validation runs, **then** the job ends `blocked`, no task is leased and no traffic reaches the target.
- **Given** an attestation that expires while the job is queued, **when** execution would start, **then** authorization is re-checked and the job ends `blocked` with the reason shown.
- **Priority:** P0 · Planned (MVP), Phase 2
- **Traces to:** FR-050 (AC-148–AC-150)

## F-03 Planning & Orchestration

### US-007 Review and approve a job plan

As PER-03 Aisha (QA Lead), I want to review the task plan before high-impact profiles run, so that I control what executes against our systems.

- **Given** the plan approval gate is enabled, **when** planning completes, **then** the job enters `awaiting_approval` and no execution task is leased until HA-05 is recorded.
- **Given** Aisha rejects with a reason, **when** saved, **then** the job ends `cancelled` and the reason is in the audit trail.
- **Given** a plan DAG with a cycle or a task type not allowed by policy, **when** validated, **then** it is rejected before reaching the approval queue.
- **Priority:** P1 · Planned (MVP), Phase 1–2
- **Traces to:** FR-008 (AC-022–AC-024), FR-009 (AC-025–AC-027)

### US-008 Monitor and cancel a job with guaranteed cleanup

As PER-02 Marco, I want to watch a job live and cancel it knowing every worker is destroyed, so that nothing keeps consuming resources or hitting a target.

- **Given** SCR-04 is open, **when** a task changes state, **then** the change is shown within 2 s, and after a reconnect missed events are replayed from the last event ID.
- **Given** Marco cancels, **when** confirmed, **then** the job moves to `cancelling` immediately and to `cancelled` once all tasks are terminal.
- **Given** cancellation, **when** tasks stop, **then** 100% of the job's workers are destroyed within 60 s and evidence captured so far remains linked.
- **Priority:** P0 · Planned (MVP), Phase 1
- **Traces to:** FR-010 (AC-028–AC-030), FR-011 (AC-031–AC-033)

### US-009 Bound retries and reject invalid agent output (negative)

As PER-03 Aisha, I want failing or misbehaving agent tasks retried a fixed number of times and then stopped, so that jobs finish predictably and I can see what went wrong.

- **Given** a transient infrastructure error, **when** a task fails, **then** it is retried at most 2 times (backoff 30 s, 120 s, ±20% jitter) before ending `failed`.
- **Given** an agent output that fails schema validation, **when** received, **then** one corrective retry carries the validation errors; a second invalid output ends the task `invalid_output` and the output is never used.
- **Given** any task ending `failed`, `invalid_output` or `timed_out`, **when** the job finishes, **then** the job is not `completed` and the task is listed in the report.
- **Priority:** P0 · Planned (MVP), Phase 1
- **Traces to:** FR-012 (AC-034–AC-036)

## F-04 Requirements & Change Analysis

### US-010 Derive scenarios from requirements and the diff

As PER-01 Priya, I want stories, acceptance criteria and the OpenAPI spec turned into prioritized scenarios focused on changed modules, so that testing targets what changed.

- **Given** an OpenAPI file and linked stories, **when** planning runs, **then** every derived scenario links to its source requirement and carries a P0/P1/P2 priority.
- **Given** a diff touching `app/routers/statements.py` (sample), **when** change-impact analysis runs, **then** affected modules and tests are listed with the selection rationale.
- **Given** a requirement that cannot be mapped to a testable scenario, **when** analysis completes, **then** it is reported as "untestable or ambiguous" rather than dropped.
- **Priority:** P1 · Planned (MVP), Phase 2
- **Traces to:** FR-013 (AC-037–AC-039), FR-014 (AC-040–AC-042)

## F-05 Functional Testing

### US-011 Run existing test suites in a sandbox

As PER-02 Marco, I want our pytest, Vitest and Playwright suites to run unchanged in a sandbox, so that I get a trustworthy baseline without modifying CI.

- **Given** a pytest repository, **when** the Baseline Run executes, **then** each result has one status from `passed`, `failed`, `skipped`, `blocked`, `timed_out`, `infrastructure_error`, plus tool version, duration and worker ID.
- **Given** test execution, **when** a test attempts outbound network access, **then** the connection fails because network is off during execution.
- **Priority:** P0 · Planned (MVP), Phase 1
- **Traces to:** FR-015 (AC-043–AC-045), FR-017 (AC-049–AC-051)

### US-012 Separate flaky tests from defects (edge)

As PER-03 Aisha, I want tests that fail and then pass on rerun classified as flaky, so that noise neither blocks releases nor wastes triage time.

- **Given** a failed test, **when** re-run up to 2 times in fresh workers and it passes, **then** it is classified `flaky`, added to the Flaky Test Register and reported separately from defects.
- **Given** 3 flaky occurrences in 14 days, **when** quarantine is proposed, **then** the test leaves the QG-03 denominator only after Aisha acknowledges it.
- **Given** a test failing in all 3 runs, **when** classified, **then** it is a failure and goes to evidence correlation.
- **Priority:** P0 · Planned (MVP), Phase 1
- **Traces to:** FR-018 (AC-052–AC-054)

### US-013 Review generated tests before promotion

As PER-02 Marco, I want agent-generated tests to carry provenance and require my review, so that unreviewed AI-written code never joins our suite.

- **Given** a generated test, **when** displayed, **then** its provenance (agent, prompt template version, model route, source scenario) is shown.
- **Given** an unreviewed generated test, **when** gates are computed, **then** its result is advisory and excluded from QG-03.
- **Priority:** P1 · Planned (MVP), Phase 2
- **Traces to:** FR-016 (AC-046–AC-048)

## F-06 API Testing

### US-014 Check API schema conformance and negative cases

As PER-02 Marco, I want every documented endpoint tested for schema conformance and boundary inputs, so that contract breaks are caught before release.

- **Given** an OpenAPI document and an ephemeral target, **when** API testing runs, **then** the coverage matrix on SCR-07 shows each operation as tested, blocked or skipped with a reason.
- **Given** a response violating its schema, **when** recorded, **then** the request, response and violated schema path are stored as evidence.
- **Priority:** P1 · Planned (MVP), Phase 2
- **Traces to:** FR-019 (AC-055–AC-057), FR-020 (AC-058–AC-060)

### US-015 Detect object-level authorization flaws

As PER-05 Sofia, I want checks that one test user cannot read another's objects, so that IDOR issues like sample FND-0193 are found early.

- **Given** two scoped, short-lived test users on an authorized target, **when** user A requests user B's statements and receives `200` with B's data, **then** a candidate authorization finding is created with request/response evidence.
- **Given** a target without authorization attestation, **when** authz checks are planned, **then** they are not executed and are listed as `blocked`.
- **Priority:** P1 · Planned (MVP), Phase 2
- **Traces to:** FR-021 (AC-061–AC-063)

## F-07 Security Testing

### US-016 Run static, dependency and secret scans with redaction

As PER-05 Sofia, I want SAST, dependency and secret scans on every job with Security Quick or higher, with secret values masked, so that known issue classes surface consistently without spreading the secrets found.

- **Given** Security Quick, **when** the stage runs, **then** Semgrep CE, Gitleaks and OSV-Scanner results are recorded with tool name and version.
- **Given** a scanner alert, **when** it becomes a finding, **then** it starts `candidate` with source class "Scanner alert" and cannot be Confirmed without reachability or precondition evidence.
- **Given** a detected secret, **when** evidence, logs, prompts and reports are produced, **then** 0 plaintext occurrences remain; a redaction marker and short hash are shown instead.
- **Priority:** P0 · Planned (MVP), Phase 2
- **Traces to:** FR-022 (AC-064–AC-066), FR-023 (AC-067–AC-069), FR-024 (AC-070–AC-072)

### US-017 Run DAST only with explicit approval (negative)

As PER-05 Sofia, I want active DAST to run only after target authorization and my approval, so that active scanning never reaches an unapproved system.

- **Given** a Deep profile, **when** the target authorization (HA-01) is missing, **then** the job ends `blocked` during validation; **when** HA-02 or HA-05 is missing, **then** the job waits in `awaiting_approval`. In both cases no DAST task is leased.
- **Given** an approved DAST run, **when** it reaches 60 min, **then** it stops and partial results are kept with a limitation note.
- **Priority:** P2 · Future, Phase 4
- **Traces to:** FR-026 (AC-076–AC-078)

## F-08 Performance Testing

### US-018 Compare baseline and candidate performance

As PER-06 Kenji (Performance Test Engineer), I want a Baseline run compared with the previous baseline, so that I see regressions with statistical caveats.

- **Given** an approved Baseline run (HA-03), **when** it completes, **then** p50/p90/p95/p99, RPS and error rate appear next to the previous baseline with percentage deltas.
- **Given** fewer than 400 samples for an endpoint, **when** p95 is reported, **then** a sample-size warning is shown and that result alone cannot fail QG-05.
- **Priority:** P1 · Planned (MVP), Phase 3
- **Traces to:** FR-027 (AC-079–AC-081), FR-029 (AC-085–AC-087)

### US-019 Abort unsafe load automatically (edge)

As PER-06 Kenji, I want load runs to stop when the target degrades, so that a test never becomes an outage.

- **Given** a running load test, **when** error rate exceeds 20% for 60 s, the health check fails 3 times consecutively, or p95 exceeds 5× baseline for 2 min, **then** load stops and the abort reason is recorded.
- **Given** generator CPU above 90%, **when** detected, **then** the run is marked invalid (generator-bound) and excluded from comparisons.
- **Given** Stress, Spike or Soak, **when** submitted, **then** no load is generated before HA-03 and HA-05.
- **Priority:** P2 · Future, Phase 4 (abort rules also apply to MVP Smoke/Baseline)
- **Traces to:** FR-028 (AC-082–AC-084)

## F-09 Mutation Testing

### US-020 Measure test effectiveness on changed modules

As PER-02 Marco, I want mutation testing on changed modules with a correct score and explained survivors, so that I know whether our tests catch real faults.

- **Given** changed modules, **when** mutation runs, **then** at most 500 mutants are generated and score = killed / (killed + survived) × 100, excluding timed-out and invalid mutants (sample: 139/186 = 74.7%).
- **Given** a surviving mutant, **when** analyzed, **then** a suggested assertion is shown, labelled as a suggestion requiring review.
- **Priority:** P1 · Planned (MVP), Phase 3
- **Traces to:** FR-030 (AC-088–AC-090), FR-031 (AC-091–AC-093)

## F-10 Evidence & Defect Analysis

### US-021 See why a finding is confirmed

As PER-04 Daniel, I want each finding to show its evidence and Defect Confidence Score breakdown, so that I can trust or challenge it quickly.

- **Given** a finding, **when** opened on SCR-11, **then** the five DCS components and linked content-addressed evidence items are shown.
- **Given** DCS ≥ 80 without reproduction in a fresh sandbox (≥2 of 3 runs), **when** displayed, **then** the finding is Probable, not Confirmed.
- **Given** only LLM agent opinion supports a finding, **when** DCS is computed, **then** that opinion contributes only to "Independent corroboration".
- **Priority:** P0 · Planned (MVP), Phase 1–2
- **Traces to:** FR-032 (AC-094–AC-096), FR-033 (AC-097–AC-099), FR-035 (AC-103–AC-105)

### US-022 Merge duplicate findings

As PER-03 Aisha, I want identical issues reported by several agents merged, so that counts and gates are not inflated.

- **Given** two signals with the same fingerprint, **when** correlated, **then** one becomes `duplicate` with links preserved.
- **Given** a near match (signature similarity ≥ 0.9, same location), **when** detected, **then** it is only suggested as duplicate and needs confirmation.
- **Priority:** P0 · Planned (MVP), Phase 2
- **Traces to:** FR-034 (AC-100–AC-102)

### US-023 Require a reviewer for false-positive marking (negative)

As PER-05 Sofia, I want false-positive marking to require an authorized reviewer and a reason, so that real issues cannot be dismissed silently by an agent or unauthorized user.

- **Given** a security finding, **when** a Developer or any agent tries to mark it `false_positive`, **then** the request is rejected with `403`.
- **Given** a Security Reviewer marks it with a reason (HA-07), **when** saved, **then** a scoped suppression (rule + location fingerprint) with 90-day default expiry and an audit event are created.
- **Priority:** P0 · Planned (MVP), Phase 2
- **Traces to:** FR-037 (AC-109–AC-111)

### US-024 Flag disputed conclusions (edge)

As PER-03 Aisha, I want conflicting agent conclusions reproduced and, if unresolved, flagged Disputed, so that disagreements are never auto-resolved either way.

- **Given** the Functional Testing Agent reports a defect and the API Testing Agent's contract test passes, **when** correlated, **then** a targeted reproduction task is scheduled.
- **Given** reproduction does not resolve the conflict, **when** triage completes, **then** the finding is Disputed, stays `triaging` and enters the human triage queue.
- **Priority:** P1 · Planned (MVP), Phase 2
- **Traces to:** FR-036 (AC-106–AC-108)

## F-11 Patch Proposal & Independent Verification

### US-025 Review a proposed patch

As PER-04 Daniel, I want to review a minimal diff with rationale and evidence before it is verified, so that I stay accountable for code changes.

- **Given** a Confirmed finding, **when** a patch is proposed, **then** SCR-12 shows the diff, rationale, evidence links, risk notes and a "no auto-commit" notice.
- **Given** a user who is neither code owner nor QA Lead, **when** they approve, **then** the request is rejected with `403`.
- **Given** any patch state, **when** the platform acts, **then** no commit, push or merge is made to the repository.
- **Priority:** P0 · Planned (MVP), Phase 3
- **Traces to:** FR-038 (AC-112–AC-114), FR-039 (AC-115–AC-117), FR-041 (AC-121–AC-123)

### US-026 Verify a patch independently

As PER-03 Aisha, I want approved patches verified in a fresh sandbox without access to the patch author's reasoning, so that verification is independent.

- **Given** a patch `approved_for_verification`, **when** verification runs, **then** it uses the pinned commit plus the patch in a new worker and records fresh-sandbox metadata.
- **Given** the original reproduction still fails or a previously passing relevant test fails, **when** verification ends, **then** the patch is `verification_failed` with evidence.
- **Given** a check not re-run (for example performance), **when** results are shown, **then** the justification and limitation are stated.
- **Priority:** P0 · Planned (MVP), Phase 3
- **Traces to:** FR-040 (AC-118–AC-120)

## F-12 Quality Gates & Release Readiness

### US-027 Record a release decision from gate results

As PER-03 Aisha, I want a recommendation computed from QG-01 to QG-08 and a place to record my decision, so that releases are evidence-based and attributable.

- **Given** any open Confirmed Critical finding, **when** gates are evaluated, **then** the verdict is `NOT_READY` regardless of other scores.
- **Given** QG-04 or QG-08 inconclusive and no blocking gate failed, **when** evaluated, **then** the verdict is `INCONCLUSIVE`.
- **Given** a failed gate, **when** Aisha overrides it (HA-09) without a reason, **then** `422` is returned; with a reason, the report shows "Overridden", approver and reason, and residual risk stays listed.
- **Given** a verdict, **when** Aisha records her decision (HA-10), **then** name, time, decision and rationale are stored and audited.
- **Priority:** P0 · Planned (MVP), Phase 2
- **Traces to:** FR-042 (AC-124–AC-126), FR-043 (AC-127–AC-129), FR-046 (AC-136–AC-138)

## F-13 Reporting & History

### US-028 Export reports and search history

As PER-02 Marco, I want reports in JSON, HTML, PDF, JUnit XML and SARIF and a searchable job history, so that results feed CI dashboards and code-scanning tools.

- **Given** a job with ≤ 10,000 test executions, **when** a report is requested, **then** it is generated within 30 s and every finding links to evidence.
- **Given** the job history, **when** filtered by repository, state and date, **then** matching jobs are returned with cursor pagination.
- **Priority:** P0 · Planned (MVP), Phase 1–2
- **Traces to:** FR-044 (AC-130–AC-132), FR-045 (AC-133–AC-135), FR-047 (AC-139–AC-141)

## F-14 Administration, Settings & Integrations

### US-029 Use a local model and controlled egress

As an Org Admin, I want to route agents to a local open-weight model and control sandbox allow-lists, so that we can run without paid services and govern outbound traffic.

- **Given** a local model route, **when** saved, **then** all agent calls use it and 0 requests reach a hosted provider.
- **Given** a new allow-list entry, **when** requested, **then** it applies only after HA-04 and is audited.
- **Priority:** P0 · Planned (MVP), Phase 1–3
- **Traces to:** FR-051 (AC-151–AC-153), FR-052 (AC-154–AC-156), FR-053 (AC-157–AC-159)

## F-15 Audit & Governance

### US-030 Reconstruct who decided what

As PER-03 Aisha, I want an audit trail of approvals, overrides, triage actions and state transitions, so that any release decision can be explained later.

- **Given** a job, **when** its audit events are queried, **then** every approval (HA-01 to HA-11), triage action and state transition is listed with actor, time and correlation ID.
- **Given** an audit event altered in storage, **when** the hash chain is verified, **then** the break is detected and reported.
- **Priority:** P0 · Planned (MVP), Phase 1
- **Traces to:** FR-054 (AC-160–AC-162)

## Coverage notes

The 30 stories trace to 51 of the 54 functional requirements. FR-025 (IaC/configuration scanning), FR-048 (dashboard) and FR-049 (agent workflow visualization) are exercised by use cases in [Use cases and failure scenarios](02-use-cases-and-failure-scenarios.md) rather than dedicated stories in this version. Feature-level flows are in the [Functional requirements document](../02-prd-frd/02-functional-requirements-document.md).
