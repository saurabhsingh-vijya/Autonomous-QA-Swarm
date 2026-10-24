# Product Requirements Document

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This Product Requirements Document (PRD) defines what Autonomous QA Swarm is proposed to deliver, for whom, in which phase, and how success will be judged. It summarizes the product at feature level (F-01 to F-15). Detailed behavior is in the [functional requirements document](02-functional-requirements-document.md), and full requirement text is in [functional requirements](../03-requirements/01-functional-requirements.md). Every feature in this PRD is **Proposed**. Items scheduled for Phases 1–3 are **Planned (MVP)**, and later items are **Future**. No item is **Implemented / Verified**, and that label will be applied only after code exists and acceptance tests pass.

## Purpose

The PRD is the agreement between product, engineering, QA and security stakeholders on:

- The problem the platform addresses and the outcomes it targets.
- The boundary between the MVP and later phases.
- The features, their requirement ranges and their phase.
- Dependencies, constraints and open questions that must be resolved before or during build.

## Background

QA in most teams relies on several disconnected tools: test frameworks in CI, separate security scanners, occasional performance tests, and defect trackers filled by hand. Results arrive late, are noisy, and often lack the evidence needed to reproduce a defect. AI assistants now generate tests and patches, but their output is usually unverified, and running untrusted code on build infrastructure is a security risk. The [problem statement](../01-product-vision/02-problem-statement.md) describes eleven specific limitations.

Autonomous QA Swarm is proposed as an open-source, self-hostable platform in which specialized AI agents, coordinated by a deterministic workflow engine, plan and run tests against a pinned commit inside isolated sandboxes. The platform will correlate evidence, propose fixes for human review and independently verify them. Two principles govern every feature:

- **"Agents propose, deterministic services dispose, humans approve."**
- **"No evidence, no defect."**

## Goals and Non-Goals

### Goals

| Objective | Goal statement |
|---|---|
| OBJ-01 | Report findings that are evidence-backed, deduplicated and scored by a deterministic Defect Confidence Score (DCS) |
| OBJ-02 | Provide fast, consistent feedback on every change, including from CI |
| OBJ-03 | Execute repository and generated code only in isolated, network-off sandboxes |
| OBJ-04 | Make test effectiveness (mutation score, plan coverage) and residual risk visible |
| OBJ-05 | Keep generated tests and patches under human review, with independent verification |
| OBJ-06 | Remain open-source, self-hostable, portable and fully auditable |

Objectives and metrics are defined in [vision, objectives and metrics](../01-product-vision/03-vision-objectives-and-metrics.md).

### Non-Goals

- Guaranteeing defect-free software or complete security coverage.
- Making release decisions. The platform recommends and a human decides (HA-10).
- Committing, pushing or merging code (FR-041). Pull-request export is Future and gated by HA-12.
- Replacing test frameworks, CI servers, issue trackers or dedicated security programs.
- Testing production systems. Active security and load testing target only authorized ephemeral or non-production environments.
- Mobile and desktop application testing in the MVP.
- Operating as a multi-tenant SaaS in the MVP.

## Target Users

| Persona | Role | Primary need from the platform |
|---|---|---|
| PER-01 Priya — Manual QA Engineer | QA Engineer | Less manual regression, clearer evidence |
| PER-02 Marco — Automation QA Engineer | QA Engineer | Reliable suites, flaky isolation, test-strength data |
| PER-03 Aisha — QA Lead | QA Lead | Gates, approvals and release readiness |
| PER-04 Daniel — Developer | Developer | Fast PR feedback, reproducible defects, patch review |
| PER-05 Sofia — Application Security Engineer | Security Reviewer | Triaged, authorized, bounded security testing |
| PER-06 Kenji — Performance Test Engineer | QA Engineer | Early, bounded, comparable performance data |

The Engineering Manager is a secondary stakeholder with Viewer access. Full personas and journeys are in [personas and user journeys](../01-product-vision/04-personas-and-user-journeys.md).

## Scope

### MVP Scope (Planned (MVP), Phases 1–3)

