# Use Cases and Failure Scenarios

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document describes twelve fully dressed use cases (UC-01 to UC-12) for the proposed Autonomous QA Swarm platform, followed by fifteen failure scenarios (FS-01 to FS-15) that state how the platform is intended to detect, contain and report faults. Use cases refer to personas PER-01 to PER-06, roles from the RBAC model, human approvals HA-01 to HA-12, screens SCR-01 to SCR-15 and functional requirements from [Functional requirements](../03-requirements/01-functional-requirements.md). Job and task state names follow the state machines in the [Low-level design](../05-architecture/03-low-level-design.md). All behavior described is **Proposed**; nothing is implemented. Examples using Northwind Fintech or QJ-1042 are sample data.

## Use cases

### UC-01 Register repository

| Field | Value |
|---|---|
| Primary actor | PER-02 Marco (Automation QA Engineer); Org Admin for private credentials |
| Stakeholders | Org Admin (network safety), Developers (correct source), Security Reviewer (no SSRF) |
| Preconditions | Actor authenticated via OIDC with QA Engineer or higher role; project exists |
| Trigger | Actor selects "Add repository" on SCR-02 or calls `POST /repositories` |
| Related | FR-001–FR-004, SEC-002, SCR-02 · Planned (MVP), Phase 1–2 |

**Main success scenario**

1. Actor enters an HTTPS URL (sample: `northwind/payments-api`) and optional credential reference.
2. Source Intake Service checks the scheme, host allow-list and resolves DNS once, pinning the result.
3. Source Intake Service rejects private, loopback and metadata addresses, then contacts the provider.
4. For a private repository, Source Intake requests a short-lived read-only token from the Secrets Broker using the credential reference.
5. The default branch and recent refs are resolved and stored; validation status becomes "Valid".
6. An audit event records the registration.

**Alternate flows**

- 1a. Credential not yet registered: the Org Admin registers it first (HA-11); the repository stores only the reference.
- 5a. Language not supported in the MVP (sample `northwind/ledger-service`, Java): repository is registered with status "Unsupported language (Phase 4)" and jobs are limited to language-agnostic scans.

**Exception flows**

- 2e. Non-HTTPS URL or disallowed host: `422`, nothing fetched.
- 3e. DNS resolves to a private address: `422` with reason "private address rejected".
- 4e. Credential invalid or revoked: status "Credential error"; the token value is never logged.

**Postconditions:** Repository record exists with validation status, default branch and masked credential reference; no code was executed.

### UC-02 Run QA job on PR or ref

| Field | Value |
|---|---|
| Primary actor | PER-01 Priya or CI Service Account |
| Stakeholders | QA Lead (gate results), Developers (feedback), Org Admin (resource budget) |
| Preconditions | Repository "Valid"; required targets authorized; actor holds a role permitted to create jobs |
| Trigger | Wizard submission on SCR-03, or `POST /jobs` from CI with `Idempotency-Key` |
| Related | FR-002, FR-005–FR-008, FR-010, FR-015, FR-050; SCR-03, SCR-04 · Planned (MVP), Phase 1 |

**Main success scenario**

1. Actor selects repository, ref (sample `release/2.8`), scope and profiles (Functional Standard, Security Standard, Performance Baseline).
2. API Gateway checks idempotency and active-duplicate rules, creates the job in `created` and returns `202`.
3. Job moves to `validating`: Policy Engine checks profiles, targets, budgets and required approvals.
4. Source Intake pins the commit SHA (sample `7c9e2a1f4b`) and creates a checksummed snapshot.
5. Job moves to `queued` then `planning`; the Orchestrator Agent and Requirements Analysis Agent build the plan DAG.
6. If no plan gate applies, the job moves to `running`; stages 3–8 execute per the plan.
7. Job moves through `analyzing` (evidence correlation) and `reporting`, then `completed`.
8. Actor views results on SCR-04 and SCR-14; CI receives JUnit and SARIF exports.

**Alternate flows**

- 5a. Plan approval gate enabled: continue at UC-03.
- 6a. Some tasks end `skipped` or `infrastructure_error`: the job ends `completed_with_warnings`.

**Exception flows**

