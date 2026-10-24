# Risks, Limitations and Open Decisions

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document records the main risks to the Autonomous QA Swarm project and to the people who would use it, the inherent limitations of autonomous testing that no design can remove, and the decisions that remain open. It is intended to be reviewed at every phase exit in the [Roadmap](02-roadmap.md). Because nothing has been built, likelihood and impact ratings are judgements made at concept stage, not measurements. The document owns the risk IDs RSK-01 to RSK-20 and the decision IDs DEC-01 to DEC-10.

## How risks are rated and owned

Each risk has a likelihood and an impact rated **L** (low), **M** (medium) or **H** (high), shown as "likelihood / impact". Owner roles refer to roles in the open-source project (for example core maintainers, the security lead or the AI and agent lead) or to the operator of a self-hosted deployment, not to the platform's RBAC roles. The indicator column names the signal that would show the risk is materializing; where possible the signal is a metric already proposed in [Observability and operations](../11-quality-gates-and-reporting/03-observability-and-operations.md) or a success metric from [Vision, objectives and metrics](../01-product-vision/03-vision-objectives-and-metrics.md).

Risks are reviewed at each phase exit. A risk whose indicator fires is escalated to the core maintainers, and its mitigation is either strengthened or the affected scope is deferred.

## Risk register

### AI quality and trust risks

| ID | Risk | L / I | Mitigation | Owner role | Indicator |
|---|---|---|---|---|---|
| RSK-01 | LLM hallucination: agents invent defects, misread results or describe nonexistent code | H / H | Agents only propose; deterministic oracles and DCS decide; LLM opinion cannot reach Confirmed; schema validation of outputs | AI and agent lead | Rising share of LLM-only Candidate findings rejected in triage |
| RSK-02 | False positives erode user trust and the tool is ignored | H / H | "No evidence, no defect"; reproduction in fresh sandboxes; scoped suppressions; precision history in DCS | Core maintainers | NFR-010 false-positive rate above 5% of Confirmed findings over 30 days |
| RSK-03 | Automation bias: users treat READY as proof of quality | M / H | Verdict is a recommendation; residual-risk section mandatory; HA-10 human decision; wording avoids guarantees | Product lead | Release decisions recorded with no reason on READY_WITH_RISKS verdicts |
| RSK-04 | LLM nondeterminism makes plans and generated tests vary between identical runs | H / M | Deterministic execution of tests; record model, prompt version and seeds; NFR-007 documents nondeterminism | AI and agent lead | Plan diff between repeated jobs on the same commit exceeds an agreed threshold |
| RSK-05 | Patch proposals introduce regressions or overload reviewers | M / M | Minimal diffs; HA-06 review; independent verification in fresh sandbox; no auto-commit (FR-041) | AI and agent lead | High `verification_failed` or `rejected` rate for patches |

### Security and safety risks

| ID | Risk | L / I | Mitigation | Owner role | Indicator |
|---|---|---|---|---|---|
| RSK-06 | Sandbox escape by malicious repository code | M / H | gVisor, dropped capabilities, no socket, network off, disposable workers; microVMs in Phase 4 | Security lead | Runtime security alerts; upstream gVisor advisories |
| RSK-07 | Prompt injection through repository content, logs or responses | H / M | Content treated as untrusted data (SEC-014); agents hold no credentials; Policy Engine validates every proposal | Security lead | Policy denials for out-of-scope proposals traced to injected text |
| RSK-08 | Legal misuse: platform used to test systems without authorization | M / H | Target registration and attestation (HA-01, HA-02); deny-by-default policy; non-destructive defaults; safe-use policy | Security lead | Reports of misuse; attestation patterns indicating unowned targets |
| RSK-09 | Load or DAST runs harm a target environment | M / H | Profile caps, automatic abort rules, approvals HA-03 and HA-05, ephemeral targets by default | Security lead | Abort-rule triggers; target owner complaints |
| RSK-10 | Secrets leak into evidence, logs, prompts or reports | M / H | Secrets Broker only; redaction before hashing; no secrets to agents or LLMs (SEC-007, SEC-008) | Security lead | Secret-detection hits on platform evidence or logs |
| RSK-11 | Supply-chain compromise of worker images or bundled tools | M / H | Images pinned by digest, signed, SBOM-tracked (SEC-006, SEC-020); dependency scanning of the platform | Core maintainers | Advisory affecting a pinned tool; signature verification failure |

### Cost risks

| ID | Risk | L / I | Mitigation | Owner role | Indicator |
|---|---|---|---|---|---|
| RSK-12 | LLM cost overrun for operators using hosted models | H / M | Per-job token budgets (NFR-015); budget exhaustion skips LLM tasks; local-model option | Operator | Token usage per job trending above budget |
| RSK-13 | Compute cost overrun from reruns, reproduction and mutation | M / M | Per-job compute budget; mutation capped at 500 mutants; rerun limits; profile duration caps | Operator | Worker-minutes per job rising faster than tests per job |

