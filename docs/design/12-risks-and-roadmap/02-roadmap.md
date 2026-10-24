# Roadmap

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This roadmap sets out how Autonomous QA Swarm is proposed to move from this concept package to an MVP and beyond. It is organized in six phases, Phase 0 to Phase 5. The MVP consists of Phases 1 to 3; items in those phases carry the status **Planned (MVP)**, and items in Phases 4 and 5 carry the status **Future**. No item has the status **Implemented / Verified**. All timing is **indicative** and expressed only in quarters; it depends on contributor availability and on the results of each phase's exit review.

## Planning principles

- **Safety before capability.** Sandbox isolation, policy enforcement and authorization controls are built and tested before the platform executes untrusted code or touches any target.
- **Deterministic core first.** Execution, evidence capture and reporting work without any LLM before agents are added on top, so that agent quality can be measured against a deterministic baseline.
- **Measurable exits.** A phase ends only when its exit criteria are met and reviewed against the [risk register](01-risks-limitations-and-decisions.md); dates move, criteria do not.
- **OSS-only path.** Every phase must remain runnable end-to-end with free and open-source components only (NFR-018).

## Phase overview

| Phase | Name | Focus | Status label | Indicative timing |
|---|---|---|---|---|
| Phase 0 | Concept & Validation | This documentation package, feedback, licence and governance decisions | Proposed | Q4 2026 (indicative) |
| Phase 1 | Foundations | Intake, sandbox, existing-suite execution, evidence store, basic report | Planned (MVP) | Q1–Q2 2027 (indicative) |
| Phase 2 | Analysis & Security Baseline | Requirements analysis, API testing, SAST/SCA/secrets, evidence correlation, quality gates | Planned (MVP) | Q2–Q3 2027 (indicative) |
| Phase 3 | MVP 1.0 | Performance Smoke/Baseline, mutation, patch proposal + verification, CI integration, hardening | Planned (MVP) | Q3–Q4 2027 (indicative) |
| Phase 4 | Scale & Depth | DAST, advanced performance, microVMs, multi-tenancy | Future | 2028 (indicative) |
| Phase 5 | Ecosystem | Plugin SDK, more languages, marketplace of agent skills | Future | After Phase 4 (indicative) |

Phase timings overlap because late hardening of one phase can proceed while the next begins; a phase's exit review still happens before the next phase's features are released.

## Phase 0 — Concept & Validation

**Goal.** Validate the problem, the architecture and the safety model with prospective users and contributors before writing platform code.

**Scope.**
- This documentation set: vision, requirements, architecture, agent design, data model, API contracts, testing workflows, threat model, quality gates and this roadmap.
- Walkthroughs of the UI mockups for SCR-01 to SCR-15 with the personas PER-01 to PER-06.
- Closing DEC-01 (project licence, Apache-2.0 proposed) and DEC-10 (contribution and governance model).
- A threat-model review of the sandbox and policy design by people outside the core group.

**Exit criteria.**
- At least 5 external reviewers (QA, developer and security practitioners) have reviewed the package, and all blocking comments are resolved or recorded as decisions.
- DEC-01 and DEC-10 are closed with a written rationale.
- Every P0 functional requirement has three acceptance criteria and is assigned to Phase 1, 2 or 3.
- A public repository with licence, code of conduct, contribution guide and security disclosure policy exists.

**Key risks.** RSK-14 (maintainer bandwidth), RSK-17 (scope creep).

## Phase 1 — Foundations

**Goal.** Run existing test suites of a pinned commit safely inside disposable sandboxes and report the results with captured evidence, without relying on LLM agents for correctness.

**Scope.**
- Features F-01 Repository & Source Intake, F-03 Planning & Orchestration, F-05 Functional Testing (existing suites), F-15 Audit & Governance, plus the basic parts of F-02, F-10, F-11, F-13 and F-14.
- Functional requirements: FR-001, FR-002, FR-004, FR-005, FR-006, FR-007, FR-008, FR-010, FR-011, FR-012, FR-015, FR-017, FR-018, FR-032, FR-041, FR-044, FR-047, FR-051, FR-054.
- Sandbox baseline with rootless containers and gVisor, network off during execution, dependency-fetch phase through the allow-listed proxy.
- Content-addressed Evidence Store and append-only, hash-chained Audit Log.
- Basic JSON, HTML and PDF report.
- Orchestrator Agent with a deterministic planner; LLM-assisted planning behind a feature flag.