- 2e. Duplicate submission: see FS-14.
- 3e. Policy refusal (unauthorized target, revoked credential): job ends `blocked`; no task executes.
- 7e. Wall-clock limit (default 4 h) reached: job ends `timed_out`; partial evidence retained.

**Postconditions:** Job is terminal with pinned SHA, plan, tasks, evidence and report stored.

### UC-03 Approve job plan

| Field | Value |
|---|---|
| Primary actor | PER-03 Aisha (QA Lead) |
| Stakeholders | Security Reviewer, Performance Test Engineer, target owners |
| Preconditions | Job in `awaiting_approval`; gate enabled (default for Deep security, Stress/Soak performance) |
| Trigger | Notification to QA Lead; plan opened from SCR-04 or SCR-05 |
| Related | FR-008, FR-009; HA-05; SCR-05 · Planned (MVP), Phase 2 |

**Main success scenario**

1. Aisha opens the plan DAG via `GET /jobs/{job_id}/plan`.
2. She reviews tasks, targets, workload caps, budgets and estimated duration.
3. She approves via `POST /jobs/{job_id}/plan/approval` with an optional comment.
4. Approval is audited and the job moves to `running`.

**Alternate flows**

- 3a. Aisha rejects with a reason: the job ends `cancelled` and the reason is recorded.
- 2a. The plan includes DAST or load above Smoke: HA-02 or HA-03 approvals are also requested from the respective roles.

**Exception flows**

- 3e. The plan changed after it was displayed: `412` (stale ETag); Aisha reloads.
- 3f. No decision before the job wall-clock limit: the job ends `timed_out`.

**Postconditions:** Approved plan is frozen; execution cannot add task types outside it.

### UC-04 Monitor and cancel job

| Field | Value |
|---|---|
| Primary actor | PER-02 Marco |
| Stakeholders | Org Admin (capacity), target owners |
| Preconditions | Job in a non-terminal state |
| Trigger | Marco opens SCR-04 or clicks "Cancel" |
| Related | FR-010, FR-011, FR-012; NFR-003, NFR-008; SCR-04 · Planned (MVP), Phase 1 |

**Main success scenario**

1. SCR-04 subscribes to `GET /jobs/{job_id}/events` and shows stage timeline, task states, redacted log tail and resource usage.
2. Marco clicks "Cancel" and confirms; `POST /jobs/{job_id}/cancel` returns `202`.
3. Job moves to `cancelling`; no new tasks are leased; running tasks are signalled.
4. Execution Service stops and destroys workers within 60 s; tasks become `cancelled`.
5. Job moves to `cancelled`; partial evidence and a partial report are kept.

**Alternate flows**

- 4a. A load test is running: load stops first, then the worker is destroyed.

**Exception flows**

- 2e. Job already terminal: `409`.
- 4e. A worker does not confirm destruction: the orphan reaper (every 5 min) destroys it and an operations alert is raised.

**Postconditions:** No worker for the job remains; cancellation actor and time are audited.

### UC-05 Triage security finding

| Field | Value |
|---|---|
| Primary actor | PER-05 Sofia (Application Security Engineer, Security Reviewer role) |
| Stakeholders | Developers, QA Lead |
| Preconditions | Security finding in `candidate` or `triaging` |
| Trigger | Finding listed on SCR-08 |
| Related | FR-022–FR-024, FR-033, FR-037; HA-07, HA-08; SCR-08, SCR-11 · Planned (MVP), Phase 2 |

**Main success scenario**

1. Sofia opens the finding (sample FND-0197, Semgrep, Candidate, DCS 38).
2. She reviews tool, version, rule, location and any reachability evidence.
3. She requests a reproduction or precondition check; the Evidence Agent schedules it.
4. Based on evidence, Sofia sets status via `POST /findings/{finding_id}/triage`.
5. The decision, reason and evidence links are audited.

**Alternate flows**

- 4a. False positive (sample FND-0198): reason required; scoped suppression created with 90-day expiry (HA-07).
- 4b. Accept risk on a Confirmed finding: requires QA Lead and Security Reviewer with expiry (HA-08).

**Exception flows**

