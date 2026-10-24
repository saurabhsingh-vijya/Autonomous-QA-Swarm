# Vision, Objectives and Metrics

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document sets out the product vision, the design principles that constrain every later decision, six product objectives (OBJ-01 to OBJ-06) and ten success metrics (MET-01 to MET-10). All targets below are **proposed targets to validate**. They are hypotheses for Phase 0 and the MVP phases, not results. No measurement has been taken, because nothing has been built.

## Vision Statement

Every code change should get a consistent, evidence-backed quality assessment that a human can trust, understand and act on. Autonomous QA Swarm is proposed as an open-source, self-hostable platform in which specialized AI agents plan and analyze testing work, while deterministic services execute it in isolated sandboxes. Humans keep authority over targets, patches and release decisions. The aim is not to remove people from QA. It is to remove repetitive coordination, noise and guesswork so that QA engineers, developers and security reviewers spend their time on judgement.

## Design Principles

1. **Agents propose, deterministic services dispose, humans approve.** Agents emit typed proposals only. The Policy Engine validates them deny-by-default. The Execution Service runs them in sandbox workers. Defined actions (HA-01 to HA-12) require a named human.
2. **No evidence, no defect.** A finding is Confirmed only with a Defect Confidence Score (DCS) ≥ 80 and successful reproduction. LLM judgement can contribute only to the "Independent corroboration" component (15 of 100 points).
3. **Pinned and reproducible.** Every job runs against an immutable commit SHA and a checksummed source snapshot, with tool versions recorded. Re-runs with the same inputs should yield the same deterministic results, except for documented nondeterminism (NFR-007).
4. **Untrusted by default.** Repository code, dependencies, generated tests and repository text (including text aimed at prompt injection) are treated as hostile. Sandboxes run with network off during execution. Agents and workers never hold platform credentials.
5. **Bounded and authorized.** Security and performance testing run only against authorized targets, within caps, abort rules and non-destructive defaults.
6. **Aggregate scores never hide blockers.** An open Confirmed Critical finding, or an open Confirmed High security finding without accepted risk, forces `NOT_READY` regardless of other scores.
7. **Honest about limits.** Reports state coverage gaps, skipped and inconclusive work, and residual risk. No profile claims comprehensive security coverage.
8. **Open and portable.** The full pipeline must run with open-source components only (NFR-018). Paid services are optional adapters.

## Product Objectives

| ID | Objective | Why it matters | Primary metrics |
|---|---|---|---|
| OBJ-01 | Deliver trustworthy, evidence-backed findings | Low trust in results is the main reason QA output is ignored | MET-01, MET-02 |
| OBJ-02 | Provide fast, consistent feedback on every change | Late feedback multiplies fix cost | MET-03, MET-04 |
| OBJ-03 | Execute untrusted code safely | Running repository and AI-generated code is the platform's largest inherent risk | MET-09 |
| OBJ-04 | Make test effectiveness and residual risk visible | Green suites can hide weak assertions and untested paths | MET-05, MET-08 |
| OBJ-05 | Keep AI assistance for tests and fixes under human control | Unverified generated tests and patches add risk instead of reducing it | MET-06, MET-07 |
| OBJ-06 | Be open, self-hostable, adoptable and auditable | Teams in regulated domains need to own their data and decision trail | MET-10, MET-02 |

### OBJ-01 — Trustworthy, Evidence-Backed Findings

Every reported finding links to content-addressed evidence, the tool and version that produced it, and its decision trail. Confirmed findings should rarely be overturned by human triage. Deduplication and conflict reconciliation (the **Disputed** flag) prevent double counting and silent auto-dismissal.

### OBJ-02 — Fast, Consistent Feedback

Jobs triggered from CI on a pull-request ref should start quickly and report early stages progressively. The same profile on the same commit should produce a comparable result, and flaky behavior should be separated from real failures.

### OBJ-03 — Safe Execution of Untrusted Code

No repository code runs on the control plane. Sandboxes enforce the default limits (2 vCPU, 4 GiB RAM, 512 PIDs, network off during execution), and workers are destroyed within 60 s of a terminal task state. Safety is measured by the absence of policy violations reaching the host or internal networks, and by cleanup completeness.

### OBJ-04 — Visible Effectiveness and Residual Risk

Mutation testing on changed modules, plan-execution coverage (QG-04) and coverage and residual-risk reporting (FR-046) show what the suite actually checks and what was not tested.

### OBJ-05 — Human-Controlled AI Assistance

Generated tests require review before promotion. Patches require human approval (HA-06) and independent verification in a fresh sandbox before they count toward QG-07. The platform never commits, pushes or merges.

### OBJ-06 — Open, Adoptable, Auditable

A new user should be able to create a first job without reading documentation. Operators should be able to run the platform on a single Linux host or on Kubernetes. Every approval, override and release decision should be reconstructable from the hash-chained audit log.

## Success Metrics

The metrics below are proposed. Each will be baselined during the phase in which it first becomes measurable, and its target confirmed or revised from that baseline. Measurement uses platform data (Metadata DB, Audit Log, Observability Stack). No metric depends on self-reported user claims alone.

### Quality and Trust Metrics