- Single-organization, self-hosted deployment on a single Linux host (Docker Compose) or Kubernetes.
- GitHub and GitLab repositories, public and private through read-only app tokens held as credential references.
- Python and JavaScript/TypeScript repositories.
- Execution of existing suites (pytest, Jest/Vitest, Playwright) in sandbox workers, with flaky detection.
- Generated candidate tests with provenance. These require human review before promotion or execution in CI.
- Schema-driven API testing (conformance, negative, boundary, property-based, authentication and object-level authorization) against ephemeral targets.
- SAST, dependency scanning and secret detection. IaC/config scanning follows in Phase 3.
- Smoke and Baseline performance profiles with baseline comparison.
- Mutation testing on changed modules, with surviving-mutant analysis.
- Evidence capture, DCS, deduplication, reproduction, conflict reconciliation and triage.
- Patch proposal, human review and independent verification.
- Quality gates QG-01 to QG-08, release-readiness recommendation and human decision record.
- Reports in JSON, HTML and PDF, and exports in SARIF and JUnit XML.
- CI triggers and notifications (GitHub Actions, Jenkins, GitLab, Slack/Teams, webhooks, email).
- Model Gateway supporting hosted or local models.
- Append-only, hash-chained audit trail.

### Future Scope (Phase 4+)

- DAST against registered external non-production targets (FR-026).
- Load, Stress, Spike and Soak performance profiles (FR-028).
- Firecracker microVM or Kata Containers isolation for hostile-code tenancy.
- Multi-tenant SaaS operation.
- Exporting verified patches or generated tests as pull requests (HA-12).
- Additional languages, for example Java (the sample `northwind/ledger-service` is shown as "Unsupported language (Phase 4)").
- A plugin SDK and a marketplace of agent skills (Phase 5).
- Temporal as a workflow backend, if the PostgreSQL-backed queue proves insufficient.

## Feature Summary

| ID | Feature | FR range | Lead agents or services | Phase | Status |
|---|---|---|---|---|---|
| F-01 | Repository & Source Intake | FR-001–FR-004 | Source Intake Service | 1–2 | Planned (MVP) |
| F-02 | QA Job Configuration & Launch | FR-005–FR-007, FR-050 | API Gateway, Policy Engine | 1–2 | Planned (MVP) |
| F-03 | Planning & Orchestration | FR-008–FR-012 | AG-01, Workflow Engine | 1–2 | Planned (MVP) |
| F-04 | Requirements & Change Analysis | FR-013, FR-014 | AG-02 | 2 | Planned (MVP) |
| F-05 | Functional Testing | FR-015–FR-018 | AG-03, Execution Service | 1–2 | Planned (MVP) |
| F-06 | API Testing | FR-019–FR-021 | AG-04 | 2 | Planned (MVP) |
| F-07 | Security Testing | FR-022–FR-026 | AG-05 | 2–4 | Planned (MVP); FR-026 Future |
| F-08 | Performance Testing | FR-027–FR-029 | AG-06 | 3–4 | Planned (MVP); FR-028 Future |
| F-09 | Mutation Testing | FR-030, FR-031 | AG-07 | 3 | Planned (MVP) |
| F-10 | Evidence & Defect Analysis | FR-032–FR-037 | AG-08, Evidence Store | 1–2 | Planned (MVP) |
| F-11 | Patch Proposal & Independent Verification | FR-038–FR-041 | AG-09, AG-10 | 1–3 | Planned (MVP) |
| F-12 | Quality Gates & Release Readiness | FR-042, FR-043, FR-046 | AG-11 | 2 | Planned (MVP) |
| F-13 | Reporting & History | FR-044, FR-045, FR-047–FR-049 | AG-11, Web UI | 1–2 | Planned (MVP) |
| F-14 | Administration, Settings & Integrations | FR-051–FR-053 | Policy Engine, Model Gateway | 1–3 | Planned (MVP) |
| F-15 | Audit & Governance | FR-054 | Audit Log | 1 | Planned (MVP) |

Priorities follow the FR catalogue. P0 items in each feature define the minimum for its phase, P1 items are expected in the phase, and P2 items may slip to a later phase without breaking the MVP.

### Feature Highlights

