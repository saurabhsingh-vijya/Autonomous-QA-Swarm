# Personas and User Journeys

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document defines the six primary personas (PER-01 to PER-06) and one secondary stakeholder for Autonomous QA Swarm. It then describes seven proposed user journeys (UJ-01 to UJ-07) as numbered steps that reference screens (SCR-xx), agents (AG-xx) and human approvals (HA-xx). The personas are illustrative archetypes for design and validation, not research findings. Journey examples use the **sample** Northwind Fintech dataset and are illustrative only.

## Persona Overview

| ID | Persona | Platform role (RBAC) | Primary concern | Key screens |
|---|---|---|---|---|
| PER-01 | Priya — Manual QA Engineer | QA Engineer | Less repetitive regression, clear failure evidence | SCR-01, SCR-04, SCR-06, SCR-11 |
| PER-02 | Marco — Automation QA Engineer | QA Engineer | Reliable suites, flaky control, stronger tests | SCR-03, SCR-06, SCR-07, SCR-10 |
| PER-03 | Aisha — QA Lead | QA Lead | Release readiness, gates, approvals | SCR-01, SCR-03, SCR-14, SCR-15 |
| PER-04 | Daniel — Developer | Developer | Fast PR feedback, reproducible defects, fix review | SCR-04, SCR-11, SCR-12, SCR-13 |
| PER-05 | Sofia — Application Security Engineer | Security Reviewer | Signal over noise, authorized and safe scanning | SCR-08, SCR-11, SCR-14 |
| PER-06 | Kenji — Performance Test Engineer | QA Engineer | Early, bounded, comparable performance data | SCR-09, SCR-14 |
| Secondary | Engineering Manager | Viewer | Trend visibility, delivery risk | SCR-01, SCR-14 |

Org Admin and CI Service Account are platform roles rather than personas. Org Admin duties such as HA-01, HA-04 and HA-11 may be held by Aisha, Sofia or a platform engineer, depending on the organization.

## Personas

### PER-01 — Priya, Manual QA Engineer

Priya runs regression checklists and exploratory sessions for the sample Payments Platform. She knows the business rules well but does not write automation code.

- **Goals:** Spend less release time re-executing known scenarios. Understand quickly which planned scenarios actually ran. Attach strong evidence when she raises defects.
- **Pain points:** Manual regression consumes most of release week. CI failures are opaque to her. Defects she raises bounce back as "cannot reproduce".
- **Key screens:** SCR-01 Dashboard — QA Health Overview, SCR-04 Live Job Execution, SCR-06 Functional Test Results, SCR-11 Defect Evidence & Investigation.
- **Permissions:** QA Engineer. She can create jobs, view results and propose triage changes on functional findings. She cannot approve false positives (HA-07, QA Lead) or override gates.

### PER-02 — Marco, Automation QA Engineer

Marco owns the pytest and Playwright suites and the CI pipeline configuration.

- **Goals:** Keep the suite trustworthy. Isolate flaky tests without hiding them. Find out whether tests actually assert behavior. Review AI-generated tests efficiently.
- **Pain points:** Flaky tests force pipeline re-runs. Coverage numbers look good while defects escape. Generated tests often assert current buggy behavior.
- **Key screens:** SCR-03 New QA Job Wizard, SCR-06 Functional Test Results, SCR-07 API Test Results, SCR-10 Mutation Testing Dashboard, SCR-05 Agent Collaboration Graph.
- **Permissions:** QA Engineer. He can create and configure jobs, review generated tests and view all results. He requests quarantine, which the QA Lead acknowledges.

### PER-03 — Aisha, QA Lead

Aisha is accountable for the quality signal that reaches release decisions.

