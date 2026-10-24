# UI Screen Inventory

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This inventory describes the 15 proposed screens (SCR-01 to SCR-15) of the Autonomous QA Swarm Web UI, a React single-page application served behind the API Gateway. For each screen it lists the purpose, primary personas, key elements, the states the screen must represent, primary actions (with required human approvals), and related functional requirements and API endpoints. Static concept mockups exist for every screen and are delivered separately as PNG images outside this Markdown set. The mockups use the **sample** Northwind Fintech dataset (for example job QJ-1042 and finding FND-0193), which is illustrative only.

## Cross-Cutting UI Conventions

- **State names:** States are shown in Title Case (for example "Awaiting Approval", "Completed With Warnings") and map one-to-one to the lower_snake_case API states.
- **Status labels:** Any capability not yet available in a deployment is labelled with its phase (for example "Future — Phase 4") rather than hidden.
- **Approval actions:** Buttons that trigger an HA-xx approval are visible only to roles allowed to perform them. They require a confirmation step, and where the approval demands it, a reason field. Every approval is audited.
- **Evidence access:** Downloads use signed, short-lived URLs (SEC-019). Logs and evidence are shown redacted (SEC-008).
- **Live updates:** Screens showing running jobs subscribe to `GET /jobs/{job_id}/events`. The target is delivery within 2 s of a state change (NFR-003).
- **Accessibility and locale:** Screens target WCAG 2.2 AA (NFR-012). Times are stored in UTC and shown in the user's time zone (NFR-020).
- **Honesty cues:** Inconclusive, skipped and blocked work is always shown with counts. It is never folded into "passed".

## Screen Summary

| ID | Screen | Primary personas | Approvals triggered | Key endpoints |
|---|---|---|---|---|
| SCR-01 | Dashboard — QA Health Overview | PER-03, Engineering Manager, PER-01 | None | GET /jobs, GET /jobs/{job_id}/quality-gates |
| SCR-02 | Repositories & Projects | PER-02, PER-03 | HA-11 | POST /repositories, POST /projects |
| SCR-03 | New QA Job Wizard | PER-02, PER-01, PER-06 | Lists HA-02, HA-03, HA-05 | POST /jobs |
| SCR-04 | Live Job Execution | PER-04, PER-02, PER-01 | None | GET /jobs/{job_id}/events, POST /jobs/{job_id}/cancel |
| SCR-05 | Agent Collaboration Graph | PER-02, PER-03 | HA-05 | GET /jobs/{job_id}/plan |
| SCR-06 | Functional Test Results | PER-01, PER-02 | Quarantine acknowledgement | GET /jobs/{job_id}/test-executions |
| SCR-07 | API Test Results | PER-02, PER-05 | None | GET /jobs/{job_id}/test-executions |
| SCR-08 | Security Testing Center | PER-05 | HA-02, HA-07 | GET /jobs/{job_id}/findings |
| SCR-09 | Performance Testing Lab | PER-06, PER-03 | HA-03, HA-05 | GET /jobs/{job_id}/performance-runs |
| SCR-10 | Mutation Testing Dashboard | PER-02 | None | GET /jobs/{job_id}/mutation-runs |
| SCR-11 | Defect Evidence & Investigation | PER-04, PER-05, PER-01 | HA-07, HA-08 | GET /findings/{finding_id} |
| SCR-12 | Patch Review | PER-04, PER-03 | HA-06 | POST /patches/{patch_id}/review |
| SCR-13 | Independent Verification | PER-04, PER-03 | None | GET /verifications/{verification_id} |
| SCR-14 | Reports & Release Readiness | PER-03, Engineering Manager | HA-08, HA-09, HA-10 | GET /jobs/{job_id}/report |
| SCR-15 | Settings & Integrations | Org Admin, PER-03 | HA-01, HA-04, HA-11 | POST /targets |

## Screen Descriptions

### SCR-01 Dashboard — QA Health Overview

- **Purpose:** Give a one-page view of quality across projects, as the landing screen after login.
- **Primary personas:** PER-03 Aisha, Engineering Manager, PER-01 Priya.
- **Key elements:** The release-readiness verdict of the latest job per project, open findings by severity and confidence, recent jobs with state, gate status, agent pool utilization and the Flaky Test Register count.
- **States:** An empty state for a new organization, with a prompt to add a repository. Jobs shown as running, failed or completed. Verdict tiles show "Pending" while gates are not yet evaluated.
- **Primary actions:** Open a job, finding or report, and filter by project. No approvals.
- **Related FRs and endpoints:** FR-048, FR-047. GET /jobs, GET /jobs/{job_id}/quality-gates, GET /jobs/{job_id}/findings.

