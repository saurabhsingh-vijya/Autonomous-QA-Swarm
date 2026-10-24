# Executive Summary

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This summary introduces Autonomous QA Swarm, a proposed open-source, self-hostable quality-assurance platform. It is written for engineering leaders, QA leads, security reviewers and prospective contributors who need a short overview before reading the detailed design. Everything in this documentation set (version 0.1, dated 24 October 2026) is design intent. No code, deployment, user base or benchmark exists yet, and no item carries the status **Implemented / Verified**. That label will only be applied after code exists and its acceptance tests pass.

## What the Platform Is

Autonomous QA Swarm is proposed as a platform in which specialized AI agents, coordinated by a deterministic workflow engine, plan and run tests against a pinned revision of a code repository inside isolated sandboxes. The platform will correlate evidence into findings, propose fixes for human review and independently verify approved fixes in a fresh sandbox.

A user will point the platform at a GitHub or GitLab repository and a ref (branch, tag or pull request). The Source Intake Service will pin that ref to an immutable commit SHA and produce a checksummed, read-only source snapshot. A QA job then moves through 13 stages, from Intake & Pinning through Planning, Environment Preparation, Baseline Run, Functional & API, Security, Performance and Mutation Testing, Evidence Correlation & Triage, Patch Proposal, Independent Verification, Quality Gates & Reporting, and Cleanup & Retention. The outcome is an evidence-backed report with a release-readiness recommendation (`READY`, `READY_WITH_RISKS`, `NOT_READY` or `INCONCLUSIVE`). A named human records the actual release decision.

The project is proposed under the Apache-2.0 licence. That choice is still an open decision (DEC-01). The platform is designed to run end to end on free and open-source components. Hosted LLMs, cloud storage and SaaS CI are optional adapters whose cost falls on the operator.

## The Problem

Teams face growing regression suites, slow feedback, flaky tests that erode trust, noisy security scanners and performance testing that happens too late to influence design. Results are scattered across tools and rarely carry enough evidence to reproduce a defect. New AI tools can generate tests or patches quickly, but their output is often unverified, and running untrusted generated code on build infrastructure creates real security risk. The [problem statement](02-problem-statement.md) describes each limitation in detail.

## The Approach

Two principles shape the design:

- **"Agents propose, deterministic services dispose, humans approve."** Agents never execute code, never hold credentials and never change a repository. They emit typed proposals. The Policy Engine validates each proposal against task contracts, scope, target authorization, resource budgets and network rules, and denies anything not explicitly allowed. The Execution Service then runs approved work in disposable sandbox workers (rootless containers with gVisor in the MVP). Network access is off during execution and permitted only in a separate dependency-fetch phase through an allow-listed proxy.
- **"No evidence, no defect."** A finding cannot be reported as Confirmed without reproducible evidence captured by deterministic tooling. Each finding receives a deterministic Defect Confidence Score (DCS, 0–100). Confirmed requires DCS ≥ 80 and successful reproduction. An LLM agent's opinion alone can never lift a finding to Confirmed.

Twelve human approvals (HA-01 to HA-12) gate actions such as authorizing a target, running active security scans, running performance profiles above Smoke, approving patches for verification and recording release decisions. Every approval, override and agent output will be written to an append-only, hash-chained audit log.

## The Eleven Agents

| ID | Agent | Kind | Role in the job |
|---|---|---|---|
| AG-01 | Orchestrator Agent | Deterministic workflow engine + LLM-assisted planner | Builds the task DAG, schedules, retries, enforces timeouts |
| AG-02 | Requirements Analysis Agent | LLM agent | Turns requirements, stories, OpenAPI specs and diffs into testable scenarios |
| AG-03 | Functional Testing Agent | LLM agent + deterministic runners | Selects and runs unit, integration and E2E tests |
| AG-04 | API Testing Agent | LLM agent + deterministic runners | Schema, auth, negative and property-based API tests |
| AG-05 | Security Testing Agent | LLM agent + deterministic scanners | SAST, SCA, secrets, IaC checks and authorized DAST; triages output |
| AG-06 | Performance Testing Agent | LLM agent + deterministic load tools | Bounded load profiles; compares metrics to thresholds and baseline |
| AG-07 | Mutation Testing Agent | Deterministic tool wrapper + LLM analysis | Mutation score on changed modules; explains surviving mutants |
| AG-08 | Evidence and Defect Analysis Agent | LLM agent + deterministic correlator | Correlates, deduplicates, scores and reproduces findings |
| AG-09 | Patch Proposal Agent | LLM agent | Proposes minimal diffs for Confirmed findings, for human review only |
| AG-10 | Independent Verification Agent | Deterministic service + LLM summary | Re-runs checks on commit + approved patch in a fresh sandbox |
| AG-11 | QA Report Agent | Deterministic aggregator + LLM narrative | Reports, coverage, quality gates, readiness recommendation |