- **Goals:** One evidence-backed view per release candidate. Gates that cannot be gamed. A clear record of who accepted which risk.
- **Pain points:** Release meetings spent reconciling tools. Waivers given verbally. Unclear residual risk.
- **Key screens:** SCR-01, SCR-03, SCR-14 Reports & Release Readiness, SCR-15 Settings & Integrations, SCR-11.
- **Permissions:** QA Lead. She holds HA-03 (performance above Smoke), HA-05 (plan approval), HA-06 (patch approval, shared with code owners), HA-07 (functional false positives), HA-08 (risk acceptance), HA-09 (gate override, reason mandatory) and HA-10 (release decision). She can use `force_new=true` on duplicate jobs.

### PER-04 — Daniel, Developer

Daniel works on `northwind/payments-api` (sample) and is the code owner for its routers.

- **Goals:** Get feedback on his pull request before review. Reproduce failures locally from evidence. Get useful fix suggestions without losing control of his code.
- **Pain points:** Slow pipelines, vague defect reports, and AI patches that touch too much.
- **Key screens:** SCR-04, SCR-11, SCR-12 Patch Review, SCR-13 Independent Verification.
- **Permissions:** Developer. He can view jobs and findings for his projects and approve or reject patches as code owner (HA-06). In the Future, he will be able to export verified patches as pull requests (HA-12).

### PER-05 — Sofia, Application Security Engineer

Sofia reviews security findings across several teams.

- **Goals:** Triage only meaningful alerts. Confirm that active testing stays within authorized targets. Keep a defensible trail of false-positive decisions.
- **Pain points:** Hundreds of unreachable scanner alerts. Teams suppressing rules wholesale. Uncertainty about what DAST touched.
- **Key screens:** SCR-08 Security Testing Center, SCR-11, SCR-14.
- **Permissions:** Security Reviewer. She holds HA-01 (target authorization, shared with Org Admin), HA-02 (DAST), HA-07 for security findings and co-approval on HA-08 for security findings.

### PER-06 — Kenji, Performance Test Engineer

Kenji is the only performance specialist across several teams.

- **Goals:** Catch latency regressions on every release candidate. Trust that percentiles are statistically meaningful. Never damage a shared environment.
- **Pain points:** Load tests happen once per quarter. Environments drift. Results arrive too late to act on.
- **Key screens:** SCR-09 Performance Testing Lab, SCR-14, SCR-04.
- **Permissions:** QA Engineer. He configures performance profiles but needs QA Lead approval (HA-03) for anything above Smoke or against external targets.

### Secondary Stakeholder — Engineering Manager

The Engineering Manager consumes trends rather than detail: verdicts per release, open Confirmed findings by severity, and flaky-register growth. They hold the Viewer role, use SCR-01 and SCR-14, and take no approval actions.

## User Journeys

### UJ-01 — First Job on a Repository

**Persona:** PER-02 Marco (with PER-03 Aisha). **Goal:** Register a repository and get a first evidence-backed report.

1. Marco opens SCR-02 Repositories & Projects, creates the project "Payments Platform" (sample) and adds `northwind/payments-api` by HTTPS URL. The Source Intake Service validates the URL (HTTPS only, private addresses rejected). If validation fails, the dialog shows the error inline, and no job can be created.
2. For a private repository, an Org Admin registers a read-only app token as a credential reference (HA-11). SCR-02 shows only the masked reference.
3. Marco opens SCR-03 New QA Job Wizard. In step 1 he selects ref `main`, and the wizard shows the pinned commit SHA. In steps 2–3 he chooses Functional Standard and Security Quick, with no performance profile.
4. Step 5 (Review) shows the policy summary, estimated duration and budget, and that no approvals are needed. Marco launches the job.
5. On SCR-04 Live Job Execution he watches the 13-stage timeline. The Orchestrator Agent (AG-01) builds the plan, and the Functional Testing Agent (AG-03) runs the Baseline Run in sandbox workers.
6. Results appear on SCR-06. The Evidence and Defect Analysis Agent (AG-08) correlates failures into findings, and the QA Report Agent (AG-11) produces the report on SCR-14 with gate results and a recommendation.
7. Because this is a first run, no performance baseline exists. The report states this as a coverage limitation.