### SCR-02 Repositories & Projects

- **Purpose:** Manage projects and the repositories registered to them.
- **Primary personas:** PER-02 Marco, PER-03 Aisha, Org Admin.
- **Key elements:** A project list, and repositories with provider, default branch, last pinned SHA, validation status and masked credential reference. The add-repository dialog shows inline validation errors (for example, non-HTTPS URL or private address rejected). Unsupported languages are flagged, such as the sample `northwind/ledger-service` marked "Unsupported language (Phase 4)".
- **States:** No projects yet (empty). Validating. Valid. Validation failed (with reason). Credential missing or revoked.
- **Primary actions:** Create a project, add a repository, re-validate, and attach a credential reference (HA-11, Org Admin only).
- **Related FRs and endpoints:** FR-001, FR-002, FR-003. POST /projects, GET /projects, POST /repositories, GET /repositories/{repository_id}, POST /repositories/{repository_id}/validate.

### SCR-03 New QA Job Wizard

- **Purpose:** Configure and launch a QA job with explicit scope, profiles, targets and limits.
- **Primary personas:** PER-02 Marco, PER-01 Priya, PER-06 Kenji.
- **Key elements:** Five steps. 1 Source: repository and ref, resolved to a SHA. 2 Scope: paths, test types. 3 Profiles: functional, security Quick/Standard/Deep, performance Smoke/Baseline. 4 Targets & Limits: authorized targets, resource budget, timeouts. 5 Review: policy summary, approvals needed, estimated duration and budget.
- **States:** Draft. Validation errors per step. Policy-refused, explaining why the job would be `blocked` (for example, an unauthorized target). Duplicate detected (`409`), with a link to the active job. Future profiles (Stress, Soak, Spike, external DAST) are shown disabled and labelled Future.
- **Primary actions:** Launch the job. The Review step states which approvals (HA-02, HA-03, HA-05) will be requested before the relevant stages run. A QA Lead can choose "force new" on a duplicate.
- **Related FRs and endpoints:** FR-005, FR-006, FR-007, FR-009, FR-050. POST /jobs, GET /repositories/{repository_id}.

### SCR-04 Live Job Execution

- **Purpose:** Follow a running job stage by stage and task by task.
- **Primary personas:** PER-04 Daniel, PER-02 Marco, PER-01 Priya.
- **Key elements:** A 13-stage timeline from Intake & Pinning to Cleanup & Retention. A task table with states, attempts and retries. A redacted live log tail. Resource usage. Infrastructure errors highlighted. A cancel button.
- **States:** Queued. Planning. Awaiting Approval. Running. Analyzing (for example, the sample QJ-1042 at "Evidence Correlation & Triage"). Cancelling. Terminal states: Completed, Completed With Warnings, Failed, Cancelled, Timed Out, Blocked.
- **Primary actions:** Cancel the job (confirmation required; workers are destroyed). Open task detail or results. No HA approval is needed to cancel your own job.
- **Related FRs and endpoints:** FR-010, FR-011, FR-012. GET /jobs/{job_id}, GET /jobs/{job_id}/events, GET /jobs/{job_id}/tasks, POST /jobs/{job_id}/cancel.

### SCR-05 Agent Collaboration Graph

- **Purpose:** Show how agents and tasks relate in the job plan, and what each agent received, proposed and produced.
- **Primary personas:** PER-02 Marco, PER-03 Aisha.
- **Key elements:** A DAG of agents and tasks with state colors. A selected-agent panel showing inputs, outputs, permissions and evidence references. A message and handoff log, including Policy Engine decisions and `invalid_output` events.
- **States:** Plan pending. Plan awaiting approval. Running, with live state colors. Completed. Tasks in failed, retry-scheduled or skipped states shown distinctly.
- **Primary actions:** Approve or reject the plan when the gate is enabled (HA-05, QA Lead). Inspect agent outputs.
- **Related FRs and endpoints:** FR-008, FR-009, FR-049. GET /jobs/{job_id}/plan, POST /jobs/{job_id}/plan/approval, GET /jobs/{job_id}/tasks.

### SCR-06 Functional Test Results

