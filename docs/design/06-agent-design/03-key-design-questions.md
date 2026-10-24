# Key Design Questions

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document answers the design questions most often asked about a multi-agent QA platform. Each answer names the concrete proposed mechanism, the numbers that bound it and the document where it is specified in detail. Nothing described here is implemented; all mechanisms are **Proposed**, and most are **Planned (MVP)** within Phases 1–3. Where a mechanism reduces rather than removes a risk, the residual risk is stated.

## How are agents assigned work and prevented from duplicating tasks?

Agents do not choose their own work. The Orchestrator Agent (AG-01) builds a validated job plan (DAG), and its Workflow Engine writes each unit of work as a Task row in a PostgreSQL task queue. Agent runtimes take tasks with `SELECT … FOR UPDATE SKIP LOCKED`, which grants a **lease** of 90 s renewed by a heartbeat every 30 s. Only the lease holder can write results, and every write carries a lease token so a holder whose lease expired cannot overwrite a newer attempt.

Duplication is prevented by an **idempotency key** per task: SHA-256(job_id, stage, task_type, canonical input hash), enforced by a unique constraint. If the planner proposes the same task twice, two correlation passes request the same reproduction, or the control plane replays planning after a restart, the second enqueue is a no-op. Details: [Orchestration and recovery](02-orchestration-and-recovery.md).

## How are conflicting agent conclusions reconciled?

A fixed precedence order applies: (1) deterministic reproduced evidence, (2) deterministic single-run evidence, (3) tool output without reproduction, (4) LLM agent judgement. When, for example, the Functional Testing Agent reports a defect while the API Testing Agent's contract test passes, the Evidence and Defect Analysis Agent (AG-08) schedules a targeted reproduction task in a fresh sandbox. If the reproduction settles it, the deterministic Defect Confidence Score (DCS) decides the level. If not, the finding is flagged **Disputed**, remains `triaging` and is routed to human triage. It is never auto-confirmed or auto-dismissed (FR-036). Details: [Orchestration and recovery](02-orchestration-and-recovery.md) and [Evidence and defect analysis](../11-quality-gates-and-reporting/01-evidence-and-defect-analysis.md).

## How are findings supported by reproducible evidence?

The principle is **"No evidence, no defect."** Every signal that becomes a finding links to EvidenceItem objects in the Evidence Store, which is content-addressed by SHA-256 and immutable. Evidence includes inputs, outputs, logs, environment, pinned commit and tool version (FR-032). Confirmation requires:

- reproduction in a fresh sandbox in at least 2 of 3 runs (FR-035);
- a DCS of at least 80, computed deterministically from reproducibility (35), deterministic oracle (25), evidence completeness (15), independent corroboration (15) and stability history (10) (FR-033).

LLM opinion can contribute only to the corroboration component and can never lift a finding to Confirmed. Because the source snapshot, image digests and tool versions are pinned, re-running a reproduction recipe is intended to give the same deterministic result (NFR-007), apart from documented nondeterminism. Sample: FND-0193 is shown as Confirmed with DCS 92, reproduced 3/3.

## How are false positives and flaky tests handled?

**Flaky tests.** A failed test is re-run up to 2 times in fresh workers. If any rerun passes, it is classified `flaky`, recorded in the Flaky Test Register and reported separately from defects (FR-018). After 3 flaky occurrences in 14 days it may be quarantined, which excludes it from the QG-03 pass-rate denominator only after QA Lead acknowledgement. Stability history feeds the DCS so that findings based on unstable tests score lower.

**False positives.** Scanner output starts as `candidate` with source class "Scanner alert". Promotion to "Probable vulnerability" or "Confirmed vulnerability" needs reachability or precondition evidence. Marking a finding false positive requires an authorized human reviewer and a reason (HA-07); agents cannot do it. Suppressions are scoped to rule plus location fingerprint and expire after 90 days by default. The proposed target is that no more than 5% of Confirmed findings are later judged false positives by human triage over 30 days (NFR-010); this is a measured goal, not a guarantee. Details: [Security testing](../09-testing-workflows/02-security-testing.md) and [Functional and API testing](../09-testing-workflows/01-functional-and-api-testing.md).

