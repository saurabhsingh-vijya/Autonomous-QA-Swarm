# Scope, Assumptions and Constraints

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document fixes the boundary of the proposed Autonomous QA Swarm platform: what the MVP (Phases 1 to 3) is planned to include, what is deferred to Future phases, and what is excluded outright. It also records the assumptions (A-01 to A-12), external dependencies (D-01 to D-10) and constraints (C-01 to C-10) on which the [Functional requirements](01-functional-requirements.md) and [Non-functional requirements](02-non-functional-requirements.md) rest. Each entry states what happens if it proves wrong and how that is mitigated. Phase content is detailed in the [Roadmap](../12-risks-and-roadmap/02-roadmap.md), and risks arising from these items are tracked in [Risks, limitations and decisions](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md).

## Scope

### In scope for the MVP — Planned (MVP)

The MVP is planned as a single-organization, self-hosted deployment. Its scope is:

- Repository intake from GitHub and GitLab over HTTPS, public and private (read-only app tokens via credential references), with SSRF-safe validation and immutable commit pinning (FR-001 to FR-004).
- Languages **Python** and **JavaScript/TypeScript**; execution of existing pytest, Jest/Vitest and Playwright suites in gVisor-isolated rootless containers (FR-015).
- Job creation, scoping, idempotency, DAG planning, optional plan approval, live progress, cancellation and bounded retries (FR-005 to FR-012).
- Requirements and change analysis, and generated candidate tests that require human review before promotion or use in CI (FR-013, FR-014, FR-016).
- Schema-driven API testing, negative and property-based tests, and authorization checks against ephemeral or authorized non-production targets (FR-019 to FR-021, FR-050).
- Security profiles Quick and Standard: SAST, dependency scanning, secret detection, IaC/configuration and container image scanning (FR-022 to FR-025).
- Performance profiles Smoke and Baseline only, with baseline comparison (FR-027, FR-029).
- Mutation testing on changed modules with surviving-mutant suggestions (FR-030, FR-031).
- Evidence capture, Defect Confidence Score, deduplication, reproduction, reconciliation and triage (FR-032 to FR-037).
- Patch proposal, human review and independent verification, with no commit, push or merge (FR-038 to FR-041).
- Quality gates QG-01 to QG-08, release-readiness recommendation and human decision record; JSON, HTML, PDF, SARIF and JUnit reports (FR-042 to FR-049).
- Settings, CI triggers (Jenkins, GitHub Actions), notifications, Model Gateway configuration and audit trail (FR-051 to FR-054).

### Future scope

Items planned after the MVP, labelled **Future**:

- Phase 4 — Scale & Depth: DAST in the Deep profile (FR-026), Load, Stress, Spike and Soak profiles (FR-028), Firecracker or Kata microVM isolation, multi-tenant operation, Java support (the sample repository `northwind/ledger-service` illustrates this as "Unsupported language (Phase 4)").
- Exporting verified patches or generated tests as pull requests under HA-12.
- Phase 5 — Ecosystem: plugin SDK, further languages and a shared catalogue of agent skills.
- Optional migration of the workflow engine to Temporal if the PostgreSQL-backed queue proves insufficient.

### Explicitly out of scope

The following are excluded from the platform's purpose, not merely deferred:

- **Production load testing.** Performance profiles target ephemeral or registered non-production environments only.
- **Exploitation beyond proof.** Security checks stop at demonstrating reachability or a precondition (SEC-018); no data extraction, persistence or lateral movement.
- **Auto-merge and autonomous repository writes.** The platform never commits, pushes or merges (FR-041); even Future pull-request export requires human approval.
- **Testing third-party systems** without the owner's recorded authorization (HA-01).
- **Mobile and desktop application testing**, device farms and native UI automation.
- **Replacement of human release authority.** The platform recommends; a named human decides (HA-10).
- **Certification or compliance attestation.** Reports are evidence for audits, not certificates of security or compliance.
- **Hosted SaaS operation by the project** in the MVP; operators self-host.
- **Training or fine-tuning models** on customer code or evidence.

## Assumptions

| ID | Assumption | Impact if wrong | Mitigation |
|---|---|---|---|
| A-01 | Target repositories build reproducibly from source with declared dependencies in a Linux container | Environment Preparation fails; jobs end `completed_with_warnings` with few results | Clear build-failure diagnostics; per-project build recipe overrides; report states that tests could not run |
| A-02 | Projects have an existing automated test suite worth running as a baseline | Baseline Run yields little signal; QG-03 and QG-04 become weak | Rely on generated scenarios after review; report low coverage as residual risk |
| A-03 | Operators can supply authorized, non-production targets or the app can start inside the sandbox | API, authorization and performance testing cannot run | Ephemeral in-sandbox targets as default; stages marked `skipped` with reason |
| A-04 | OpenAPI documents, where supplied, are reasonably accurate | Schema tests produce noise or miss defects | Contract violations start below Confirmed until reproduced; spec-quality warnings in report |
| A-05 | LLM output quality is sufficient for planning, scenario derivation and patch drafting when validated | More `invalid_output` tasks; fewer useful proposals | Schema validation, one corrective retry, deterministic fallbacks (run full suite when planning fails) |
| A-06 | Reviewers (QA Lead, Security Reviewer, Developer) are available to act on approvals within working hours | Jobs wait in `awaiting_approval` and may time out | Notifications, approval queue visibility, configurable job wall clock up to 12 h |
| A-07 | gVisor provides adequate isolation for semi-trusted code from the operator's own organization | Sandbox escape risk higher than estimated | Defense in depth (SEC-003 to SEC-005); microVMs planned for hostile-code tenancy |
| A-08 | Package registries are reachable through the egress proxy during the dependency-fetch phase | Builds fail; QG-08 trips; verdict INCONCLUSIVE | Registry mirrors or caches; clear `infrastructure_error` classification |
| A-09 | The reference deployment (8 workers × 2 vCPU) is representative of early adopters | Capacity and latency targets misjudged | Publish sizing guidance with measured numbers once available |
| A-10 | Test flakiness is largely explainable by reruns in fresh workers | Flaky defects mis-classified as real or vice versa | Flaky Test Register, QA Lead acknowledgement for quarantine, DCS stability component |
| A-11 | Organizations accept that findings and gates are recommendations requiring human judgement | Users over-trust verdicts | Confidence levels, "recommendation" wording, residual-risk sections in every report |
| A-12 | Python and JavaScript/TypeScript cover the majority of early-adopter repositories | Limited MVP adoption | Adapter interfaces (NFR-017) to add languages in Phase 4 |