- **Purpose:** Present functional test outcomes and failure detail.
- **Primary personas:** PER-01 Priya, PER-02 Marco.
- **Key elements:** Counts by status. For the sample QJ-1042: 1,286 executed, 1,241 passed, 19 failed, 14 skipped, 3 blocked, 2 timed out and 7 infrastructure error, with 4 flaky. A test table with type, provenance (existing or generated), duration and status. Flaky badges. Failure detail with an assertion diff.
- **States:** No results yet. Running (partial). Completed. Results incomplete due to infrastructure errors.
- **Primary actions:** Open the linked finding, review generated tests for promotion, and request quarantine of a flaky test (QA Lead acknowledgement required).
- **Related FRs and endpoints:** FR-015, FR-016, FR-017, FR-018. GET /jobs/{job_id}/test-executions.

### SCR-07 API Test Results

- **Purpose:** Show API contract and authorization test outcomes with request and response evidence.
- **Primary personas:** PER-02 Marco, PER-05 Sofia.
- **Key elements:** An endpoint coverage matrix, schema violations, authentication and authorization checks, negative and boundary cases, and request/response evidence with redaction.
- **States:** Not applicable (no OpenAPI spec, with reason). Target blocked or unhealthy. Running. Completed.
- **Primary actions:** Open a finding (for example, the sample FND-0193 IDOR) and download evidence. No approvals.
- **Related FRs and endpoints:** FR-019, FR-020, FR-021. GET /jobs/{job_id}/test-executions, GET /jobs/{job_id}/findings.

### SCR-08 Security Testing Center

- **Purpose:** Present security scans and findings for triage.
- **Primary personas:** PER-05 Sofia.
- **Key elements:** The profile used. Scans listed with tool and version. A findings grid by severity × source class (Scanner alert, Probable vulnerability, Confirmed vulnerability, False positive). Scope and exclusions. Active suppressions with expiry. A coverage-limitations notice stating that no profile is comprehensive.
- **States:** No scans configured. Scans running. DAST awaiting approval. A scanner failure, shown as incomplete coverage. Completed.
- **Primary actions:** Approve DAST (HA-02, Security Reviewer), mark a false positive or suppress a rule (HA-07, reason mandatory), and request a reproduction run.
- **Related FRs and endpoints:** FR-022, FR-023, FR-024, FR-025, FR-026, FR-037. GET /jobs/{job_id}/findings, POST /findings/{finding_id}/triage.

### SCR-09 Performance Testing Lab

- **Purpose:** Configure bounded performance runs and analyze results against thresholds and baseline.
- **Primary personas:** PER-06 Kenji, PER-03 Aisha.
- **Key elements:** Workload configuration (profile, VUs, ramp, duration, thresholds). A safety summary with caps, abort rules and required approvals. Results: p50/p90/p95/p99, RPS and errors. Baseline vs. candidate comparison, for example the sample FND-0199 with p95 412 ms vs. 261 ms. Sample-size warnings.
- **States:** No baseline. Awaiting approval. Running. Aborted (with the triggering rule). Invalid (generator-bound). Completed.
- **Primary actions:** Submit a run, and approve profiles above Smoke or runs against external targets (HA-03, QA Lead). Stress, Spike and Soak also need HA-05 and are labelled Future.
- **Related FRs and endpoints:** FR-027, FR-028, FR-029. GET /jobs/{job_id}/performance-runs.

### SCR-10 Mutation Testing Dashboard

- **Purpose:** Show test-suite strength on changed modules.
- **Primary personas:** PER-02 Marco.
- **Key elements:** Score on changed modules (sample: 74.7%, 139/186). Killed, survived, invalid and timeout counts, with exclusions explained. A survived-mutants list with suggested assertions. Equivalent-mutant flags. QG-06 shown as advisory.
- **States:** Not run (no changed modules or profile disabled). Running. Inconclusive (baseline suite failing). Completed. Sampled (more than 500 candidate mutants).
- **Primary actions:** Review suggested tests (promotion requires human review) and mark suspected equivalent mutants. No HA approvals.
- **Related FRs and endpoints:** FR-030, FR-031. GET /jobs/{job_id}/mutation-runs.

### SCR-11 Defect Evidence & Investigation

