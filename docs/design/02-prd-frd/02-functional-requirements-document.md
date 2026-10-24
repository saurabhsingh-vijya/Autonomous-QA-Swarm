# Functional Requirements Document

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This Functional Requirements Document (FRD) specifies the proposed behavior of Autonomous QA Swarm feature by feature (F-01 to F-15). For each feature it gives the purpose, actors, workflow, expected outcome, business rules, edge cases and traceability to requirements, acceptance criteria, screens and API endpoints. The authoritative text of each FR and its acceptance criteria is in [functional requirements](../03-requirements/01-functional-requirements.md). This document explains how those requirements fit together. Product scope and phasing are in the [product requirements document](01-product-requirements-document.md).

## Conventions

### Identifier Scheme

| Family | Format | Owner document |
|---|---|---|
| Feature | `F-01` to `F-15` | This document |
| Functional requirement | `FR-001` to `FR-054` | 03-requirements/01 |
| Acceptance criterion | `AC-001` to `AC-162` | 03-requirements/01 |
| Screen | `SCR-01` to `SCR-15` | 02-prd-frd/03 |
| Human approval | `HA-01` to `HA-12` | Agent design, used throughout |
| Quality gate | `QG-01` to `QG-08` | 11-quality-gates-and-reporting/02 |

API paths are relative to the base `/api/v1`.

### Priority Definitions

- **P0:** Required for the phase in which the requirement is scheduled. The phase cannot exit without it.
- **P1:** Expected in its phase. It may slip one phase only with a recorded decision.
- **P2:** Desirable. It may move to a later phase without affecting MVP viability.

### Status Labels

- **Proposed:** Design intent, not yet validated. This applies to every item in this document.
- **Planned (MVP):** Intended for Phases 1–3.
- **Future:** Phase 4 or later.
- **Implemented / Verified:** No item has this status. It will be applied only after code exists and the item's acceptance criteria pass.

### Acceptance-Criteria Numbering Rule

Every FR has exactly three acceptance criteria. FR-n owns AC-(3n−2), AC-(3n−1) and AC-3n, zero-padded to three digits. For example, FR-001 owns AC-001 to AC-003, FR-015 owns AC-043 to AC-045, and FR-054 owns AC-160 to AC-162. The AC ranges below are derived from this rule.

### Common Rules for All Features

- Agents emit typed proposals only. The Policy Engine validates them deny-by-default, and the Execution Service runs them in sandbox workers.
- All agent and worker outputs are schema-validated (SEC-015). Invalid LLM output receives at most one corrective retry and then becomes `invalid_output`.
- Every state change, approval and override produces an audit event (FR-054).
- Asynchronous operations return `202` with the resource location. Errors use problem+json (RFC 9457).

## Feature Specifications

### F-01 Repository & Source Intake

**Purpose:** Register repositories safely and produce an immutable, checksummed source snapshot for every job. **Status:** Planned (MVP), Phases 1–2.

**Actors:** QA Engineer, QA Lead, Org Admin (credentials, HA-11), Source Intake Service, Secrets Broker.

**Workflow:**

1. The user submits an HTTPS repository URL on SCR-02.
2. The Source Intake Service validates the URL against the allow-list. It accepts HTTPS only, pins DNS and rejects private addresses (SEC-002).
3. For private repositories, the service obtains a short-lived read-only token from the Secrets Broker through a credential reference.
4. At job time, the ref (branch, tag or PR) is resolved to an immutable commit SHA.
5. A read-only tarball snapshot is created with its SHA-256 checksum. No repository code runs on the control plane.

**Expected outcome:** A Repository record with validation status, and a SourceSnapshot linked to the job's pinned SHA.

**Business rules:** Raw tokens are never stored or displayed. Only masked credential references are shown. A snapshot is immutable once created.

**Edge cases:** A force-pushed branch between resolution and fetch is detected by SHA mismatch, and the job fails validation. URLs that redirect to private IPs are rejected. A repository in an unsupported language (for example, sample `northwind/ledger-service`, Java) can be registered but is flagged "Unsupported language (Phase 4)".

| Trace | Values |
|---|---|
| FRs | FR-001, FR-002, FR-003, FR-004 |
| ACs | AC-001 to AC-012 |
| Screens | SCR-02, SCR-03 |
| Endpoints | POST /repositories, GET /repositories/{repository_id}, POST /repositories/{repository_id}/validate |