- **F-01** pins every ref to an immutable commit SHA and produces a checksummed snapshot. The control plane never executes repository code (SEC-001).
- **F-02** enforces idempotent job creation. The same `Idempotency-Key` within 24 h returns the original response, and an active duplicate (repository, SHA, profile hash) returns `409` unless a QA Lead sets `force_new=true`.
- **F-03** runs a validated task DAG with 90 s leases, bounded retries (max 2 for infrastructure errors, max 1 corrective retry for invalid LLM output) and a 4 h default job limit.
- **F-05** re-runs each failed test up to 2 times in fresh workers. A pass on rerun is classified `flaky` and recorded in the Flaky Test Register.
- **F-07** offers Quick, Standard and Deep security profiles. Deep adds DAST, requires HA-02 and HA-05, is bounded to 60 min, and is Future (Phase 4, FR-026) for every target type; the MVP offers Quick and Standard.
- **F-08** caps Smoke at 5 VUs for 1 min and Baseline at 20 VUs for 5 min, with automatic abort rules and sample-size warnings.
- **F-10** computes the DCS from five components. Confirmed requires DCS ≥ 80 plus reproduction. Conflicts are reconciled by precedence or flagged **Disputed**.
- **F-11** separates proposal (AG-09) from verification (AG-10) and runs verification in a fresh sandbox with no access to the proposer's reasoning.
- **F-12** applies the verdict logic: any blocking gate failed gives `NOT_READY`; else any gate inconclusive gives `INCONCLUSIVE`; else an advisory failure or open accepted risk gives `READY_WITH_RISKS`; else `READY`.

## Release Plan by Phase

Quarters are indicative only. Exit criteria are proposed and will be confirmed in Phase 0. The [roadmap](../12-risks-and-roadmap/02-roadmap.md) holds the detailed plan.

### Phase 0 — Concept & Validation (Indicative Q4 2026)

- **Content:** This documentation package, persona validation interviews, a sandbox isolation spike, metric baselining plan, and resolution of key open decisions including DEC-01 (licence).
- **Exit criteria:** Reviewed documentation set. Sandbox spike shows network-off execution and cleanup within 60 s on a sample repository. MVP backlog agreed.

### Phase 1 — Foundations

- **Content:** F-01 (FR-001, FR-002, FR-004), F-02 (FR-005–FR-007), F-03 (FR-008, FR-010–FR-012), F-05 (FR-015, FR-017, FR-018), F-10 evidence capture (FR-032), F-11 no-auto-commit guarantee (FR-041), F-13 basic report and history (FR-044, FR-047), F-14 execution limits (FR-051), F-15 audit (FR-054).
- **Exit criteria:** Existing suites run end to end on sample Python and TypeScript repositories with evidence and a basic report. MET-02, MET-03, MET-09 and MET-10 are measurable.

### Phase 2 — Analysis & Security Baseline

- **Content:** Private repositories (FR-003), plan approval (FR-009), requirements and change analysis (F-04), generated tests (FR-016), API testing (F-06), SAST, SCA and secrets (FR-022–FR-024), DCS, dedup, reproduction, reconciliation and triage (FR-033–FR-037), quality gates and readiness (F-12), exports, dashboard and workflow visualization (FR-045, FR-048, FR-049), target registration (FR-050), Model Gateway (FR-053).
- **Exit criteria:** Gates QG-01 to QG-04 and QG-08 evaluate on sample jobs. MET-01 and MET-05 are measurable.

### Phase 3 — MVP 1.0

- **Content:** IaC scanning (FR-025), Smoke and Baseline performance with comparison (FR-027, FR-029), mutation testing (F-09), patch proposal, review and verification (FR-038–FR-040), CI and notification integrations (FR-052), and hardening against the [non-functional requirements](../03-requirements/02-non-functional-requirements.md).
- **Exit criteria:** All P0 and P1 MVP requirements meet their acceptance criteria. Security review of the sandbox and policy design is complete. MET-06 to MET-08 are measurable.

### Phase 4 — Scale & Depth (Future)

DAST (FR-026), Load, Stress, Spike and Soak (FR-028), microVM isolation, multi-tenancy, additional languages and PR export (HA-12).

### Phase 5 — Ecosystem (Future)