- **Purpose:** Investigate a single finding and record triage decisions.
- **Primary personas:** PER-04 Daniel, PER-05 Sofia, PER-01 Priya.
- **Key elements:** A finding header (ID, severity, confidence, DCS breakdown by its five components). Reproduction steps. An evidence timeline. Logs, screenshots and requests. Deduplication links. The decision trail. A Disputed badge when agents disagree. Triage actions.
- **States:** Candidate. Triaging. Reproducing. Confirmed. Not Reproducible. False Positive. Duplicate. Accepted Risk. Fix Proposed. Fix Verified. Fix Failed. Reopened.
- **Primary actions:** Mark false positive (HA-07), accept risk with expiry (HA-08; security findings also need a Security Reviewer), confirm a suggested duplicate, and request reproduction.
- **Related FRs and endpoints:** FR-032 to FR-037. GET /findings/{finding_id}, GET /findings/{finding_id}/evidence, POST /findings/{finding_id}/triage.

### SCR-12 Patch Review

- **Purpose:** Review a proposed patch and decide whether it proceeds to verification.
- **Primary personas:** PER-04 Daniel, PER-03 Aisha.
- **Key elements:** A patch summary (sample PCH-0007: +14/−3 lines, 2 files including a new test). A diff viewer. Rationale. Linked evidence. Risk notes. A prominent "no auto-commit" notice.
- **States:** Proposed. Awaiting review. Approved for verification. Rejected. Verification running, Verified and Verification failed are shown as read-only links to SCR-13.
- **Primary actions:** Approve for verification or reject with a reason (HA-06, code owner or QA Lead). Exporting as a pull request is shown disabled and labelled Future (HA-12).
- **Related FRs and endpoints:** FR-038, FR-039, FR-041. GET /jobs/{job_id}/patches, POST /patches/{patch_id}/review.

### SCR-13 Independent Verification

- **Purpose:** Show the fresh-sandbox verification result of an approved patch.
- **Primary personas:** PER-04 Daniel, PER-03 Aisha.
- **Key elements:** An original vs. patched comparison of functional, API, security and performance re-checks. Fresh-sandbox metadata (worker image digest, commit, tool versions). Checks not re-run, with justification and stated limitations (sample VER-0011: performance not re-run).
- **States:** Not started. Verification running. Verified. Verification failed (with new or persisting failures).
- **Primary actions:** Start verification (after HA-06) and open the addendum report. No further approvals.
- **Related FRs and endpoints:** FR-040. POST /patches/{patch_id}/verifications, GET /verifications/{verification_id}.

### SCR-14 Reports & Release Readiness

- **Purpose:** Present gate results, residual risk and the release recommendation, and capture the human decision.
- **Primary personas:** PER-03 Aisha, Engineering Manager, PER-05 Sofia.
- **Key elements:** QG-01 to QG-08 with results. The verdict (READY, READY_WITH_RISKS, NOT_READY, INCONCLUSIVE). Residual risks. Accepted risks with expiry. Coverage. Export buttons (JSON, HTML, PDF, SARIF, JUnit). The human release-decision panel.
- **States:** Pending (job in progress, as for sample QJ-1042). Evaluated. Overridden gate, marked with reason. Decision recorded. Partial report, for failed or cancelled jobs.
- **Primary actions:** Accept risk (HA-08), override a failed gate (HA-09, reason mandatory) and record the release decision (HA-10), all restricted to QA Lead. Export reports.
- **Related FRs and endpoints:** FR-042, FR-043, FR-044, FR-045, FR-046. GET /jobs/{job_id}/quality-gates, GET /jobs/{job_id}/report, POST /jobs/{job_id}/release-decision.

### SCR-15 Settings & Integrations

- **Purpose:** Administer the platform's safety limits, permissions, integrations and model access.
- **Primary personas:** Org Admin, PER-03 Aisha.
- **Key elements:** Execution limits (defaults 2 vCPU, 4 GiB RAM, 30 min per task). Network policy and dependency-fetch allow-list. An agent permissions matrix. Integrations (GitHub, GitLab, Jenkins, GitHub Actions, Slack/Teams). Model Gateway (hosted or local providers, token budgets). Target registration. Retention (default 90 days evidence, 1 year audit). Audit-trail access.
- **States:** Default configuration. Pending changes awaiting approval. Integration connected, failing or disconnected. Model provider unavailable.
- **Primary actions:** Register a target and attest authorization (HA-01), add allow-list entries (HA-04), and register or rotate credentials (HA-11). Platform invariants such as network-off execution cannot be disabled here.
- **Related FRs and endpoints:** FR-050, FR-051, FR-052, FR-053, FR-054. POST /targets, POST /targets/{target_id}/authorizations, GET /audit-events.