- 4e. Actor lacks Security Reviewer role: `403`.

**Postconditions:** Finding status updated; gates recomputed on next evaluation.

### UC-06 Run performance baseline

| Field | Value |
|---|---|
| Primary actor | PER-06 Kenji (Performance Test Engineer) |
| Stakeholders | QA Lead (HA-03), target owners |
| Preconditions | Ephemeral target defined or external target authorized (HA-01) |
| Trigger | Baseline profile selected in SCR-03 |
| Related | FR-027, FR-029; SEC-017; HA-03; SCR-09 · Planned (MVP), Phase 3 |

**Main success scenario**

1. Kenji selects Baseline (20 VUs, 5 min cap) and thresholds (sample p95 ≤ 300 ms).
2. QA Lead approves (HA-03).
3. Target Environment Manager starts the ephemeral target; a Smoke check confirms health.
4. The Performance Testing Agent proposes the workload; the Policy Engine validates it against profile caps.
5. k6 runs in a sandbox worker; abort rules are monitored.
6. Metrics and comparisons are stored; sample-size warnings are attached where applicable.

**Alternate flows**

- 6a. A regression above 10% is detected: a performance finding is created (sample FND-0199).

**Exception flows**

- 5e. An abort rule fires: see FS-09.
- 5f. Generator CPU > 90%: run marked invalid (generator-bound).

**Postconditions:** PerformanceRun and metrics stored; QG-05 evaluable.

### UC-07 Review mutation results

| Field | Value |
|---|---|
| Primary actor | PER-02 Marco |
| Stakeholders | Developers, QA Lead |
| Preconditions | Mutation stage completed |
| Trigger | Marco opens SCR-10 |
| Related | FR-030, FR-031; QG-06; SCR-10 · Planned (MVP), Phase 3 |

**Main success scenario**

1. Marco reviews score on changed modules (sample 74.7%, 139/186).
2. He inspects surviving mutants with the Mutation Testing Agent's explanations and suggested assertions.
3. He marks suspected equivalent mutants; they are no longer counted as survived.
4. He adopts suggestions as candidate tests, which require review before promotion (FR-016).

**Alternate flows**

- 1a. More than 500 candidate mutants: a sample of 500 is run and the report states the sampling.

**Exception flows**

- 1e. Baseline tests failing: mutation is `skipped` with reason, since kills cannot be measured.

**Postconditions:** QG-06 (advisory) result recorded; reviewed tests queued.

### UC-08 Investigate defect evidence

| Field | Value |
|---|---|
| Primary actor | PER-04 Daniel (Developer) |
| Stakeholders | QA Lead, Security Reviewer |
| Preconditions | Finding exists with linked evidence |
| Trigger | Notification or link from report |
| Related | FR-032–FR-036; NFR-009; SCR-11 · Planned (MVP), Phase 2 |

**Main success scenario**

1. Daniel opens FND-0193 (sample) on SCR-11.
2. He reviews the DCS breakdown, reproduction steps (3/3) and evidence timeline.
3. He downloads request/response evidence via signed, short-lived URLs.
4. He reviews dedup links and the decision trail.

**Alternate flows**

- 2a. Finding is Disputed: Daniel adds context; QA Lead decides.

**Exception flows**

- 3e. Evidence Store unavailable: see FS-13.

**Postconditions:** Investigation actions are audited; no state change unless triage occurs.

### UC-09 Review and approve patch

| Field | Value |
|---|---|
| Primary actor | PER-04 Daniel (code owner) or QA Lead |
| Stakeholders | Security Reviewer, Engineering Manager |
| Preconditions | Patch in `awaiting_review` for a Confirmed finding |
| Trigger | Patch appears on SCR-12 |
| Related | FR-038, FR-039, FR-041; HA-06; SCR-12 · Planned (MVP), Phase 3 |

**Main success scenario**

1. Daniel opens the patch (sample PCH-0008), reading diff, rationale, evidence and risk notes.
2. He approves via `POST /patches/{patch_id}/review`.
3. Status becomes `approved_for_verification`; UC-10 starts.

**Alternate flows**

- 2a. Rejects with reason: status `rejected`; finding stays `confirmed`.

