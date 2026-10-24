# Glossary

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This glossary defines terms used across the Autonomous QA Swarm documentation set. Where a term names a state, status or verdict, the API value is given in `lower_snake_case` (or upper case for verdicts) as used in [API contracts](../08-api-specifications/01-api-contracts.md); the UI shows the same value in Title Case. Definitions describe the proposed design; none of the mechanisms is implemented yet.

## Terms A to B

| Term | Definition |
|---|---|
| Accepted risk | Finding status `accepted_risk`: a Confirmed finding a QA Lead (plus Security Reviewer for security) chose to tolerate with reason and expiry (HA-08) |
| `advisory_failed` | Gate result state: a non-blocking gate's threshold was not met |
| Advisory gate | A quality gate whose failure yields `advisory_failed` and at worst READY_WITH_RISKS; QG-06 by default |
| Agent | An LLM-assisted component (AG-01 to AG-11) that emits typed proposals; agents never execute code, hold credentials or change repositories |
| `analyzing` | Job state in which results are correlated into findings |
| `approved_for_verification` | Patch status after a human approved it for independent verification (HA-06) |
| Audit Log | Append-only, hash-chained record of actions and decisions (SEC-013) |
| `awaiting_approval` | Optional job state after planning that waits for plan approval (HA-05) and any profile approvals still missing (HA-02, HA-03) |
| `awaiting_review` | Patch status: proposal waiting for human review (HA-06) |
| Baseline (performance) | Reference measurements from an earlier run used to compute regressions; also the name of a 20 VU, 5 min performance profile |
| Baseline Run | Pipeline stage 4: existing suites run on the pinned commit before new testing |
| `blocked` | Job state when policy refused the job before execution; also a test result when a test could not run because a prerequisite was missing |
| BOLA / IDOR | Broken Object Level Authorization / Insecure Direct Object Reference: access to another user's object by changing an identifier (CWE-639) |

## Terms C to D

| Term | Definition |
|---|---|
| `cancelled` | Terminal job or task state after a cancellation request completed |
| `cancelling` | Intermediate job state while workers are being stopped and destroyed |
| Candidate | Confidence level for DCS below 50; also the initial finding status `candidate` |
| Chain of custody | The record of who produced, accessed, exported or deleted an evidence item and when |
| `completed` | Terminal job state: the pipeline finished without warnings |
| `completed_with_warnings` | Terminal job state: pipeline finished but some tasks ended `skipped`, `infrastructure_error` or `timed_out`, or a gate is `inconclusive` |
| Confirmed | Confidence level for DCS ≥ 80 and reproduced; also finding status `confirmed` |
| Content addressing | Storing an object under the SHA-256 digest of its bytes, so identity equals content |
| Correlation ID | Identifier (trace, job, task, worker run) attached to telemetry to connect events across services |
| `created` | Initial job state after a valid creation request |
| CVE | Common Vulnerabilities and Exposures: public identifiers for known vulnerabilities |
| CVSS | Common Vulnerability Scoring System; base scores (v3.1/v4) are mapped to platform severity |
| CWE | Common Weakness Enumeration: catalogue of weakness types, for example CWE-639 |
| DAG | Directed acyclic graph; the job plan's task structure |
| DAST | Dynamic Application Security Testing: probing a running application; only against authorized targets (HA-02) |
| Decision trail | The "Why was this reported?" record linking a finding to evidence, oracle, scores, reproduction and human actions |
| Defect Confidence Score (DCS) | Deterministic 0–100 score from reproducibility (35), deterministic oracle (25), evidence completeness (15), corroboration (15) and stability history (10) |
| Dependency-fetch phase | Worker phase in which packages are downloaded through an allow-listed egress proxy before network is switched off |
| Disputed | Flag on a finding whose conflicting evidence remains unresolved after targeted reproduction; stays `triaging` and goes to human triage |
| `duplicate` | Finding status for a signal merged into an existing finding with the same fingerprint |

## Terms E to I

| Term | Definition |
|---|---|
| Environment manifest | JSON record of worker image digest, limits, network phases, tool versions, commit SHA and seeds for a worker run |
| Equivalent mutant | A mutant that behaves identically to the original program, so no test can kill it; flagged and excluded when marked |
| Evidence item | An immutable, content-addressed artifact (log, result, trace, screenshot, SARIF, metrics) with metadata |
| Evidence Store | S3-compatible, content-addressed, immutable, retention-managed object storage for evidence |
| Exposure | Risk Priority factor: 1.0 changed or externally reachable code, 0.7 internal, 0.4 test-only |
| `failed` | Terminal job or task state for unrecoverable failure; test result for a failing assertion; gate result state for a blocking gate not met |
| `failed_retryable` | Task state after a transient error or expired lease, eligible for retry |
| False positive | A reported issue that is not a real defect; finding status `false_positive`, set via HA-07 |
| Fingerprint | SHA-256(category, normalized location, normalized signature, rule/CWE id) used for deduplication |
| `fix_failed` | Finding status when a proposed patch did not pass verification |
| `fix_proposed` | Finding status when a patch proposal exists for it |
| `fix_verified` | Finding status when its patch passed independent verification |
| `flaky` | Derived test classification: failed, then passed on a fresh-worker rerun |
| Flaky Test Register | Per-project list of FlakyTestRecord entries; source for quarantine |
| gVisor | User-space kernel (`runsc`) that intercepts system calls; the proposed MVP sandbox isolation layer |
| Hard blocker | Open Confirmed Critical finding, or open Confirmed High security finding without accepted risk; forces NOT_READY |
| Human approval (HA) | One of HA-01 to HA-12: actions that require a named human with a specific role |
| Idempotency key | Value that makes repeated requests safe: the `Idempotency-Key` header for job creation, and SHA-256(job_id, stage, task_type, input hash) for tasks |
| `inconclusive` | Gate result state when there is not enough valid data to decide |
| INCONCLUSIVE | Verdict when no blocking gate failed but at least one gate is `inconclusive` |
| `infrastructure_error` | A test-execution result status, and an error class on tasks, for failures caused by the platform or environment rather than the code under test. A task with this error class ends in state `failed` once its retries are exhausted |
| `invalid_output` | Task state after an agent's output failed schema validation and one corrective retry |