### UJ-02 — Pull-Request Regression Check from CI

**Persona:** PER-04 Daniel. **Goal:** Feedback on a pull request before human code review.

1. Daniel opens a pull request. The CI integration configured on SCR-15 calls `POST /jobs` as the CI Service Account, with an `Idempotency-Key` header and the PR ref.
2. If CI retries the call, the same key within 24 h returns the original response. If an active job already exists for the same repository, SHA and profile hash, the API returns `409` with a link to it.
3. The Requirements Analysis Agent (AG-02) runs change-impact analysis on the diff, and AG-01 schedules affected tests first.
4. Daniel follows progress on SCR-04 through the event stream. A failed test is re-run up to 2 times in fresh workers. In this example, `test_statement_pagination_cursor` passes on rerun and is marked `flaky`, not a defect.
5. A consistent failure becomes a finding. Daniel opens it on SCR-11, reads the reproduction steps and downloads the request and response evidence through a signed, short-lived URL.
6. The CI check receives the JUnit and SARIF exports and the verdict. If the verdict is `NOT_READY`, CI marks the check failed. The platform does not block the merge itself.

### UJ-03 — Security Triage

**Persona:** PER-05 Sofia. **Goal:** Reduce a job's security output to actionable findings.

1. Sofia opens SCR-08 Security Testing Center for job QJ-1042 (sample). She sees Security Standard, each scan with its tool and version, and the findings grid by severity × source class.
2. FND-0197 (sample, Semgrep, possible SQL concatenation, DCS 38) is a Candidate / Scanner alert. She opens it on SCR-11 and reviews the code location and the absence of reachability evidence. She leaves it as a Candidate and requests a targeted reproduction run.
3. FND-0198 (sample, Gitleaks, a password in `tests/fixtures/users.py`) is a test fixture. Sofia marks it false positive with a reason (HA-07). The suppression is scoped to rule plus location fingerprint and expires in 90 days.
4. FND-0194 (sample, PyJWT CVE, Probable, DCS 64) remains Probable because reachability is unconfirmed. Sofia records a note, and the finding stays visible in the report.
5. FND-0193 (sample, IDOR, Critical, Confirmed, DCS 92, reproduced 3/3) needs no promotion. It forces QG-01 and therefore `NOT_READY` until it is resolved.
6. For a Deep profile later, Sofia would first approve the target (HA-01), then approve DAST (HA-02). Aisha would approve the plan (HA-05).

### UJ-04 — Performance Baseline

**Persona:** PER-06 Kenji (with PER-03 Aisha). **Goal:** Establish a baseline and detect regressions.

1. Kenji opens SCR-09 Performance Testing Lab and configures the Baseline profile (20 VUs, 5 min cap) against the ephemeral in-sandbox target, with a p95 threshold of 300 ms for `POST /v1/transfers`.
2. The safety summary shows the caps, abort rules and required approval. Kenji submits, and Aisha approves the run (HA-03).
3. The Performance Testing Agent (AG-06) runs k6 inside the sandbox. Abort rules (for example, error rate > 20% for 60 s) are active throughout.
4. Results show p50/p90/p95/p99, RPS and errors. In the sample job QJ-1042, FND-0199 records p95 412 ms against a 261 ms baseline (+58%) from 6,240 requests. The sample size is sufficient for p95.
5. QG-05 fails, and the report on SCR-14 shows the regression with evidence. If the generator CPU had exceeded 90%, the run would have been marked invalid (generator-bound) rather than producing a finding.

### UJ-05 — Patch Review and Verification

**Persona:** PER-04 Daniel. **Goal:** Review a proposed fix and confirm it independently.