**Exit criteria.**
- Existing pytest, Jest/Vitest and Playwright suites execute for the sample repositories `northwind/payments-api` and `northwind/web-portal` (sample) with results matching a local run in at least 95% of test outcomes, with every difference explained.
- A sandbox escape and egress test suite (blocked metadata IPs, blocked RFC1918 ranges, no Docker socket, read-only root FS) passes 100% of cases on the reference deployment.
- 100% of workers destroyed within 60 seconds of terminal task state across 500 consecutive tasks (NFR-008).
- Job start latency at or below 60 seconds with a warm pool (NFR-002) and event delivery at or below 2 seconds (NFR-003) on the reference deployment.
- Duplicate job creation with the same `Idempotency-Key` returns the original response in 100% of test cases.
- DEC-03, DEC-04, DEC-05 and DEC-06 closed.

**Key risks.** RSK-06 (sandbox escape), RSK-11 (supply chain), RSK-19 (flaky infrastructure).

## Phase 2 — Analysis & Security Baseline

**Goal.** Add the analysis layer: requirement-driven scenarios, API testing, static security scanning, evidence correlation with confidence scoring, and quality gates with a release-readiness recommendation.

**Scope.**
- Features F-04 Requirements & Change Analysis, F-06 API Testing, F-07 Security Testing (Quick and Standard static parts), F-10 Evidence & Defect Analysis, F-12 Quality Gates & Release Readiness, and the remainder of F-02 and F-13 for this phase.
- Functional requirements: FR-003, FR-009, FR-013, FR-014, FR-016, FR-019, FR-020, FR-021, FR-022, FR-023, FR-024, FR-033, FR-034, FR-035, FR-036, FR-037, FR-042, FR-043, FR-045, FR-046, FR-048, FR-049, FR-050, FR-053.
- Agents AG-02, AG-04, AG-05, AG-08, candidate test generation by AG-03 (with human review before promotion), and the deterministic gate evaluator of AG-11.
- Model Gateway with hosted and local model options, token budgets and output schema validation.
- SARIF and JUnit XML exports.

**Exit criteria.**
- On a seeded benchmark of at least 50 known defects across the sample repositories, the false-positive rate of Confirmed findings is at or below 5% (NFR-010 measured on the benchmark).
- 100% of reported findings link to evidence, tool version and decision trail (NFR-009).
- Deduplication merges at least 90% of known duplicate signals in the benchmark and wrongly merges fewer than 2% of distinct defects.
- Quality-gate verdicts match a hand-computed expected verdict on 100% of at least 30 scripted gate scenarios, including every gate result state.
- No secret from a seeded secret set appears in any evidence, log, prompt or report (SEC-008).
- DEC-07 closed.

**Key risks.** RSK-01 (hallucination), RSK-02 (false positives), RSK-07 (prompt injection), RSK-10 (secret leakage), RSK-12 (LLM cost).

## Phase 3 — MVP 1.0

**Goal.** Complete the MVP with bounded performance testing, mutation testing, patch proposal with independent verification, CI integration and hardening for a first stable release.

**Scope.**
- Features F-08 Performance Testing (Smoke and Baseline), F-09 Mutation Testing, F-11 Patch Proposal & Independent Verification, F-14 integrations, and IaC/configuration scanning within F-07.
- Functional requirements: FR-025, FR-027, FR-029, FR-030, FR-031, FR-038, FR-039, FR-040, FR-052.
- Agents AG-06, AG-07, AG-09, AG-10 and the narrative part of AG-11.
- Integrations with GitHub, GitLab, Jenkins, GitHub Actions and Slack/Teams notifications.
- Hardening: performance tuning, documentation, upgrade path, backup and restore drill, external security review.

**Exit criteria.**
- All P0 and P1 functional requirements in Phases 1 to 3 pass their acceptance criteria; at that point those items may move to **Implemented / Verified**.
- Performance Smoke and Baseline runs respect workload and duration caps and trigger every automatic abort rule in fault-injection tests.
- Mutation scores computed by the platform match the underlying tools' own reports on the sample repositories.
- Independent verification runs in a fresh sandbox with no access to Patch Proposal Agent reasoning, confirmed by an audit of inputs.
- 10 concurrent jobs complete on the reference deployment of 8 workers × 2 vCPU (NFR-004).
- A restore drill meets RPO ≤ 15 minutes and RTO ≤ 4 hours (NFR-006).
- An external security review finds no unresolved Critical or High issues in the platform.
- DEC-02 and DEC-08 closed.