### Project and ecosystem risks

| ID | Risk | L / I | Mitigation | Owner role | Indicator |
|---|---|---|---|---|---|
| RSK-14 | Open-source maintainer bandwidth is insufficient | H / H | Narrow MVP; plugin interfaces so others own adapters; clear contribution guide | Core maintainers | Issue and pull-request response time growing; few active maintainers |
| RSK-15 | Licence changes in a dependent tool (for example k6, Grafana, Vault) | M / M | Adapter interfaces (NFR-017); OSS alternatives listed; licences re-verified at adoption | Core maintainers | Upstream licence change announcement |
| RSK-16 | Model provider terms change (data retention, training use, region) | M / H | Provider allow-list and data controls (SEC-021); local-model option; per-provider terms review | Security lead | Provider terms update affecting stored or processed data |
| RSK-17 | Scope creep delays the MVP | H / M | Fixed MVP boundary; out-of-MVP list; phase exit criteria | Product lead | Phase exit slipping by more than one indicative quarter |
| RSK-18 | Limited language support (Python and JavaScript/TypeScript first) restricts adoption | M / M | Adapter SDK in Phase 5; clear "unsupported language" reporting | Product lead | Share of registered repositories marked unsupported |

### Operational and technical risks

| ID | Risk | L / I | Mitigation | Owner role | Indicator |
|---|---|---|---|---|---|
| RSK-19 | Flaky infrastructure makes jobs INCONCLUSIVE and hides real results | M / H | Bounded retries, leases, QG-08 reports instead of hiding; image pre-pull; orphan reaper | Operator | QG-08 inconclusive on more than 10% of jobs per week |
| RSK-20 | PostgreSQL-backed task queue limits control-plane throughput | M / M | Measure early; queue behind an interface; Temporal as Future option (DEC-02) | Core maintainers | Queue latency or lock contention rising with concurrent jobs |

### Top risks for the MVP

At concept stage the risks judged most likely to decide whether the project succeeds are RSK-01 and RSK-02 (trust in findings), RSK-06 and RSK-08 (safety and legal exposure), and RSK-14 (maintainer bandwidth). The Phase 1 and Phase 2 exit criteria in the [Roadmap](02-roadmap.md) are deliberately tied to these: sandbox controls must be tested before any untrusted repository is run, and the confirmed-finding false-positive rate must be measured before quality gates are offered as release input.

## Limitations of autonomous testing

The following limits are inherent. The platform is designed to make them visible, not to claim it has overcome them.

### The oracle problem

A test can only detect a defect if something decides what correct behavior is. Deterministic oracles (assertions, schemas, thresholds, scanner rules) encode the expectations someone already wrote down. Where requirements are missing or ambiguous, the Requirements Analysis Agent can propose expectations, but those proposals are interpretations; a generated test that asserts the current behavior can freeze a defect into the suite. This is why generated tests require human review before promotion (FR-016) and why LLM opinion cannot confirm a finding.

### Coverage is not quality

Line coverage, scenario execution coverage (QG-04) and even mutation score (QG-06) measure how much was exercised and how sensitive tests are, not whether the software is correct. A suite can execute every line with weak assertions. Mutation score helps expose that, but it covers only the operators the mutation tool applies, and only changed modules by default.

### Testing cannot prove absence of defects

Every verdict, including READY, means only that the configured checks found no blocking issue at the measured confidence. Untested paths, unmodeled inputs, timing issues and threats outside the selected profile remain possible. No security profile claims comprehensive coverage; the Quick and Standard profiles do not include DAST at all.

### Environment parity

Tests run against ephemeral in-sandbox targets or registered non-production environments. Differences in data volume, configuration, network topology, third-party services and hardware mean that performance results in particular may not transfer to production. Reports state the target used and the parity caveats.

### AI nondeterminism

LLM outputs vary between calls even with the same inputs. Plans, scenario lists and patch proposals may differ between two jobs on the same commit. The platform constrains this by executing only deterministic tooling, recording model and prompt versions, and treating LLM output as proposals; it cannot make LLM reasoning reproducible.

### Business-logic understanding

Defects such as incorrect fee calculation, wrong rounding policy or a missing regulatory check are only detectable when the rule is specified somewhere the platform can read. The sample finding FND-0196 ("Amount 0.005 rounds to 0.00 and transfer succeeds") is illustrative: it is detectable as a boundary case, but whether it is a defect depends on business rules that a human must confirm.