Plugin SDK, more languages, and a marketplace of agent skills built on the versioned adapter interfaces (NFR-017).

## Dependencies

Formal dependency IDs are maintained in [scope, assumptions and constraints](../03-requirements/03-scope-assumptions-and-constraints.md). At product level:

- **Open-source components:** PostgreSQL 16+, an S3-compatible object store, Keycloak (OIDC), OpenBao or Vault, Open Policy Agent, gVisor, and the test, scanner, performance and mutation tools listed in [technology options](../05-architecture/05-technology-options.md). Licences must be re-verified at adoption.
- **LLM access:** Either a hosted provider (paid, operator's cost) or local open-weight models via Ollama or vLLM (compute cost). The platform must remain functional for deterministic stages when the model provider is unavailable.
- **Git providers:** GitHub and GitLab APIs and app-token models for read-only access.
- **CI systems:** GitHub Actions, Jenkins and GitLab CI for triggers and result consumption.
- **Customer environments:** Ephemeral targets must be startable in-sandbox, or the customer must provide authorized non-production targets (HA-01).
- **Human reviewers:** QA Lead, Security Reviewer and code owners must be available for approvals. Approval latency directly affects job duration.

## Success Metrics

| Metric | Measures | Linked objective | First measurable |
|---|---|---|---|
| MET-01 | Confirmed-finding precision | OBJ-01 | Phase 2 |
| MET-02 | Evidence completeness | OBJ-01, OBJ-06 | Phase 1 |
| MET-03 | Time to first result | OBJ-02 | Phase 1 |
| MET-04 | Flaky classification agreement | OBJ-02 | Phase 1 |
| MET-05 | Security triage reduction | OBJ-04 | Phase 2 |
| MET-06 | Patch first-pass verification rate | OBJ-05 | Phase 3 |
| MET-07 | Patch review usefulness | OBJ-05 | Phase 3 |
| MET-08 | Mutation-score uplift | OBJ-04 | Phase 3 |
| MET-09 | Sandbox safety and cleanup | OBJ-03 | Phase 1 |
| MET-10 | Time to first job | OBJ-06 | Phase 1 |

All targets are proposed and must be validated against baselines. Definitions and targets are in [vision, objectives and metrics](../01-product-vision/03-vision-objectives-and-metrics.md).

## Constraints

- **Open-source operability:** The full pipeline must run with OSS components only (NFR-018). Paid services are optional adapters.
- **Licensing:** The project licence is proposed as Apache-2.0 (DEC-01 open). AGPL-3.0 components (k6, Grafana, Loki) run as separate processes. Vault's BUSL-1.1 licence is not OSI open source, so OpenBao is the default proposal.
- **Security posture:** The control plane never executes repository code. Workers run with network off during execution. Secrets never reach agents or LLMs (SEC-007). Active testing only targets authorized environments (SEC-016).
- **Resource defaults:** Sandbox workers default to 2 vCPU, 4 GiB RAM and 30 min per task (max 2 h). Jobs default to 4 h (max 12 h). Mutation is capped at 500 mutants per job.
- **Human authority:** Twelve approvals (HA-01 to HA-12) are mandatory for their actions and cannot be bypassed by configuration.
- **Language support:** Python and JavaScript/TypeScript only in the MVP.
- **Deployment:** Single-organization self-hosted only in the MVP.

## Open Questions

Open questions are tracked in the decisions log in [risks, limitations and decisions](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md). DEC-01 (project licence: Apache-2.0 proposed) is the first. Other product-level questions for that log include:

- Whether the plan approval gate (HA-05) should be on by default for all profiles, or only for Deep security and Stress/Soak performance as proposed.
- Whether the default local model is capable enough for the Requirements Analysis and Patch Proposal agents, or whether a hosted model should be recommended for those agents.
- Whether QG-06 (mutation score ≥ 60%) should become blocking for some project classes after Phase 3 data is available.
- How long the PostgreSQL-backed task queue can serve before Temporal is warranted, and what throughput signal should trigger that review.
- Whether Java support should move ahead of other Phase 4 items, given sample demand such as `northwind/ledger-service`.
- What minimum evidence an external target's authorization attestation (HA-01) should require.
