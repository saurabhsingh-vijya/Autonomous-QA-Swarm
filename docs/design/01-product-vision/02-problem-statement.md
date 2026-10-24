# Problem Statement

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document describes the QA workflow limitations that Autonomous QA Swarm is proposed to address. Each limitation is described by its symptom, its impact, the platform's proposed response and the part of the problem the platform will not solve. The proposed responses are design intent only. Their effectiveness has not been measured, and the [vision, objectives and metrics](03-vision-objectives-and-metrics.md) document defines how it will be.

## Context

Most delivery teams already have unit tests, a CI server, one or more security scanners and occasional load tests. The problem is rarely that tools are missing. The tools are hard to run consistently, their outputs are hard to trust and combine, and the people who must decide whether to release rarely have a single, evidence-backed view. AI coding assistants add capacity but also add a new class of unverified output. The limitations below are the ones the platform design is built around.

## Limitations of Current QA Workflows

### 1. Regression Load Grows Faster Than Capacity

- **Symptom:** Every release adds tests. Full regression runs take hours, and manual regression checklists keep growing.
- **Impact:** Teams either run everything (slow) or run a hand-picked subset (risky and undocumented). Manual QA engineers spend release weeks re-executing known scenarios.
- **Proposed response:** The Requirements Analysis Agent will perform change-impact analysis from the diff to affected modules and tests (FR-014). The Orchestrator Agent will build a task DAG that prioritizes P0 scenarios. The plan is validated and visible, so the selection is documented rather than tacit. QG-04 requires ≥ 95% of P0 and ≥ 85% of P1 planned scenarios to actually execute, or the verdict becomes `INCONCLUSIVE`.
- **Will not solve:** Impact analysis can miss indirect coupling, such as configuration, data or shared infrastructure. Teams will still need periodic full runs, and the platform cannot replace exploratory testing.

### 2. Slow Feedback

- **Symptom:** Developers learn about failures hours or days after a change, often after merging.
- **Impact:** Context is lost, fixes cost more, and defects pile up near release dates.
- **Proposed response:** CI-triggered jobs on pull-request refs (FR-052), a target of ≤ 60 s from job creation to first running task on a warm pool (NFR-002), and live progress over Server-Sent Events (FR-010). Stages 5–8 may run in parallel within the resource budget.
- **Will not solve:** A deep job (security Deep, mutation, performance) can still take hours. The default job wall-clock limit is 4 h. Feedback speed is bounded by the project's own build and test time.

### 3. Flaky Tests Erode Trust

- **Symptom:** Tests fail intermittently. Engineers re-run pipelines until they turn green.
- **Impact:** Real failures are dismissed as "probably flaky", and pass rates become meaningless.
- **Proposed response:** Each failed test will be re-run up to 2 times in fresh workers. A pass on rerun classifies the result as `flaky`, not a defect, and records it in the Flaky Test Register (FR-018). A test is quarantined, which excludes it from the QG-03 pass-rate denominator, only after 3 flaky occurrences in 14 days and only with QA Lead acknowledgement. Flaky results are reported separately and never hidden.
- **Will not solve:** The platform is proposed to detect and isolate flakiness. It would not fix the root cause, such as timing, shared state or order dependence. A test that fails consistently for environmental reasons will look like a defect until humans triage it.

### 4. Scanner Noise and False Positives

- **Symptom:** SAST and dependency scanners produce hundreds of alerts per run, many unreachable or irrelevant (for example, a hard-coded password in a test fixture).
- **Impact:** Alert fatigue. Real vulnerabilities get lost, and teams suppress rules wholesale.
- **Proposed response:** Every scanner finding starts as a Candidate and "Scanner alert". Promotion to Probable or Confirmed requires reachability or precondition evidence. Findings are deduplicated by fingerprint (FR-034). Marking a false positive requires a reviewer and a reason (HA-07). Suppressions are scoped to rule plus location fingerprint and expire after 90 days by default.
- **Will not solve:** Reachability analysis is imperfect, and some real issues will remain Candidates. Scanner blind spots, such as business-logic flaws and novel vulnerability classes, are not covered by adding triage on top.

### 5. Siloed Tools and Fragmented Results

- **Symptom:** Test results live in CI, security findings in a scanner console, load results in a separate dashboard and defects in a tracker.
- **Impact:** Nobody sees the combined risk picture. The same root cause is reported three times by three tools, and release meetings become manual reconciliation.
- **Proposed response:** One QA job will run functional, API, security, performance and mutation work against the same pinned commit SHA. The Evidence and Defect Analysis Agent will correlate signals into a single finding list. The QA Report Agent will produce one report with quality gates QG-01 to QG-08, exported as JSON, HTML, PDF, SARIF and JUnit XML for existing tools.
- **Will not solve:** The platform does not replace issue trackers or the team's existing CI. Integration depth depends on adapters, and the MVP targets GitHub, GitLab, Jenkins, GitHub Actions and Slack/Teams notifications.

### 6. Weak Evidence and Poor Reproducibility

- **Symptom:** Defect reports say "it failed in CI" without inputs, environment, commit or tool version.
- **Impact:** Developers cannot reproduce issues, defects bounce between teams, and some are closed as "cannot reproduce" while still present.
- **Proposed response:** "No evidence, no defect." Each finding links to content-addressed evidence (SHA-256) in an immutable Evidence Store (FR-032), including inputs, outputs, logs, environment, commit and tool version. Reproduction runs execute in fresh sandboxes (FR-035), and Confirmed requires DCS ≥ 80 with reproduction (for example, reproduced in at least 2 of 3 runs).
- **Will not solve:** Defects that depend on production data, scale or third-party behavior may not reproduce in an ephemeral sandbox. These will remain Probable or Candidate, and reports will state why.