**Key risks.** RSK-05 (patch regressions), RSK-09 (target harm), RSK-13 (compute cost), RSK-17 (scope creep), RSK-20 (queue scalability).

## MVP boundary

The MVP (Phases 1 to 3) is a single-organization self-hosted deployment with:

- GitHub and GitLab repositories, public and private via read-only app tokens.
- Python and JavaScript/TypeScript first.
- Existing-suite execution; generated tests require human review before execution in CI.
- SAST, SCA and secret detection.
- Schema-driven API testing against ephemeral targets.
- Smoke and Baseline performance profiles only.
- Mutation testing on changed modules.
- Patch proposal and independent verification.
- Quality gates.
- JSON, HTML, SARIF and JUnit reports.

Out of the MVP: DAST in the Deep security profile (Phase 4), Stress, Soak and Spike profiles, multi-tenant SaaS, microVM isolation and automatic pull-request creation. Mobile and desktop application testing is out of scope for the current plan and is not scheduled in any phase.

## Phase 4 — Scale & Depth

**Goal.** Extend testing depth and deployment scale for organizations that need stronger isolation or heavier testing.

**Scope.**
- FR-026 DAST against authorized targets (Deep security profile with OWASP ZAP, HA-02 and HA-05).
- FR-028 Load, Stress, Spike and Soak profiles with approvals and abort rules.
- Firecracker microVMs (or Kata Containers, DEC-09) for hostile-code tenancy.
- Multi-tenancy with organization isolation hardened beyond row-level security.
- Java support (the sample `northwind/ledger-service` currently shows "Unsupported language (Phase 4)").
- HA-12 pull-request export of verified patches or generated tests.

**Exit criteria.**
- DAST runs never exceed the 60-minute bound and only run against targets with a valid HA-01 attestation in 100% of policy tests.
- Advanced performance profiles abort correctly in fault-injection tests for every abort rule.
- MicroVM isolation passes the Phase 1 escape suite plus kernel-level isolation tests.
- Cross-tenant access tests show no data leakage across organizations.

**Key risks.** RSK-08 (legal misuse), RSK-09 (target harm), RSK-06 (sandbox escape in multi-tenant setting).

## Phase 5 — Ecosystem

**Goal.** Let the community extend the platform without changing its core.

**Scope.**
- Plugin SDK for agents, tool adapters and report formats, built on versioned adapter interfaces (NFR-017).
- More languages through community adapters.
- A marketplace of agent skills with provenance, signing and review requirements.

**Exit criteria.**
- At least 3 adapters maintained outside the core team pass the conformance suite.
- Every published skill is signed and has a declared permission set validated by the Policy Engine.

**Key risks.** RSK-14 (maintainer bandwidth), RSK-11 (supply chain through plugins), RSK-15 (licence changes).

## Dependencies between phases

- Phase 2 evidence correlation depends on the Phase 1 Evidence Store and environment manifest.
- Phase 2 quality gates depend on Phase 1 test result taxonomy and flaky handling.
- Phase 3 patch verification depends on Phase 2 findings reaching Confirmed through reproduction.
- Phase 4 DAST depends on Phase 2 target registration and authorization (FR-050).

## What would change the plan

The plan is expected to change. The following signals would trigger a re-plan at the next phase review:

- **Trust metrics miss targets.** If the Confirmed false-positive rate stays above 5% in Phase 2, Phase 3 scope moves to evidence quality before new testing types.
- **Sandbox weakness found.** A credible escape path in gVisor-based isolation would pull microVM work from Phase 4 into Phase 3 and pause untrusted-repository support.
- **Control-plane scaling limits.** If RSK-20 indicators fire in Phase 2, DEC-02 is brought forward and Temporal adoption may enter Phase 3.
- **Contributor capacity.** With fewer active maintainers than expected, Phase 3 is split, with performance and mutation shipped after patch verification.
- **Licence or terms changes.** A licence change in k6, Grafana, Loki or another core dependency, or a model provider terms change, would trigger adapter replacement work ahead of new features.
- **User feedback.** If walkthroughs show that teams most need a different language or CI system, language and integration priorities are reordered within the MVP boundary.
- **Regulation.** New rules about automated security testing or AI use in software assurance could add compliance work to the earliest affected phase.

## Related documents

- [Executive summary](../01-product-vision/01-executive-summary.md)
- [Functional requirements](../03-requirements/01-functional-requirements.md)
- [Scope, assumptions and constraints](../03-requirements/03-scope-assumptions-and-constraints.md)
- [Functional requirements document](../02-prd-frd/02-functional-requirements-document.md)