## How is test execution isolated from untrusted repositories and code?

Repository code is treated as hostile. The control plane never executes it (SEC-001); it only produces a read-only, checksummed source snapshot. All builds, tests, scanners, mutants and load generators run in disposable Sandbox Workers with these proposed defaults: 2 vCPU, 4 GiB RAM, 512 PIDs, 10 GiB ephemeral disk, 30 min per task (max 2 h), 50 MiB captured output, non-root UID 10001, read-only root file system, all Linux capabilities dropped, `no-new-privileges`, default seccomp and AppArmor, no Docker socket, no host mounts and no host namespaces.

Network is **off** during execution. Dependencies are fetched in a separate phase through an egress proxy allow-listed to package registries, with cloud metadata IPs and RFC1918 ranges blocked. Worker images are pinned by digest, signed and SBOM-tracked (SEC-006). MVP isolation uses rootless containers with gVisor (runsc); Firecracker microVMs or Kata Containers are **Future** for hostile multi-tenant use. Workers are destroyed within 60 s of a terminal task state, with an orphan reaper every 5 min (NFR-008). Residual risk: a sandbox escape vulnerability in the isolation layer remains possible, which is why microVM isolation is on the roadmap. Details: [Sandboxed execution](../10-security-and-threat-model/03-sandboxed-execution.md).

## How are API credentials and secrets protected?

Secrets live only in the Secrets Broker (OpenBao or HashiCorp Vault proposed). The database stores CredentialReference records, never raw tokens (FR-003). The broker issues short-lived, scoped tokens to the Source Intake Service and Target Environment Manager only. Agents and LLMs never receive secrets (SEC-007). The single exception is target test-user credentials: scoped, short-lived, non-production values injected into a worker when the target is authorized, never into an agent prompt.

Redaction applies to logs, evidence, prompts and reports (SEC-008); the Model Gateway redacts before sending any prompt. Registering or rotating credentials requires an Org Admin (HA-11). Details: [Identity, secrets, audit and data protection](../10-security-and-threat-model/02-identity-secrets-audit-and-data-protection.md).

## How are resource-intensive or potentially disruptive tests restricted?

Every disruptive capability is bounded by profile caps, approvals and automatic abort rules, all enforced by deterministic services rather than agents:

| Area | Bound | Approval |
|---|---|---|
| Performance Smoke | 5 VUs, 1 min | None for ephemeral target |
| Performance Baseline | 20 VUs, 5 min | HA-03 |
| Load / Stress / Spike / Soak (Future) | Up to 100 / 500 / 300 VUs; 15 min / 20 min / 5 min / 2 h | HA-03, plus HA-05 for Stress, Spike, Soak |
| DAST (Deep profile, Future) | 60 min, passive first then active rules | HA-01, HA-02, HA-05 |
| Any external target | Must have active TargetAuthorization | HA-01, HA-03 for performance |

Load runs abort automatically when error rate exceeds 20% for 60 s, the target health check fails 3 times consecutively, or p95 exceeds 5× baseline for 2 min; generator CPU above 90% marks the run invalid. Security checks stop at proof of reachability and are non-destructive by default (SEC-018). Details: [Performance testing](../09-testing-workflows/03-performance-testing.md) and [Safe use policies](../10-security-and-threat-model/04-safe-use-policies.md).

## How are mutations created, evaluated, and cleaned up?

The Mutation Testing Agent (AG-07) wraps deterministic tools (mutmut for Python, Stryker for JS/TS in the MVP; PIT for Java is Future). Mutants are generated only for changed modules, capped at 500 per job, inside the sandbox; they never leave it. Each mutant runs with a timeout of 2 × baseline test time + 10 s. The score is computed deterministically: killed / (killed + survived) × 100 over valid, completed mutants. Timed-out and invalid mutants are excluded and reported separately (sample: 139 / 186 = 74.7%). Suspected equivalent mutants are flagged, and are excluded from "survived" only once a human marks them. The agent explains survivors and suggests assertions, which are unreviewed suggestions. Cleanup is the normal worker destruction; no mutated code is persisted beyond the mutant descriptor and result. QG-06 (≥ 60%) is advisory. Details: [Mutation testing](../09-testing-workflows/04-mutation-testing.md).