### F-02 QA Job Configuration & Launch

**Purpose:** Let users and CI create QA jobs with explicit profiles, scope, limits and authorized targets, without duplicate work. **Status:** Planned (MVP), Phases 1–2.

**Actors:** QA Engineer, QA Lead, CI Service Account, Org Admin or Security Reviewer (HA-01), Policy Engine.

**Workflow:**

1. The user completes SCR-03 steps: Source, Scope, Profiles, Targets & Limits, Review.
2. Targets are registered and their authorization is attested (HA-01) before they can be selected.
3. The Policy Engine evaluates the request. The Review step lists required approvals (HA-02, HA-03, HA-05) and estimated duration and budget.
4. `POST /jobs` with an `Idempotency-Key` creates the job in state `created`, which then moves to `validating`.

**Expected outcome:** A Job in `queued`, or in `blocked` if the policy refuses it.

**Business rules:** The same key within 24 h returns the original response. An active job with the same (repository, commit SHA, profile hash) returns `409` with a link, unless `force_new=true` is set by a QA Lead. Scope may restrict paths, test types, resource budget and timeouts, within the platform maxima.

**Edge cases:** An unauthorized or revoked target puts the job in `blocked` with no execution (sample QJ-1037). A missing `Idempotency-Key` returns `400`. A budget above platform maxima returns `422`.

| Trace | Values |
|---|---|
| FRs | FR-005, FR-006, FR-007, FR-050 |
| ACs | AC-013 to AC-021, AC-148 to AC-150 |
| Screens | SCR-03, SCR-02, SCR-15 |
| Endpoints | POST /jobs, POST /targets, POST /targets/{target_id}/authorizations, POST /projects, GET /projects |

### F-03 Planning & Orchestration

**Purpose:** Turn a job into a validated task DAG and run it reliably with leases, retries, timeouts and cancellation. **Status:** Planned (MVP), Phases 1–2.

**Actors:** Orchestrator Agent (AG-01), Workflow Engine, QA Lead (HA-05), all task-executing agents.

**Workflow:**

1. AG-01 proposes a plan. The Workflow Engine validates it as an acyclic DAG against task contracts.
2. If the plan approval gate is enabled (default on for Deep security and Stress/Soak performance), the job waits in `awaiting_approval` for HA-05. The same state holds the job when the selected profiles need HA-02 or HA-03 and those approvals are not yet recorded.
3. Tasks are leased (TTL 90 s, heartbeat every 30 s) and run. Progress streams via SSE.
4. Cancellation moves the job to `cancelling` and then `cancelled` after all workers are destroyed.

**Expected outcome:** The job reaches a terminal state with every task in a terminal state.

**Business rules:** Infrastructure errors get at most 2 retries (backoff 30 s and 120 s, jitter ±20%). Invalid LLM output gets at most 1 corrective retry. Deterministic test failures are results, never retried as errors. The task idempotency key is SHA-256(job_id, stage, task_type, canonical input hash). The job limit defaults to 4 h (max 12 h).

**Edge cases:** An expired lease leads to `failed_retryable`. A plan rejected under HA-05 ends the job as `cancelled`, with the reason audited. Exceeding the wall-clock limit leads to `timed_out`. Partial task failure leads to `completed_with_warnings`.

| Trace | Values |
|---|---|
| FRs | FR-008, FR-009, FR-010, FR-011, FR-012 |
| ACs | AC-022 to AC-036 |
| Screens | SCR-04, SCR-05, SCR-03 |
| Endpoints | GET /jobs/{job_id}/plan, POST /jobs/{job_id}/plan/approval, GET /jobs/{job_id}/events, POST /jobs/{job_id}/cancel, GET /jobs/{job_id}/tasks, GET /jobs/{job_id} |

### F-04 Requirements & Change Analysis

**Purpose:** Derive testable scenarios from requirements and specs, and focus testing on what the change affects. **Status:** Planned (MVP), Phase 2.

**Actors:** Requirements Analysis Agent (AG-02), QA Engineer.

**Workflow:**