### 7. Performance Testing Happens Late

- **Symptom:** Load tests run once before a major release, on shared environments, often by a single specialist.
- **Impact:** Regressions are discovered when they are expensive to fix, and results vary because environments and workloads drift.
- **Proposed response:** Bounded Smoke (5 VUs, 1 min) and Baseline (20 VUs, 5 min) profiles are proposed to run on every job against ephemeral targets (FR-027); Smoke needs no approval, and Baseline needs a QA Lead approval (HA-03). They are compared with a stored baseline (FR-029) and checked by QG-05 (p95 ≤ project threshold, error rate ≤ 1%, p95 regression ≤ 10%). Sample-size warnings flag unreliable percentiles: p95 needs ≥ 400 samples per endpoint. Automatic abort rules protect targets.
- **Will not solve:** Sandbox numbers are relative indicators, not production capacity figures. Stress, Spike and Soak profiles are Future (Phase 4). Capacity planning still needs production-like environments and specialist judgement.

### 8. Test-Suite Effectiveness Is Unknown

- **Symptom:** Line coverage is high, but defects still escape. Tests execute code without asserting on its behavior.
- **Impact:** False confidence. Teams cannot tell whether a green suite means anything.
- **Proposed response:** The Mutation Testing Agent will run mutation tools on changed modules only (max 500 mutants per job). It computes score = killed / (killed + survived) × 100 over valid, completed mutants and explains surviving mutants with suggested assertions (FR-030, FR-031). QG-06 (≥ 60%) is advisory by default.
- **Will not solve:** Mutation score measures one dimension of test strength. Equivalent mutants and tool limits mean the score is an estimate, and running it on whole large codebases is out of scope.

### 9. AI Tools Generate Unverified Tests and Patches

- **Symptom:** AI assistants generate tests that pass trivially, assert the current (buggy) behavior, or patch the symptom instead of the cause.
- **Impact:** Suites grow without becoming stronger, and plausible-looking but wrong fixes reach review fatigued by volume.
- **Proposed response:** Generated tests carry provenance and require human review before promotion (FR-016). Patches are proposed only for Confirmed findings, reviewed by a human (HA-06), then re-checked by the Independent Verification Agent in a fresh sandbox with no access to the Patch Proposal Agent's reasoning (FR-040). The platform never commits, pushes or merges (FR-041). Agent outputs are schema-validated (SEC-015).
- **Will not solve:** Human reviewers can still approve a poor patch. Verification proves only that the re-run checks pass, not that the patch is complete or optimal.

### 10. Running Untrusted Code Is a Security Risk

- **Symptom:** CI runners execute arbitrary repository code, including dependencies and AI-generated tests, often with network access and long-lived credentials.
- **Impact:** Credential theft, lateral movement and supply-chain compromise.
- **Proposed response:** The control plane never executes repository code (SEC-001). Sandbox workers run as non-root with all capabilities dropped, a read-only root filesystem and no Docker socket, under gVisor. Network is off during execution, and cloud metadata and internal networks are blocked. Agents and workers never receive repository or platform credentials. The Secrets Broker issues short-lived scoped tokens to Source Intake and the Target Environment Manager only.
- **Will not solve:** Container-based isolation with gVisor reduces but does not eliminate escape risk. Hostile multi-tenant use needs microVM isolation (Future). Operators remain responsible for host hardening.

### 11. Weak Auditability of QA Decisions

- **Symptom:** Nobody can later say who waived a failing check, why a finding was dismissed, or which commit was actually tested.
- **Impact:** Compliance gaps (a particular concern in regulated domains such as fintech), repeated mistakes and blame-driven post-mortems.
- **Proposed response:** Every approval (HA-01 to HA-12), triage change, gate override (HA-09, reason mandatory) and release decision (HA-10) will be recorded in an append-only, hash-chained audit log (FR-054, SEC-013). It will be linked to the pinned SHA, tool versions and evidence.
- **Will not solve:** An audit trail records decisions. It does not make them correct. Organizational accountability processes remain the customer's responsibility.

## Summary of Proposed Responses

| # | Limitation | Primary mechanism | Key IDs |
|---|---|---|---|
| 1 | Regression load | Change-impact planning, coverage gate | FR-014, QG-04 |
| 2 | Slow feedback | CI triggers, warm pool, live events | FR-052, NFR-002 |
| 3 | Flaky tests | Fresh-worker reruns, Flaky Test Register | FR-018, QG-03 |
| 4 | Scanner noise | Candidate-first triage, scoped suppressions | FR-034, HA-07 |
| 5 | Siloed tools | One job, one finding list, standard exports | FR-044, FR-045 |
| 6 | Weak evidence | Content-addressed evidence, DCS, reproduction | FR-032, FR-035 |
| 7 | Late performance | Bounded Smoke/Baseline with comparison | FR-027, QG-05 |
| 8 | Unknown effectiveness | Mutation on changed modules | FR-030, QG-06 |
| 9 | Unverified AI output | Review gates, fresh-sandbox verification | FR-040, HA-06 |
| 10 | Untrusted code risk | Isolated, network-off sandboxes | SEC-001, SEC-004 |
| 11 | Auditability | Hash-chained audit log | FR-054, SEC-013 |

## What the Platform Does Not Claim

The platform does not claim to find all defects, prove security, replace QA professionals or make release decisions. It aims to make testing more consistent, evidence more complete and residual risk more visible, so that humans can make better-informed decisions. Limits and residual risks are documented in the [risks, limitations and decisions](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md) document.