1. For Confirmed finding FND-0193 (sample), the Patch Proposal Agent (AG-09) proposes PCH-0007. On SCR-12 Patch Review, Daniel sees the diff (+14/−3 lines in 2 files, including a new test), the rationale, linked evidence and the "no auto-commit" notice.
2. Daniel approves the patch for verification (HA-06), and its status becomes `approved_for_verification`. Rejecting it would set `rejected` with a reason.
3. The Independent Verification Agent (AG-10) runs VER-0011 in a fresh sandbox on the pinned commit plus the patch, with no access to AG-09's reasoning.
4. On SCR-13 Independent Verification, Daniel compares the original and patched results. Functional tests pass, and the IDOR check no longer reproduces. Performance was not re-run, and the stated justification is that the change is not on the hot path. This limitation is shown explicitly.
5. PCH-0007 becomes `verified`, and an addendum report is produced. Applying the patch to the repository remains Daniel's manual action. Exporting it as a pull request is Future (HA-12).

### UJ-06 — Release Decision

**Persona:** PER-03 Aisha (Engineering Manager informed). **Goal:** Record a defensible release decision.

1. Aisha opens SCR-14 Reports & Release Readiness for the release candidate. QG-01 to QG-08 are listed with results, and the verdict is computed deterministically.
2. In the sample QJ-1041, the verdict is `READY_WITH_RISKS`: no blocking gate failed, but an advisory gate failed or accepted risks are open.
3. For an open Confirmed Medium finding, Aisha accepts the risk with an expiry (HA-08). A security finding would also need Sofia's co-approval.
4. If a blocking gate had failed for a known, documented reason, Aisha could override it (HA-09) with a mandatory, audited reason. The override is visible in the report.
5. Aisha records the release decision (HA-10) in the decision panel. The recommendation and the human decision are stored separately in the audit log.
6. The Engineering Manager sees the verdict and decision on SCR-01.

### UJ-07 — Flaky Test Handling

**Persona:** PER-02 Marco (with PER-03 Aisha). **Goal:** Isolate a flaky test without hiding it.

1. On SCR-06 Functional Test Results, Marco sees a flaky badge on `test_statement_pagination_cursor` (sample). It failed once and passed on a fresh-worker rerun.
2. The Flaky Test Register records the occurrence. After 3 flaky occurrences in 14 days, the platform proposes quarantine.
3. Aisha acknowledges the quarantine. From then on, the test is excluded from the QG-03 pass-rate denominator but still runs and is reported separately.
4. SCR-01 shows the flaky register count. Marco fixes the root cause and the next clean runs are recorded. The quarantine is lifted through the same acknowledgement path.

## Journey to Screen and Approval Map

| Journey | Primary persona | Screens | Agents | Approvals |
|---|---|---|---|---|
| UJ-01 | PER-02 | SCR-02, SCR-03, SCR-04, SCR-06, SCR-14 | AG-01, AG-03, AG-08, AG-11 | HA-11 (if private) |
| UJ-02 | PER-04 | SCR-15, SCR-04, SCR-11 | AG-01, AG-02, AG-03, AG-08 | None |
| UJ-03 | PER-05 | SCR-08, SCR-11 | AG-05, AG-08 | HA-07, HA-01, HA-02, HA-05 |
| UJ-04 | PER-06 | SCR-09, SCR-14 | AG-06, AG-08 | HA-03 |
| UJ-05 | PER-04 | SCR-12, SCR-13 | AG-09, AG-10 | HA-06 |
| UJ-06 | PER-03 | SCR-14, SCR-01 | AG-11 | HA-08, HA-09, HA-10 |
| UJ-07 | PER-02 | SCR-06, SCR-01 | AG-03 | QA Lead acknowledgement |

Detailed use cases and failure scenarios for these journeys are in [use cases and failure scenarios](../04-use-cases/02-use-cases-and-failure-scenarios.md), and user stories are in [user stories and acceptance criteria](../04-use-cases/01-user-stories-and-acceptance-criteria.md).