1. AG-02 reads requirements, user stories, OpenAPI specs and the diff as untrusted data (SEC-014).
2. It proposes TestScenario records with priority (P0/P1) and acceptance criteria, plus an affected-modules list.
3. Outputs are schema-validated, and AG-01 uses them for planning.

**Expected outcome:** Prioritized scenarios linked to requirements, and an impact map used for test selection.

**Business rules:** Scenarios are proposals. Their execution coverage is measured by QG-04. Impact analysis narrows priority but does not silently drop P0 scenarios.

**Edge cases:** When no requirements or spec are supplied, scenarios are derived from the existing tests and the diff only, and the report notes the limitation. Diffs too large for the token budget are analyzed at module level. Instructions embedded in repository text are ignored.

| Trace | Values |
|---|---|
| FRs | FR-013, FR-014 |
| ACs | AC-037 to AC-042 |
| Screens | SCR-05, SCR-14 |
| Endpoints | GET /jobs/{job_id}/plan, GET /jobs/{job_id}/tasks |

### F-05 Functional Testing

**Purpose:** Run existing and approved generated tests in sandboxes, record results precisely, and separate flaky behavior from defects. **Status:** Planned (MVP), Phases 1–2.

**Actors:** Functional Testing Agent (AG-03), Execution Service, QA Engineer, QA Lead.

**Workflow:**

1. The Baseline Run executes the existing suites (pytest, Jest/Vitest, Playwright) on the pinned commit, with network off.
2. AG-03 may propose candidate tests with provenance. They require human review before promotion.
3. Each TestExecution records status (`passed`, `failed`, `skipped`, `blocked`, `timed_out`, `infrastructure_error`), duration, tool version and evidence.
4. Failed tests are re-run up to 2 times in fresh workers.

**Expected outcome:** A complete result set, with flaky tests classified and recorded in the Flaky Test Register.

**Business rules:** A pass on rerun is classified `flaky`, not a defect. Quarantine requires 3 flaky occurrences in 14 days and QA Lead acknowledgement, and only then is the test excluded from the QG-03 denominator.

**Edge cases:** Build failure in Environment Preparation leads to `blocked` tests and an INCONCLUSIVE coverage gate. An image pull failure is an `infrastructure_error` (sample QJ-1039). A test exceeding the per-task wall clock is `timed_out`.

| Trace | Values |
|---|---|
| FRs | FR-015, FR-016, FR-017, FR-018 |
| ACs | AC-043 to AC-054 |
| Screens | SCR-06, SCR-04 |
| Endpoints | GET /jobs/{job_id}/test-executions, GET /jobs/{job_id}/tasks |

### F-06 API Testing

**Purpose:** Check API behavior against its contract, including negative, boundary, authentication and object-level authorization cases. **Status:** Planned (MVP), Phase 2.

**Actors:** API Testing Agent (AG-04), Target Environment Manager, Security Reviewer.

**Workflow:**

1. The Target Environment Manager starts an ephemeral in-sandbox target, or binds an authorized external non-production target.
2. AG-04 derives conformance, negative and property-based cases from the OpenAPI spec (Schemathesis).
3. Authorization checks use scoped, short-lived test-user credentials injected only for authorized targets.
4. Request and response pairs are captured as evidence.

**Expected outcome:** An endpoint coverage matrix, schema violations and authorization results that feed findings.

**Business rules:** No checks run against unauthorized targets (SEC-016). Checks prove reachability only and are non-destructive (SEC-018).

**Edge cases:** A missing or invalid OpenAPI spec means the tasks are `skipped` with the reason reported. A target health failure makes tasks `blocked`. Rate limiting by the target is recorded, not treated as a defect.

| Trace | Values |
|---|---|
| FRs | FR-019, FR-020, FR-021 |
| ACs | AC-055 to AC-063 |
| Screens | SCR-07, SCR-11 |
| Endpoints | GET /jobs/{job_id}/test-executions, GET /jobs/{job_id}/findings |

### F-07 Security Testing

**Purpose:** Run bounded, authorized security checks and triage their output into evidence-backed findings. **Status:** Planned (MVP) for FR-022 to FR-025; Future for FR-026.

**Actors:** Security Testing Agent (AG-05), Security Reviewer (HA-02, HA-07), QA Lead (HA-05).

**Workflow:**