**Exception flows**

- 2e. Not a code owner or QA Lead: `403`.
- 3e. Patch does not apply: see FS-11.

**Postconditions:** Decision audited; repository untouched.

### UC-10 Independent verification

| Field | Value |
|---|---|
| Primary actor | Independent Verification Agent (system), initiated by approver |
| Stakeholders | Developer, QA Lead |
| Preconditions | Patch `approved_for_verification` |
| Trigger | `POST /patches/{patch_id}/verifications` |
| Related | FR-040; QG-07; SCR-13 · Planned (MVP), Phase 3 |

**Main success scenario**

1. Verification Agent receives pinned commit, approved diff and original finding's reproduction, but not the Patch Proposal Agent's reasoning.
2. A fresh worker applies the patch and builds.
3. The original reproduction and relevant functional, API and security checks run.
4. Results are compared with the original; status `verified` (sample VER-0011).
5. An addendum report is produced.

**Alternate flows**

- 3a. Performance not re-run: justification and limitation recorded.

**Exception flows**

- 4e. Reproduction still fails or regression appears: `verification_failed`.
- 4f. Flaky result: see FS-12.

**Postconditions:** Finding `fix_verified` or `fix_failed`; QG-07 updated.

### UC-11 Release-readiness decision

| Field | Value |
|---|---|
| Primary actor | PER-03 Aisha (QA Lead) |
| Stakeholders | Engineering Manager, Developers |
| Preconditions | Job in `completed` or `completed_with_warnings` |
| Trigger | Aisha opens SCR-14 |
| Related | FR-042, FR-043, FR-046; HA-09, HA-10; SCR-14 · Planned (MVP), Phase 2 |

**Main success scenario**

1. Aisha reviews QG-01..QG-08 and the verdict (sample QJ-1041: READY_WITH_RISKS).
2. She reviews residual and accepted risks and coverage limits.
3. She records her decision via `POST /jobs/{job_id}/release-decision` with rationale (HA-10).

**Alternate flows**

- 1a. A gate failed and Aisha overrides it with a mandatory reason (HA-09).

**Exception flows**

- 3e. Job not terminal: `409`.

**Postconditions:** Decision stored with name, time, verdict at decision time; audited.

### UC-12 Configure execution policy and integrations

| Field | Value |
|---|---|
| Primary actor | Org Admin |
| Stakeholders | QA Lead, Security Reviewer |
| Preconditions | Org Admin role |
| Trigger | Admin opens SCR-15 |
| Related | FR-051–FR-053; HA-04, HA-11; SCR-15 · Planned (MVP), Phase 1–3 |

**Main success scenario**

1. Admin sets execution limits within platform maximums (e.g. task wall clock ≤ 2 h).
2. Admin reviews the agent permissions matrix (read-only for denied permissions).
3. Admin configures integrations (GitHub, GitLab, Jenkins, GitHub Actions, Slack/Teams) through credential references (HA-11).
4. Admin configures the Model Gateway route (hosted or local) and token budgets.
5. Changes are versioned and audited.

**Alternate flows**

- 1a. Adding an egress allow-list entry requires explicit HA-04 confirmation.

**Exception flows**

- 1e. Value exceeds platform maximum: `422`.
- 2e. Attempt to grant secrets or egress to an agent: rejected; not configurable.

**Postconditions:** New policy version applies to jobs created afterward; running jobs keep their pinned policy version.

## Failure scenarios

The table summarizes each failure; the narratives below describe the intended detection and response. Retry numbers follow the task state machine: transient errors retry at most 2 times (30 s, 120 s, ±20% jitter), invalid LLM output gets 1 corrective retry, lease TTL is 90 s with 30 s heartbeat.