The [agent catalogue](../06-agent-design/01-agent-catalogue.md) gives the full contracts and permissions for each agent.

## MVP Boundary

The MVP is planned to cover Phases 1–3 of the [roadmap](../12-risks-and-roadmap/02-roadmap.md). Its intended scope is:

- Single-organization, self-hosted deployment (Docker Compose or Kubernetes).
- GitHub and GitLab repositories, public and private via read-only app tokens.
- Python and JavaScript/TypeScript as the first supported languages.
- Execution of existing test suites (pytest, Jest/Vitest, Playwright). Generated tests require human review before they can run in CI.
- SAST, dependency scanning and secret detection, plus schema-driven API testing against ephemeral targets.
- Smoke and Baseline performance profiles only, and mutation testing on changed modules.
- Patch proposal with independent verification, quality gates QG-01 to QG-08, and JSON/HTML/SARIF/JUnit reports.

The following are outside the MVP and labelled **Future**: DAST in the Deep security profile (FR-026, Phase 4), Stress/Soak/Spike profiles, multi-tenant SaaS, microVM isolation (Firecracker or Kata Containers) and automatic pull-request creation. Mobile and desktop application testing is explicitly out of scope for the current plan rather than scheduled.

## What Is Explicitly Not Promised

- **No defect-free software.** Gates measure what was tested. Untested behavior, environment differences and tool blind spots leave residual risk, and every report is intended to state that risk.
- **No complete security coverage.** No security profile (Quick, Standard or Deep) claims comprehensive coverage. Scanner alerts start as Candidates and are promoted only with reachability or precondition evidence.
- **No autonomous changes to code.** The platform will never commit, push or merge (FR-041). Exporting a verified patch as a pull request is a Future capability gated by HA-12.
- **No autonomous release decisions.** The platform recommends. A QA Lead decides (HA-10).
- **No unbounded testing.** Performance and security testing are always authorized, bounded by caps and abort rules, and non-destructive by default.

## Key Risks

The [risk register](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md) treats the following as the leading risks:

- **Sandbox escape or misuse** by hostile repository code. Mitigated by layered isolation, network-off execution and blocked metadata and internal networks. Residual risk remains until microVM isolation arrives.
- **Prompt injection** through repository content. All repository content is treated as untrusted data, and agents can only emit schema-validated proposals that the Policy Engine checks.
- **LLM output quality and cost.** Generated tests may be wrong or trivial, and token spend can grow. Mitigated by human review, mutation feedback and per-job budgets.
- **False positives and alert fatigue.** Mitigated by the DCS, deduplication and reviewer-gated suppression. Effectiveness has to be measured against a proposed ≤ 5% false-positive target for Confirmed findings.
- **Adoption friction.** The platform adds steps (approvals, target registration). These must be cheaper than the manual effort they replace.
- **Licence obligations of components** such as k6, Grafana and Loki (AGPL-3.0) and Vault (BUSL-1.1). These must be re-verified at adoption.

## Next Steps

Phase 0 — Concept & Validation (indicative Q4 2026) is proposed to:

1. Review this documentation set with prospective users matching the six personas and with security reviewers.
2. Resolve open decisions in the decisions log, starting with DEC-01 (project licence).
3. Build a throwaway spike that proves the sandbox baseline (gVisor, network-off execution, cleanup within 60 s) and an end-to-end Baseline Run on a sample repository.
4. Validate the proposed success metrics and gate thresholds against real suites before Phase 1 commits to them.
5. Confirm the Phase 1 — Foundations backlog against the [functional requirements](../03-requirements/01-functional-requirements.md).