## Terms J to P

| Term | Definition |
|---|---|
| Job | One QA run of a pinned commit with selected profiles; display ID such as QJ-1042 |
| Job plan | Validated task DAG produced in the Planning stage (JobPlan entity) |
| Lease | Time-limited claim on a task by a worker process: TTL 90 s, heartbeat every 30 s |
| `leased` | Task state while a lease is held but execution has not started |
| Model Gateway | Single egress point to LLM providers with redaction, token budgets and output validation |
| Mutant | A copy of the code with a small deliberate change, used to test whether tests detect it |
| Mutation score | killed / (killed + survived) × 100 over valid, completed mutants |
| `not_applicable` | Gate result state when the gate's precondition did not occur |
| NOT_READY | Verdict when a hard blocker exists or a blocking gate failed without override |
| `not_reproducible` | Finding status when reproduction runs failed to show the defect |
| Oracle | The mechanism that decides whether an observed result is correct |
| Orphan worker | A sandbox worker still alive after its task reached a terminal state; removed by the reaper every 5 minutes |
| Override | HA-09 action by a QA Lead to proceed despite a failed gate; reason mandatory, audited |
| `passed` | Test result for a passing test; gate result state when the threshold is met |
| `pending` | Initial task state before a lease |
| Pinned commit | The immutable commit SHA resolved from a ref at intake; all testing uses it |
| `planning` | Job state in which the job plan is built |
| Policy Engine | Deterministic, deny-by-default service validating every agent proposal (OPA/Rego proposed) |
| Probable | Confidence level for DCS 50–79 |
| Profile | Named configuration of a testing type, such as Security Quick/Standard/Deep or Performance Smoke to Soak |
| Prompt injection | Untrusted content containing instructions meant to manipulate an LLM agent |
| `proposed` | Initial patch status |

## Terms Q to R

| Term | Definition |
|---|---|
| Quality gate | A measurable check (QG-01 to QG-08) over job results with a threshold and blocking setting |
| Quarantine | Exclusion of a flaky test from the QG-03 denominator after 3 flaky occurrences in 14 days and QA Lead acknowledgement |
| `queued` | Job state waiting for scheduling capacity |
| READY | Verdict when all gates passed or are not applicable and no accepted risks are open |
| READY_WITH_RISKS | Verdict when no blocking gate failed and none is inconclusive, but an advisory gate failed or accepted risks are open |
| `rejected` | Patch status when a reviewer declines it |
| Rejected | Confidence display level for findings that are `false_positive` or `not_reproducible` |
| `reopened` | Finding status when a previously fixed or closed finding reappears |
| `reporting` | Job state in which gates are evaluated and the report is produced |
| `reproducing` | Finding status while reproduction runs are in progress |
| Reproduction run | Re-execution of a failing check in a fresh sandbox; reproduced when 2 of 3 runs agree |
| Residual risk | Risk that remains after testing: unconfirmed findings, coverage gaps, accepted risks and profile limits |
| `retry_scheduled` | Task state waiting for backoff before a new lease |
| Risk Priority | Severity weight × Confidence factor × Exposure; used for ordering findings |
| `running` | Job or task state while execution is in progress |

## Terms S to Z

| Term | Definition |
|---|---|
| SARIF | Static Analysis Results Interchange Format 2.1.0, used for scanner output and exports |
| SAST | Static Application Security Testing: analysis of source code without running it |
| SCA | Software Composition Analysis: detection of vulnerable or risky third-party dependencies |
| Scanner alert | Security source class for raw tool output not yet supported by reachability evidence |
| Secrets Broker | Service that holds credentials and issues short-lived scoped tokens; never to agents |
| Severity | Critical, High, Medium, Low or Informational |
| `skipped` | Test result or task state when execution was intentionally not performed |
| SSE | Server-Sent Events: one-way HTTP stream used by `GET /jobs/{job_id}/events` |
| SSRF | Server-Side Request Forgery: tricking a server into requesting internal resources; prevented in repository URL validation |
| `succeeded` | Terminal task state for successful completion |
| Suppression | Scoped (rule plus location fingerprint), expiring exclusion of a scanner rule result; default 90 days |
| Surviving mutant | A mutant not detected by any test; indicates a possible test gap |
| Target environment | An application instance under test: ephemeral in-sandbox or registered non-production |
| Task | Unit of work in a job plan, executed through leases and attempts (Task, TaskAttempt entities) |
| `timed_out` | Job, task or test state after exceeding its time limit |
| `triaging` | Finding status while evidence is assessed |
| `validating` | Job state while inputs, policy and source are checked |
| Verdict | Release-readiness recommendation: READY, READY_WITH_RISKS, NOT_READY or INCONCLUSIVE |
| `verification_failed` | Patch status when independent verification did not pass |
| `verification_running` | Patch status during independent verification |
| `verified` | Patch status after passing independent verification in a fresh sandbox |
| VU | Virtual user in a load test |
| Worker (sandbox) | Disposable, isolated container or microVM that runs builds, tests, scanners or load generators |

## Related documents

- [References](02-references.md)
- [Data model and ERD](../07-data-model/01-data-model-and-erd.md)
- [Evidence and defect analysis](../11-quality-gates-and-reporting/01-evidence-and-defect-analysis.md)