| ID | Failure | Detection | Task / job outcome | Evidence retained |
|---|---|---|---|---|
| FS-01 | Repository unreachable | Source Intake fetch error or timeout | Job `failed` before planning | Error, DNS result, timestamps |
| FS-02 | Ref deleted after pinning | Provider returns not-found on ref | Continues on pinned SHA snapshot | Pinned SHA, snapshot checksum |
| FS-03 | Sandbox image pull failure | Execution Service pull error or digest mismatch | Task `infrastructure_error` after 2 retries; job `failed` or `completed_with_warnings` | Image digest, registry error |
| FS-04 | Worker OOM | Worker exit code and cgroup OOM event | Test `infrastructure_error`; task retried in fresh worker | Memory metrics, last output |
| FS-05 | Task lease expiry | No heartbeat within 90 s | `failed_retryable` → `retry_scheduled` | Attempt record, last heartbeat |
| FS-06 | LLM provider outage | Model Gateway errors/timeouts | Agent tasks `infrastructure_error` or `skipped`; job `completed_with_warnings` | Gateway error log, prompt hashes |
| FS-07 | Invalid agent output twice | Schema validation fails twice | Task `invalid_output` | Both outputs (hash), validation errors |
| FS-08 | Prompt injection in README | Gateway markers, Policy Engine denial | Proposal denied; task continues or `invalid_output` | Offending content hash, denial record |
| FS-09 | Target down mid performance test | Health check fails 3× | Run aborted; finding candidate or run invalid | Metrics up to abort, abort reason |
| FS-10 | DAST target not authorized | Policy Engine authorization check | Job `blocked` | Policy decision record |
| FS-11 | Patch does not apply | `git apply --check` failure in worker | Verification `verification_failed` (apply error) | Apply output, diff hash |
| FS-12 | Verification flaky | Mixed pass/fail across reruns | Verdict not `verified`; flagged for human | All rerun results |
| FS-13 | Evidence store unavailable | Write/read errors to object store | Tasks pause/retry; no finding Confirmed without evidence | Local buffer, error log |
| FS-14 | Duplicate job submission | Idempotency key or active-duplicate check | Original returned or `409` | Audit event of rejected duplicate |
| FS-15 | Cancellation during verification | Cancel on job with running VerificationRun | Verification task `cancelled`; patch `verification_failed` (reason: cancelled) | Partial verification output |

### FS-01 Repository unreachable

The Source Intake Service attempts the fetch during `validating`. A connection error, TLS error or provider `5xx` is a transient error and is retried at most 2 times with 30 s and 120 s backoff. If all attempts fail, the job ends `failed` with reason "repository unreachable", no plan is built and no worker is started. The user sees the reason on SCR-04 with the option to re-validate via `POST /repositories/{repository_id}/validate`. A `401`/`403` from the provider is not retried and instead marks the credential as needing rotation (HA-11).

### FS-02 Ref deleted after pinning

Because every task reads the immutable source snapshot (identified by SHA-256 checksum), deletion or force-push of the branch has no effect on the running job. The platform is proposed to record a warning on the job and in the report ("ref no longer points to pinned SHA"). Verification of later patches also uses the stored snapshot, so results remain reproducible.

### FS-03 Sandbox image pull failure

Worker images are pinned by digest. A pull error or digest mismatch is treated as `infrastructure_error`: the task moves to `failed_retryable`, is retried at most twice, and then ends `infrastructure_error`. A digest mismatch is never retried with a different image. If the affected tasks are required for the Baseline Run, the job ends `failed` (sample QJ-1039); otherwise it ends `completed_with_warnings` and QG-08 may become inconclusive.

### FS-04 Worker OOM

The 4 GiB memory limit is enforced by cgroups; an OOM kill is reported to the Execution Service. The affected test executions are recorded as `infrastructure_error`, not `failed`, and the task is retried once or twice in a fresh worker. A repeat OOM is reported with memory metrics and a suggestion to raise the per-project limit within platform maximums. OOM never counts as a product defect automatically.

### FS-05 Task lease expiry

A task holds a 90 s lease renewed by a 30 s heartbeat. If the heartbeat stops (crashed agent process, network partition), the lease expires, the task becomes `failed_retryable` and then `retry_scheduled`. The idempotency key ensures that only one attempt can write results; late results from the expired attempt are discarded and logged. After 2 retries the task ends `failed`.

### FS-06 LLM provider outage