## How are proposed patches reviewed and independently verified?

The Patch Proposal Agent (AG-09) proposes a minimal diff with rationale, risk notes and evidence links for Confirmed findings only. It never commits, pushes or merges (FR-041). Deterministic checks verify that the diff parses and applies, touches existing paths, and flag deleted assertions, deleted tests or changes to build and CI files.

A Developer who owns the code or a QA Lead must approve the patch for verification (HA-06). The Independent Verification Agent (AG-10) then applies the diff to the pinned commit in a **fresh** sandbox, without access to the Patch Proposal Agent's reasoning, and re-runs the original reproduction plus relevant functional, API, security and, where justified, performance checks. The verdict (`verified` or `verification_failed`) is deterministic; flaky results cannot produce `verified`; checks not re-run are stated with justification (sample VER-0011 did not re-run performance). QG-07 requires 100% of patches in the release candidate to be `verified`. Exporting a patch as a pull request is **Future** and requires HA-12. Details: [Patch proposal and verification](../09-testing-workflows/05-patch-proposal-and-verification.md).

## What happens when an agent times out, fails, or returns invalid output?

| Event | Handling | Final state if unresolved |
|---|---|---|
| Lease not renewed within 90 s | Task becomes `failed_retryable`, then retried | `failed` after 2 retries |
| Transient error (provider, worker) | Retries at 30 s and 120 s, jitter ±20% | `failed` / `infrastructure_error` |
| Invalid output (schema or semantic) | 1 corrective retry with validation errors | `invalid_output` |
| Task wall clock exceeded | Stopped; worker destroyed | `timed_out` |
| LLM outage | Deterministic stages continue | Agent tasks `skipped` / `infrastructure_error` |

Where a deterministic fallback exists (template plan, existing suites, raw scanner alerts, report without narrative), it is used. A job with any such task ends `completed_with_warnings`, and QG-08 turns the verdict `INCONCLUSIVE` if more than 5% of tasks ended `infrastructure_error` or `timed_out`. Details: [Orchestration and recovery](02-orchestration-and-recovery.md).

## How are retries bounded and duplicate jobs prevented?

Retries are bounded by error class, not by agent preference: max 2 retries for transient errors, max 1 corrective retry for invalid LLM output, up to 2 reruns for flaky detection, and **no** retries for deterministic test failures, which are results. Each retry is a new TaskAttempt in a new worker.

Duplicate jobs are prevented at the API: `POST /jobs` requires an `Idempotency-Key`, and a repeat within 24 h returns the original response. An active job with the same repository, commit SHA and profile hash returns `409` with a link to the existing job unless a QA Lead sets `force_new=true`, which is audited (FR-006). Details: [API contracts](../08-api-specifications/01-api-contracts.md).

## How are audit trails and execution history preserved?

All approvals, triage actions, overrides, policy decisions and state transitions are written to an append-only, hash-chained Audit Log (SEC-013, FR-054); the chain is verified on control-plane restart and on demand, so tampering is detectable. Execution history is kept as Task, TaskAttempt, AgentOutput (with prompt and response hashes), WorkerRun and TestExecution records in PostgreSQL, with evidence in the Evidence Store. Default retention is 90 days for evidence and 1 year for audit events, configurable per deployment (NFR-016). `GET /audit-events` filters by job, actor and action. Details: [Identity, secrets, audit and data protection](../10-security-and-threat-model/02-identity-secrets-audit-and-data-protection.md).

## How can users understand why a defect or release risk was reported?

Every reported finding is designed to link to its evidence, tool and version, and decision trail (NFR-009). On SCR-11 (Defect Evidence & Investigation) the user sees the DCS breakdown by component, reproduction steps and counts, the evidence timeline, deduplication links and every status change with actor and reason. On SCR-05 (Agent Collaboration Graph) the user can open any agent task and see its inputs, outputs, permissions and provenance.