1. The selected profile determines the scans. Quick: Semgrep CE, Bandit, Gitleaks, OSV-Scanner. Standard: adds Trivy, Checkov and API authorization checks. Deep: adds OWASP ZAP.
2. Scanners run in sandboxes, and each scan records its tool and version.
3. Every alert starts as `candidate` and "Scanner alert". AG-05 proposes reachability or precondition checks.
4. Secrets found are redacted in all outputs (SEC-008).

**Expected outcome:** Findings by severity × source class, with explicit coverage limitations.

**Business rules:** Deep requires HA-02 and HA-05 and is bounded to 60 min. False-positive marking requires a reviewer and a reason (HA-07). Suppressions are scoped and expire after 90 days by default. No profile claims comprehensive coverage.

**Edge cases:** A scanner crash produces `infrastructure_error`, and coverage is reported as incomplete. A secret in a test fixture (sample FND-0198) is triaged as false positive. An unreachable vulnerable dependency stays Probable (sample FND-0194).

| Trace | Values |
|---|---|
| FRs | FR-022, FR-023, FR-024, FR-025, FR-026 |
| ACs | AC-064 to AC-078 |
| Screens | SCR-08, SCR-11 |
| Endpoints | GET /jobs/{job_id}/findings, POST /findings/{finding_id}/triage |

### F-08 Performance Testing

**Purpose:** Detect latency and error-rate regressions early with bounded, comparable workloads. **Status:** Planned (MVP) for FR-027 and FR-029; Future for FR-028.

**Actors:** Performance Testing Agent (AG-06), Performance Test Engineer, QA Lead (HA-03, HA-05).

**Workflow:**

1. The user configures the profile, thresholds and endpoints on SCR-09.
2. Approvals are collected: none for Smoke on an ephemeral target, HA-03 for Baseline and above.
3. k6 (default) runs inside the sandbox, with abort rules active throughout.
4. Metrics (p50/p90/p95/p99, RPS, errors) are compared with the stored baseline.

**Expected outcome:** PerformanceRun records and, on breach, a finding with evidence.

**Business rules:** Caps are Smoke 5 VUs for 1 min and Baseline 20 VUs for 5 min. A run aborts on error rate > 20% for 60 s, 3 consecutive health-check failures, or p95 > 5× baseline for 2 min. Generator CPU > 90% marks the run invalid. Sample-size warnings apply below 400 samples for p95 and below 2,000 for p99.

**Edge cases:** With no baseline, the run becomes the candidate baseline and the regression check is inconclusive. An invalid generator-bound run produces no finding.

| Trace | Values |
|---|---|
| FRs | FR-027, FR-028, FR-029 |
| ACs | AC-079 to AC-087 |
| Screens | SCR-09, SCR-14 |
| Endpoints | GET /jobs/{job_id}/performance-runs |

### F-09 Mutation Testing

**Purpose:** Measure how well tests detect injected faults in changed code, and suggest improvements. **Status:** Planned (MVP), Phase 3.

**Actors:** Mutation Testing Agent (AG-07), Automation QA Engineer.

**Workflow:**

1. Mutants are generated for changed modules only (mutmut or Stryker), up to 500 per job.
2. Each mutant runs with a timeout of 2 × baseline test time + 10 s.
3. Results are classified as killed, survived, timed out or invalid.
4. AG-07 explains surviving mutants and proposes assertions for review.

**Expected outcome:** A mutation score and a list of surviving mutants with suggestions.

**Business rules:** Score = killed / (killed + survived) × 100. Invalid, timed-out and unexecuted mutants are excluded and reported. Suspected equivalent mutants are flagged. QG-06 (≥ 60%) is advisory. Mutants never leave the sandbox.

**Edge cases:** More than 500 candidate mutants are sampled, and the sampling is reported. A baseline suite that fails prevents scoring, and the result is reported as inconclusive. In the sample, 139 killed of 186 valid gives 74.7%.

| Trace | Values |
|---|---|
| FRs | FR-030, FR-031 |
| ACs | AC-088 to AC-093 |
| Screens | SCR-10 |
| Endpoints | GET /jobs/{job_id}/mutation-runs |

### F-10 Evidence & Defect Analysis