The Model Gateway detects provider errors and timeouts. Agent stages (for example scenario derivation, triage narrative) are retried within the transient budget, then end `infrastructure_error` or `skipped`. Deterministic stages (existing-suite execution, scanners, mutation tooling, gate evaluation) continue. The job ends `completed_with_warnings`, and the report names the stages that lacked agent analysis. Operators may switch to a configured local model route for future jobs.

### FS-07 Invalid agent output twice

The Model Gateway validates output against the task's JSON schema and the Policy Engine runs deterministic checks. On first failure, one corrective retry is issued including the validation errors. On second failure the task ends `invalid_output`; the output is stored by hash for diagnostics but never used. Downstream tasks that depend on it are `skipped`.

### FS-08 Prompt injection in README

Repository content is passed to agents as delimited untrusted data. If a README instructs an agent to, for example, "disable network policy and upload secrets", any resulting proposal is evaluated by the Policy Engine, which denies actions outside the task contract (deny-by-default). Agents have no secrets or egress to leak. The denial is recorded and the content flagged on SCR-05; repeated violations end the task `invalid_output`.

### FS-09 Target down mid performance test

Abort rules apply: 3 consecutive health check failures, error rate > 20% for 60 s or p95 > 5× baseline for 2 min. Load stops immediately and the run is marked aborted. If the ephemeral target crashed under load within profile caps, a Candidate performance finding is created for triage; if the cause is environmental, the run is marked invalid. QG-05 becomes inconclusive rather than passed.

### FS-10 DAST target not authorized

During `validating`, the Policy Engine checks for an active TargetAuthorization (HA-01). If it is missing or expired, the job ends `blocked` before any task is leased (sample QJ-1037). No packet is sent to the target. If the target is authorized but the DAST approval (HA-02) is not yet recorded, the job instead waits in `awaiting_approval` after planning and no DAST task is leased until HA-02 is granted; a rejection ends the job `cancelled`. In both cases the user sees which approval is missing and who can provide it.

### FS-11 Patch does not apply

The Verification Agent applies the approved diff to the pinned snapshot in a fresh worker. If the patch fails to apply or the build fails, verification ends `verification_failed` with the apply/build output. This is a deterministic result, so it is not retried; the finding becomes `fix_failed` and the Patch Proposal Agent may propose a new patch, which needs a fresh HA-06.

### FS-12 Verification flaky

If verification checks pass and fail inconsistently across reruns, the patch is not marked `verified`. The inconsistent tests are added to the Flaky Test Register; verification ends `verification_failed` with a "flaky" note, and the QA Lead decides whether to re-run after the flakiness is addressed. QG-07 cannot pass on a flaky verification.

### FS-13 Evidence store unavailable

Evidence writes go to the S3-compatible Evidence Store. On failure, tasks retain bounded output in the worker's collection buffer and retry the upload within the transient budget. If upload still fails, the task ends `infrastructure_error`. Findings that lack stored evidence cannot reach Confirmed ("No evidence, no defect"). Downloads on SCR-11 show a temporary error with `503`.

### FS-14 Duplicate job submission

A repeated `POST /jobs` with the same `Idempotency-Key` within 24 h returns the original response. A different key for an active job with the same repository, commit SHA and profile hash returns `409` with a link to the existing job, unless a QA Lead sets `force_new=true`. Within a job, task idempotency keys prevent duplicate work.

### FS-15 Cancellation during verification

If a job is cancelled while a VerificationRun is in progress, the verification task becomes `cancelled`, the worker is destroyed within 60 s and partial output is kept. The patch is recorded as `verification_failed` with reason "cancelled before completion" so that it can never be counted as `verified`, and the finding stays `fix_proposed` rather than `fix_failed` because no negative result was observed. The approver can start a new verification of the unchanged diff with `POST /patches/{patch_id}/verifications`; any change to the diff requires a fresh HA-06.

## Related documents

Detailed agent behavior is described in the [Agent catalogue](../06-agent-design/01-agent-catalogue.md) and [Orchestration and recovery](../06-agent-design/02-orchestration-and-recovery.md). Sandbox limits are in [Sandboxed execution](../10-security-and-threat-model/03-sandboxed-execution.md), and gate logic is in [Quality gates and release readiness](../11-quality-gates-and-reporting/02-quality-gates-and-release-readiness.md).