For release risk, SCR-14 (Reports & Release Readiness) shows each gate QG-01 to QG-08 with measured value, threshold and contributing findings, and the deterministic verdict logic: any failed blocking gate gives `NOT_READY`; otherwise any inconclusive gate gives `INCONCLUSIVE`; otherwise failed advisory gates or open accepted risks give `READY_WITH_RISKS`; otherwise `READY`. Aggregate scores never hide blockers: an open Confirmed Critical finding forces `NOT_READY`. Report narratives are cross-checked against aggregates. Details: [Quality gates and release readiness](../11-quality-gates-and-reporting/02-quality-gates-and-release-readiness.md).

## How can the platform operate with open-source or free tooling without assuming every external service is free?

The design requires that the full pipeline can run with open-source components only (NFR-018): PostgreSQL, an S3-compatible store such as SeaweedFS or Ceph RGW, Keycloak, OpenBao, Open Policy Agent, gVisor, OpenTelemetry, and test, security, performance and mutation tools such as pytest, Playwright, Schemathesis, Semgrep CE, Gitleaks, OSV-Scanner, Trivy, k6, Locust, mutmut and Stryker. LLM access goes through a provider-agnostic Model Gateway that can use local open-weight models via Ollama or vLLM.

Free licenses are not the same as free operation. Local models need GPU or CPU compute; hosted LLMs, cloud storage and SaaS CI are paid, optional adapters whose cost is the operator's responsibility. Per-job token and compute budgets are enforced and reported (NFR-015). License conditions differ (for example k6, Grafana and Loki are AGPL-3.0, MinIO is AGPL-3.0, Vault is BUSL-1.1 and not OSI open source, Semgrep registry rules have their own terms) and must be re-verified at adoption. Details: [Technology options](../05-architecture/05-technology-options.md).

## Which actions require human approval?

| ID | Action | Approver |
|---|---|---|
| HA-01 | Register a target and attest authorization to test it | Org Admin or Security Reviewer |
| HA-02 | Run DAST or active security checks | Security Reviewer |
| HA-03 | Run performance above Smoke, or any profile against an external target | QA Lead |
| HA-04 | Add sandbox outbound allow-list entries | Org Admin |
| HA-05 | Approve a job plan when the gate is enabled | QA Lead |
| HA-06 | Approve a patch for verification | Developer (code owner) or QA Lead |
| HA-07 | Mark a finding false positive or suppress a rule | Security Reviewer / QA Lead |
| HA-08 | Accept risk on a Confirmed finding, with expiry | QA Lead + Security Reviewer for security |
| HA-09 | Override a failed quality gate, reason mandatory | QA Lead |
| HA-10 | Record the release decision | QA Lead |
| HA-11 | Register or rotate repository or target credentials | Org Admin |
| HA-12 | Export a verified patch or generated tests as a pull request (Future) | Developer (code owner) |

No agent holds any approval permission, and the platform only recommends a release verdict; a named human records the decision.

## How is AI agent output validated rather than trusted?

Agent output is treated as untrusted input in four layers:

1. **Untrusted inputs are marked.** Repository content is delimited as data in prompts (SEC-014); instructions found in a README or code comment have no authority.
2. **Schema validation.** The Model Gateway validates every response against the task's output schema (SEC-015) and records prompt and response hashes plus template version and model route as provenance.
3. **Deterministic semantic checks.** References to tests, files, operations, findings and evidence hashes must resolve; numbers in narratives must match stored metrics; status fields cannot be set by agents.
4. **Policy evaluation.** Every proposed task contract is evaluated deny-by-default by the Policy Engine for scope, target authorization, budgets and network rules before the Execution Service runs it.

Failures get one corrective retry, then `invalid_output`. Beyond validation, scoring and verdicts are deterministic, confirmation requires reproduced evidence, and human gates cover every consequential action. Residual risk: a well-formed but wrong agent proposal (for example a poorly chosen test selection) can pass validation; QG-04 coverage measurement, plan review under HA-05 and human triage are the intended mitigations. Details: [Agent catalogue](01-agent-catalogue.md) and [Security architecture and threat model](../10-security-and-threat-model/01-security-architecture-and-threat-model.md).