| ID | Metric | Definition | Proposed target | Measurement method | Phase |
|---|---|---|---|---|---|
| MET-01 | Confirmed-finding precision | Share of Confirmed findings not later marked false positive or not reproducible by human triage | ≥ 95% over a rolling 30 days (mirrors NFR-010) | Finding status transitions and triage Approval records | Phase 2 |
| MET-02 | Evidence completeness | Share of reported findings with evidence, tool/version, commit and decision trail all linked | 100% (mirrors NFR-009) | Automated check at report generation | Phase 1 |
| MET-03 | Time to first result | Median time from job creation to the first test execution result on a CI-triggered job | ≤ 10 min on reference sample repositories with a warm pool | Job and TestExecution timestamps | Phase 1 |
| MET-04 | Flaky classification agreement | Share of tests auto-classified `flaky` that a QA Lead acknowledges as flaky | ≥ 90% | Flaky Test Register acknowledgements | Phase 1 |
| MET-05 | Security triage reduction | Reduction in items needing human security triage per job, compared with raw scanner alert count, after dedup and candidate grouping | ≥ 40% reduction, without any later-confirmed issue lost from the list | Raw alert counts vs. Finding records per job | Phase 2 |

### Assistance, Safety and Adoption Metrics

| ID | Metric | Definition | Proposed target | Measurement method | Phase |
|---|---|---|---|---|---|
| MET-06 | Patch first-pass verification rate | Share of patches approved for verification that end `verified` on the first VerificationRun | ≥ 60% | Patch and VerificationRun status | Phase 3 |
| MET-07 | Patch review usefulness | Share of proposed patches that reviewers approve for verification rather than reject | ≥ 40% | Patch review Approval records | Phase 3 |
| MET-08 | Mutation-score uplift | Median change in mutation score on changed modules after reviewed suggested tests are added | +10 percentage points | Paired MutationRun results per project | Phase 3 |
| MET-09 | Sandbox safety and cleanup | Policy violations reaching host or blocked networks, plus share of workers destroyed within 60 s of a terminal state | 0 violations; 100% cleanup (mirrors NFR-008) | Worker runtime alerts, egress logs, orphan reaper reports | Phase 1 |
| MET-10 | Time to first job | Time for a new user to create a first job without documentation | ≤ 10 min for at least 80% of usability-test participants (mirrors NFR-012) | Moderated usability sessions on the Web UI | Phase 1 |

### Interpreting the Targets

- Targets apply to the reference deployment and sample repositories first. Production use on customer repositories may justify different values, recorded per project.
- MET-06 and MET-07 are deliberately modest. A rejected patch is an acceptable outcome. A patch that is approved but fails verification is also acceptable, as long as the failure is caught before release.
- MET-05 is paired with a "no loss" condition so that the platform cannot improve the metric by hiding alerts.
- A metric that misses its target in its first phase triggers a design review, recorded in the [decisions log](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md). It does not trigger a silent change of the target.

## Differentiation

The comparisons below are about approach, not product quality. They describe categories, not specific vendors. Many teams will run Autonomous QA Swarm alongside tools in each category rather than instead of them.

### Versus Classic Test Automation Frameworks

Frameworks such as pytest, Jest/Vitest, Playwright and JUnit are excellent at defining and running tests, and the platform depends on them. It does not replace them. The proposed additions are orchestration across test types against one pinned commit, sandboxed execution of untrusted code, flaky-test handling with fresh-worker reruns, evidence correlation across tools and gate-based release recommendations. A team with a mature framework setup still has to write and maintain its tests. The platform adds analysis and coordination around them.

### Versus AI Test-Generation Tools

AI test generators can produce many tests quickly. The platform's proposed difference is the trust chain around generated output: provenance on every generated test, mandatory human review before promotion, execution only in network-off sandboxes, and mutation testing to check whether new tests actually strengthen the suite. The platform will itself use LLMs and inherit their limitations, including incorrect assertions, hallucinated APIs and sensitivity to prompt injection. It mitigates rather than removes these limitations.

### Versus Commercial SAST/DAST Platforms

Dedicated security platforms typically offer deeper rule sets, curated vulnerability research and vendor support. The platform proposes to orchestrate open-source scanners (Semgrep CE, Bandit, Gitleaks, OSV-Scanner, Trivy, Checkov, OWASP ZAP), correlate their output with functional and API evidence, and require reachability evidence before promotion. It does not claim greater detection coverage than any security product, and no profile claims comprehensive security coverage. SARIF export allows results to feed into existing security tooling.

### Versus CI Quality Gates

CI quality gates commonly evaluate thresholds such as coverage percentage or "build green". The platform's proposed gates (QG-01 to QG-08) separate failed from inconclusive outcomes. A verdict of `INCONCLUSIVE` is distinct from `NOT_READY`, so missing evidence is never reported as a pass. Blockers are never averaged away, and the platform recommends while a named human decides (HA-10). The platform integrates with CI (GitHub Actions, Jenkins, GitLab) rather than replacing it.

## Relationship to Other Documents

Requirements behind these objectives are in the [product requirements document](../02-prd-frd/01-product-requirements-document.md) and [functional requirements](../03-requirements/01-functional-requirements.md). Gate logic is in [quality gates and release readiness](../11-quality-gates-and-reporting/02-quality-gates-and-release-readiness.md). The personas who benefit from each objective are described in [personas and user journeys](04-personas-and-user-journeys.md).