**Purpose:** Correlate raw signals into deduplicated, scored, reproducible findings. **Status:** Planned (MVP), Phases 1–2.

**Actors:** Evidence and Defect Analysis Agent (AG-08), QA Lead, Security Reviewer.

**Workflow:**

1. Every result's evidence is stored content-addressed (SHA-256) in the Evidence Store.
2. Signals are normalized, fingerprinted and matched. Exact matches become `duplicate`. Near matches (similarity ≥ 0.9) are suggested.
3. Reproduction runs execute in fresh sandboxes. The DCS is computed from reproducibility (35), oracle (25), completeness (15), corroboration (15) and stability (10).
4. Conflicts follow the precedence order. Unresolved conflicts are flagged **Disputed** and routed to humans.
5. Humans triage via SCR-11 (HA-07, HA-08).

**Expected outcome:** Findings with confidence level, Risk Priority and a full decision trail.

**Business rules:** Confirmed requires DCS ≥ 80 and reproduction. LLM opinion can never lift a finding to Confirmed. Disputed findings are never auto-confirmed or auto-dismissed.

**Edge cases:** Reproduction blocked by infrastructure leaves the finding Probable or Candidate. A previously false-positive finding that reappears outside its suppression scope is `reopened`.

| Trace | Values |
|---|---|
| FRs | FR-032, FR-033, FR-034, FR-035, FR-036, FR-037 |
| ACs | AC-094 to AC-111 |
| Screens | SCR-11, SCR-06, SCR-08 |
| Endpoints | GET /jobs/{job_id}/findings, GET /findings/{finding_id}, GET /findings/{finding_id}/evidence, POST /findings/{finding_id}/triage |

### F-11 Patch Proposal & Independent Verification

**Purpose:** Offer minimal fixes for human review, and verify approved fixes independently. **Status:** Planned (MVP), Phases 1–3.

**Actors:** Patch Proposal Agent (AG-09), Independent Verification Agent (AG-10), Developer (code owner) or QA Lead (HA-06).

**Workflow:**

1. AG-09 proposes a diff for a Confirmed finding, with rationale and evidence links. The status moves `proposed` → `awaiting_review`.
2. The reviewer approves (`approved_for_verification`) or rejects (`rejected`) on SCR-12 (HA-06).
3. AG-10 re-runs relevant checks on the pinned commit plus the patch, in a fresh sandbox, without AG-09's reasoning.
4. The status becomes `verified` or `verification_failed`, and an addendum report is produced.

**Expected outcome:** Verified patches that are eligible for QG-07, with stated limitations.

**Business rules:** No automatic commit, push or merge (FR-041). Patches are proposed only for Confirmed findings. Verification must state any check not re-run and why.

**Edge cases:** A patch that fails to apply to the snapshot leads to `verification_failed`. A patch that introduces a new failure fails verification and creates a new finding.

| Trace | Values |
|---|---|
| FRs | FR-038, FR-039, FR-040, FR-041 |
| ACs | AC-112 to AC-123 |
| Screens | SCR-12, SCR-13 |
| Endpoints | GET /jobs/{job_id}/patches, POST /patches/{patch_id}/review, POST /patches/{patch_id}/verifications, GET /verifications/{verification_id} |

### F-12 Quality Gates & Release Readiness

**Purpose:** Evaluate gates deterministically and support a recorded human release decision. **Status:** Planned (MVP), Phase 2.

**Actors:** QA Report Agent (AG-11), QA Lead (HA-08, HA-09, HA-10).

**Workflow:**

1. QG-01 to QG-08 are evaluated as `passed`, `failed`, `advisory_failed`, `inconclusive` or `not_applicable` (shown as `pending` until evaluated), together with the coverage and residual-risk summary.
2. The verdict is computed: a blocking failure gives NOT_READY, then any inconclusive gate gives INCONCLUSIVE, then an advisory failure or accepted risk gives READY_WITH_RISKS, else READY.
3. A human may accept risk (HA-08), override a gate (HA-09, reason mandatory) and record the decision (HA-10).

**Expected outcome:** QualityGateResult records, a verdict and a separate human decision.

**Business rules:** Aggregate scores never hide blockers. An open Confirmed Critical, or an open Confirmed High security finding without accepted risk, forces NOT_READY. Thresholds are configurable per project.