### Bounded and non-destructive by design

Because security and performance testing are authorized, bounded and non-destructive by default, the platform will intentionally not find issues that only appear under destructive exploitation, unbounded load or long soak periods outside the approved profiles.

## Open decisions

Each decision lists the options, the main considerations and the phase by which it must be decided. Decisions are recorded with rationale when closed; until then the proposed default shown applies in the documentation.

| ID | Decision | Options | Proposed default | Decide by |
|---|---|---|---|---|
| DEC-01 | Project licence (Apache-2.0 proposed) | Apache-2.0; MIT; MPL-2.0; AGPL-3.0 | Apache-2.0 | Phase 0 exit |
| DEC-02 | Workflow engine for scale | PostgreSQL state machine only; Temporal; other durable engine | PostgreSQL state machine for MVP | Phase 3 exit |
| DEC-03 | Default model strategy | Hosted API default; local open-weight default; no default | No default, operator chooses at install | Phase 1 exit |
| DEC-04 | Policy engine implementation | OPA/Rego; embedded rules in Python; Cedar-style alternative | OPA/Rego | Phase 1 exit |
| DEC-05 | Default secrets backend | OpenBao; HashiCorp Vault; cloud KMS adapters | OpenBao | Phase 1 exit |
| DEC-06 | Default log store in reference deployment | Loki; OpenSearch | Undecided | Phase 1 exit |
| DEC-07 | Can HA-09 override the hard blockers (open Confirmed Critical or High security without accepted risk) | Never; with two approvers; per-project setting | Never | Phase 2 exit |
| DEC-08 | Route for promoting reviewed generated tests | In-platform review then manual copy; PR export (HA-12); both | In-platform review for MVP | Phase 3 exit |
| DEC-09 | MicroVM isolation technology | Firecracker; Kata Containers; both behind an interface | Firecracker | Phase 4 start |
| DEC-10 | Contribution and governance model | DCO sign-off; CLA; foundation hosting | DCO sign-off | Phase 0 exit |

### Decision considerations

- **DEC-01 Project licence.** Apache-2.0 offers a patent grant and is compatible with most dependencies listed in [Technology options](../05-architecture/05-technology-options.md). Several proposed components are AGPL-3.0 (Grafana, Loki, k6) or BUSL-1.1 (HashiCorp Vault); they are run as separate processes or optional, and the decision must confirm this does not affect the project licence. Legal review is required before closing.
- **DEC-02 Workflow engine.** The MVP queue uses `SELECT … FOR UPDATE SKIP LOCKED`, which keeps the stack small. Temporal (MIT) adds durable workflows and better scaling but another service to operate. The decision depends on RSK-20 indicators measured in Phase 2 and Phase 3.
- **DEC-03 Default model strategy.** Hosted models are likely more capable but carry cost (RSK-12) and terms risk (RSK-16). Local models avoid data egress but need GPUs. NFR-018 requires the pipeline to be runnable with OSS components only, which a local default would demonstrate.
- **DEC-04 Policy engine.** OPA/Rego gives auditable policy-as-code and a mature ecosystem; embedded rules are simpler but harder for operators to customize. Performance of per-proposal evaluation must be measured.
- **DEC-05 Secrets backend.** OpenBao is MPL-2.0; Vault is BUSL-1.1 and not OSI open source. Both have similar APIs today; divergence over time is a consideration.
- **DEC-06 Log store.** Loki is AGPL-3.0 and lightweight; OpenSearch is Apache-2.0 and heavier but offers full-text search for log investigation. The reference Docker Compose deployment must stay small enough for a single host.
- **DEC-07 Hard-blocker overrides.** Allowing overrides gives teams flexibility in emergencies but weakens the "aggregate scores never hide blockers" rule. Requiring accepted risk (HA-08) instead of override keeps the decision explicit and expiring. See [Quality gates and release readiness](../11-quality-gates-and-reporting/02-quality-gates-and-release-readiness.md).
- **DEC-08 Generated test promotion.** PR export is convenient but moves the platform closer to changing repositories; HA-12 is Future. In the MVP, reviewed tests are exported as artifacts only.
- **DEC-09 MicroVM technology.** Firecracker has a small attack surface but needs KVM; Kata Containers integrates with Kubernetes runtime classes. The choice affects which hosts can run the hostile-code tenancy mode.
- **DEC-10 Governance.** DCO is lighter for contributors; a CLA eases future relicensing but deters some contributors. Foundation hosting could help with RSK-14 but adds process.

## Review cadence

The register and decisions are reviewed at each phase exit, and additionally when an indicator fires, when a dependent tool or provider changes terms, or when a security incident affects any component. Closed decisions remain listed with their outcome so that later readers can see why a choice was made.