## Dependencies

| ID | Dependency | Impact if unavailable or changed | Mitigation |
|---|---|---|---|
| D-01 | Git providers (GitHub, GitLab) APIs and HTTPS clone endpoints | Intake and ref resolution fail; jobs cannot start | Retries with backoff; clear validation errors; provider adapters isolated |
| D-02 | OIDC identity provider (Keycloak proposed, or operator's IdP) | No user login; MFA unavailable | Support any standards-compliant IdP; service-account tokens cached within expiry only |
| D-03 | LLM availability through the Model Gateway (hosted APIs or local Ollama/vLLM) | Planning, analysis, patches and narratives degrade | Deterministic fallbacks; local-model option; per-provider timeouts; LLM-dependent stages marked skipped, not silently passed |
| D-04 | Secrets Broker (OpenBao proposed, or Vault) | Private repositories and target credentials inaccessible | High-availability deployment guidance; jobs needing secrets end `blocked` rather than proceed without |
| D-05 | Container runtime with gVisor (Docker or Podman rootless + runsc) | No sandbox execution at all | Startup self-check refuses to run without required isolation; documented supported versions |
| D-06 | PostgreSQL 16+ and an S3-compatible object store | Loss of state or evidence availability | Backups, WAL archiving, NFR-006 restore drills |
| D-07 | Vulnerability databases and scanner rule sets (OSV, Semgrep rules, Trivy DB) | Stale or missing security results | Record database snapshot version and date; warn when older than 7 days (proposed) |
| D-08 | Test and analysis tools (pytest, Jest/Vitest, Playwright, Schemathesis, k6, mutmut, Stryker, ZAP) | Stage unavailable or results change across versions | Pin tool versions in worker images by digest; adapter contract tests |
| D-09 | CI systems (Jenkins, GitHub Actions) for triggers and result consumption | CI integration unavailable; manual use still possible | Standard REST API and SARIF/JUnit outputs; no CI-specific logic in core |
| D-10 | Notification channels (SMTP, Slack, Teams, webhooks) | Users miss approvals or results | Retry with logging; in-app approval queue; delivery failure never alters job state |

## Constraints

| ID | Constraint | Impact if violated | Mitigation |
|---|---|---|---|
| C-01 | Licensing: project licence proposed Apache-2.0 (DEC-01 open); bundled components must be compatible | Distribution blocked or legal exposure | Licence inventory per release; AGPL tools (k6, Grafana, Loki) run as separate processes, not linked |
| C-02 | Legal: testing only systems the operator is authorized to test | Unlawful or harmful testing | HA-01 attestation, scope-bound targets, SEC-016 enforcement |
| C-03 | Security: agents never execute code, hold credentials or change repositories | Core trust model broken | Policy Engine deny-by-default; architecture reviews; SEC-001, SEC-007, FR-041 tests |
| C-04 | Non-destructive defaults for all security and performance testing | Damage to targets or data | Profile caps, abort rules, destructive rules excluded (SEC-017, SEC-018) |
| C-05 | OSS-only operability: the full pipeline must run without paid services | Adoption barrier; lock-in | NFR-018 reference profile; paid services only as optional adapters |
| C-06 | Budget: LLM and compute cost is the operator's responsibility and must be boundable per job | Unexpected spend | Per-job token and compute budgets enforced and reported (NFR-015) |
| C-07 | Hardware: reference deployment is a modest self-hosted cluster; no GPU assumed for the control plane | Local models slow or infeasible on small installs | Hosted-model adapter optional; local models on separate inference hosts |
| C-08 | Data residency and privacy: source and evidence must not leave the operator's boundary unless configured | Disclosure to providers | Model Gateway allow-list, redaction, local-model option (SEC-021) |
| C-09 | Linux-only workers in the MVP | Windows- or macOS-specific suites cannot run | Documented limitation; stage marked skipped with reason |
| C-10 | Human approval for every high-impact action (HA-01 to HA-12) | Unsafe autonomy | Approvals enforced in Policy Engine and audited (FR-054) |

## Scope change control

Changes to the in-scope list, to any assumption, dependency or constraint above, or to the boundary between MVP and Future are planned to be recorded as decisions in [Risks, limitations and decisions](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md), with the affected FR, NFR and SEC IDs listed. An assumption shown to be false during Phase 1 to 3 validation triggers a review of the requirements that depend on it before the next phase exit. Nothing in this document will be labelled Implemented / Verified until the relevant phase's acceptance criteria have passed.