**Edge cases:** For a job still in progress, gates show "Pending" (sample QJ-1042, in state `analyzing`). When QG-05 has no performance run, the gate is not applicable rather than passed.

| Trace | Values |
|---|---|
| FRs | FR-042, FR-043, FR-046 |
| ACs | AC-124 to AC-129, AC-136 to AC-138 |
| Screens | SCR-14, SCR-01 |
| Endpoints | GET /jobs/{job_id}/quality-gates, POST /jobs/{job_id}/release-decision |

### F-13 Reporting & History

**Purpose:** Produce evidence-backed reports and exports, and give users history, dashboards and workflow visibility. **Status:** Planned (MVP), Phases 1–2.

**Actors:** QA Report Agent (AG-11), all roles (read access per RBAC), CI Service Account.

**Workflow:**

1. AG-11 aggregates results deterministically and adds an LLM narrative, labelled as generated.
2. Reports are rendered as JSON, HTML or PDF. Exports are produced as SARIF and JUnit XML.
3. Job history supports search and filters. The dashboard and agent graph read the same data.

**Expected outcome:** Reports in which every finding links to evidence (NFR-009), generated within 30 s for jobs with ≤ 10,000 test executions (NFR-019).

**Business rules:** Narrative text cannot alter deterministic figures. Reports include skipped, blocked and inconclusive work.

**Edge cases:** For a failed or cancelled job, a partial report is marked incomplete. If the LLM is unavailable, the report is produced without narrative.

| Trace | Values |
|---|---|
| FRs | FR-044, FR-045, FR-047, FR-048, FR-049 |
| ACs | AC-130 to AC-135, AC-139 to AC-147 |
| Screens | SCR-14, SCR-01, SCR-05 |
| Endpoints | GET /jobs/{job_id}/report, GET /jobs, GET /jobs/{job_id} |

### F-14 Administration, Settings & Integrations

**Purpose:** Configure limits, network policy, agent permissions, integrations and model access. **Status:** Planned (MVP), Phases 1–3.

**Actors:** Org Admin (HA-04, HA-11), QA Lead.

**Workflow:**

1. On SCR-15, admins set execution limits within the platform maxima.
2. Outbound allow-list entries for the dependency-fetch phase require HA-04.
3. The agent permissions matrix defines which tools each agent may propose.
4. Integrations (GitHub, GitLab, Jenkins, GitHub Actions, Slack/Teams) and the Model Gateway (hosted or local) are configured, with credentials registered via HA-11.

**Expected outcome:** Versioned, audited configuration that the Policy Engine enforces.

**Business rules:** Settings cannot disable HA approvals or the network-off execution rule. The provider allow-list and redaction apply to all prompts (SEC-021).

**Edge cases:** A model provider outage blocks LLM tasks, while deterministic tasks continue. A rotated credential invalidates active tokens. A new job that needs a revoked credential ends `blocked` during validation; tasks of an already running job that depend on it end `skipped` with the reason recorded, and that job finishes `completed_with_warnings`.

| Trace | Values |
|---|---|
| FRs | FR-051, FR-052, FR-053 |
| ACs | AC-151 to AC-159 |
| Screens | SCR-15 |
| Endpoints | No dedicated settings endpoint in the v1 catalogue; credentials and targets use POST /repositories, POST /targets |

### F-15 Audit & Governance

**Purpose:** Keep a tamper-evident record of every action and decision. **Status:** Planned (MVP), Phase 1.

**Actors:** All roles. Auditors use Viewer or Org Admin access.

**Workflow:**

1. Each action emits an AuditEvent with actor, action, target, timestamp (UTC) and correlation ID.
2. Events are appended to a hash chain.
3. Users query by job, actor or action.

**Expected outcome:** A verifiable audit trail retained for 1 year by default (NFR-016).

**Business rules:** Events are append-only. Approvals record the approver role and reason where required (HA-08, HA-09).

**Edge cases:** A detected hash-chain break raises an integrity alert. A failure to write an audit event fails the action it records.

| Trace | Values |
|---|---|
| FRs | FR-054 |
| ACs | AC-160 to AC-162 |
| Screens | SCR-15, SCR-11, SCR-14 |
| Endpoints | GET /audit-events |
