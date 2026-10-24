# Non-Functional and Security Requirements

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document defines the quality attributes (NFR-001 to NFR-020) and security requirements (SEC-001 to SEC-022) that the proposed Autonomous QA Swarm platform is planned to meet. All targets are proposed values for a self-hosted reference deployment and have not been measured, because no implementation exists; every requirement here has status **Proposed**, and none is **Implemented / Verified**. Each requirement states how it will be measured so that it can later be verified objectively. Functional behavior is specified in [Functional requirements](01-functional-requirements.md); the threats these controls address are analyzed in [Security architecture and threat model](../10-security-and-threat-model/01-security-architecture-and-threat-model.md).

## Conventions

Priorities use the same definitions as the functional catalogue: **P0** must hold for the phase to exit, **P1** should hold and may slip one phase with a recorded decision, **P2** is desirable. Phase is the roadmap phase in which the requirement is first planned to be verified; Phases 1 to 3 are **Planned (MVP)** and Phase 4 onward is **Future**. NFR and SEC titles are reproduced verbatim from the requirement catalogue.

The **reference deployment** used for all performance and capacity targets is a single organization, self-hosted control plane (API Gateway, Workflow Engine, Policy Engine, Model Gateway, PostgreSQL 16, S3-compatible Evidence Store) plus a worker pool of 8 sandbox workers with 2 vCPU and 4 GiB RAM each. Targets measured on other hardware are reported against this baseline, not substituted for it.

Measurements follow three principles. First, latency targets are percentiles over a stated window and load, never averages. Second, a target counts as met only when it holds in at least three consecutive measurement runs. Third, LLM provider latency is excluded from platform latency targets and reported separately, because it is outside the operator's control.

## Quality attribute requirements

### Performance efficiency

| ID | Title | Target | Measurement method | Pri | Phase |
|---|---|---|---|---|---|
| NFR-001 | API latency: p95 ≤ 300 ms for read endpoints at 50 concurrent users | p95 ≤ 300 ms, error rate < 0.5% | k6 script against GET endpoints (jobs, findings, test-executions) with 50 VUs for 10 min on seeded dataset of 500 jobs | P0 | 2 |
| NFR-002 | Job start latency ≤ 60 s from creation to first task running (warm pool) | ≤ 60 s at p95 | Timestamp delta between Job `created` and first Task `running` over 50 jobs with ≥ 1 warm worker available | P1 | 1 |
| NFR-003 | Event stream delivery ≤ 2 s from state change to UI | ≤ 2 s at p95 | Compare DB commit timestamp of transition with client receipt time for 1,000 events at 10 concurrent jobs | P0 | 1 |
| NFR-004 | Throughput: ≥ 10 concurrent jobs on reference deployment (8 workers × 2 vCPU) | 10 jobs running, 0 lost tasks, QG-08 ≤ 5% | Launch 10 Functional Standard jobs on fixture repos simultaneously; verify all reach a terminal state | P1 | 3 |
| NFR-019 | Report generation ≤ 30 s for jobs with ≤ 10,000 test executions | ≤ 30 s for JSON and HTML; PDF reported separately | Time report task on synthetic job with 10,000 TestExecutions and 200 findings | P1 | 2 |

### Reliability and scalability

| ID | Title | Target | Measurement method | Pri | Phase |
|---|---|---|---|---|---|
| NFR-005 | Control-plane availability 99.5% monthly (self-hosted reference) | ≥ 99.5% of 1-min probes succeed per calendar month | Synthetic probe of `/api/v1` health and GET /projects every 60 s; planned maintenance windows reported, not excluded silently | P1 | 3 |
| NFR-006 | Durability: no loss of committed job state or evidence on single-node failure (RPO ≤ 15 min, RTO ≤ 4 h) | RPO ≤ 15 min, RTO ≤ 4 h | Quarterly restore drill: kill primary DB node and object-store node, restore from backups and WAL, compare row and object counts | P0 | 3 |
| NFR-008 | Worker cleanup: 100% of workers destroyed within 60 s of terminal task state; orphan reaper every 5 min | 100% within 60 s; 0 orphans after one reaper cycle | Chaos test that kills Execution Service mid-task; count runtime sandboxes and volumes at +60 s and +5 min | P0 | 1 |
| NFR-011 | Scalability: horizontal worker scaling without control-plane changes | Adding worker hosts increases concurrent task capacity linearly ±15% up to 32 workers | Add worker hosts by configuration only; measure tasks per hour with fixed workload | P1 | 3 |

### Reproducibility and explainability

| ID | Title | Target | Measurement method | Pri | Phase |
|---|---|---|---|---|---|
| NFR-007 | Reproducibility: same commit + config + tool versions re-run yields identical deterministic results except documented nondeterminism | 100% identical test statuses and finding fingerprints for deterministic fixtures | Re-run 3 fixture jobs twice with pinned image digests; diff TestExecution statuses and fingerprints; every difference must map to a documented source (flaky list, time, LLM output) | P0 | 2 |
| NFR-009 | Explainability: 100% of reported findings link to evidence, tool/version and decision trail | 100% | Automated report check over every finding in a sample of 20 jobs | P0 | 2 |
| NFR-010 | False-positive rate of Confirmed findings ≤ 5% measured by human triage over rolling 30 days | ≤ 5% | Count Confirmed findings later triaged false positive or not reproducible ÷ all triaged Confirmed findings, rolling 30 days; reported only when ≥ 40 findings triaged | P1 | 3 |

NFR-007 accepts that LLM outputs are not bit-reproducible. Reproducibility therefore applies to deterministic results (test statuses, scanner outputs, scores and gate verdicts given the same evidence); agent text is reproducible only in the sense that prompts, model identifiers and response hashes are recorded.

NFR-010 is a measure of residual error, not a guarantee. It depends on human triage actually happening, so the platform is planned to report the triage rate alongside it.

### Usability and portability

| ID | Title | Target | Measurement method | Pri | Phase |
|---|---|---|---|---|---|
| NFR-012 | Usability: first job created by new user in ≤ 10 min without docs; WCAG 2.2 AA | ≥ 80% of 5+ test participants succeed in ≤ 10 min; 0 WCAG 2.2 AA violations in automated scan; manual keyboard and screen-reader check | Moderated usability sessions on SCR-03; axe-core scan of all 15 screens | P1 | 3 |
| NFR-020 | Localisation-ready UI strings; times stored UTC, shown in user time zone | 0 hard-coded UI strings; 100% timestamps stored UTC | Lint for literal strings in components; pseudo-locale build renders all screens; DB schema check for timezone-aware columns | P2 | 3 |
| NFR-013 | Portability: runs on single Linux host (Docker Compose) and Kubernetes | Same fixture job passes on both topologies | CI pipeline deploys Compose and a Helm-based Kubernetes install and runs the acceptance fixture job | P1 | 3 |

### Operability and cost

| ID | Title | Target | Measurement method | Pri | Phase |
|---|---|---|---|---|---|
| NFR-014 | Observability: all services emit OTel traces/metrics/logs with correlation IDs | 100% of services; one trace spans API request to WorkerRun | Trace inspection for a fixture job; check job_id and task_id attributes on spans and logs | P0 | 1 |
| NFR-015 | Cost control: per-job LLM token budget and compute budget enforced; usage reported | 0 jobs exceed budget by more than one in-flight call | Fixture job with low token budget; verify task ends with "token budget exceeded" and report shows usage per agent | P0 | 2 |
| NFR-016 | Data retention configurable (default 90 days evidence, 1 year audit) | Expired evidence deleted within 24 h of expiry; audit retained ≥ 1 year | Time-shifted retention test; verify deletion AuditEvents and legal-hold exclusion | P1 | 2 |
| NFR-018 | Open-source operability: full pipeline runnable with OSS components only | Fixture job completes with 0 paid services | Reference profile using local model via Ollama or vLLM, OSS object store, Keycloak and OpenBao; licence inventory reviewed | P0 | 3 |

### Maintainability

| ID | Title | Target | Measurement method | Pri | Phase |
|---|---|---|---|---|---|
| NFR-017 | Maintainability: agents and tools pluggable through versioned adapter interfaces | New tool adapter added without changing Workflow Engine or Policy Engine code | Add a second runner adapter (for example Locust next to k6) using only the adapter SDK; contract tests pass | P1 | 3 |

NFR-017 also implies that adapter interfaces follow semantic versioning and that a breaking interface change requires a major version bump with a deprecation period of at least one minor release.

## Security requirements

Security requirements describe controls, not outcomes: meeting all of them reduces risk but does not make the platform or the systems it tests secure. Each requirement below lists the threats it addresses by category; the numbered threat entries and STRIDE tags are maintained only in the [threat model](../10-security-and-threat-model/01-security-architecture-and-threat-model.md). Implementation detail is in [Identity, secrets, audit and data protection](../10-security-and-threat-model/02-identity-secrets-audit-and-data-protection.md), [Sandboxed execution](../10-security-and-threat-model/03-sandboxed-execution.md) and [Safe-use policies](../10-security-and-threat-model/04-safe-use-policies.md).

### SEC-001 — Control plane never executes repository code

- **Requirement:** No control-plane service shall run, import, build, or evaluate repository content, including Git hooks, LFS filters, build scripts and configuration templates; all execution happens in sandbox workers.
- **Rationale:** Repository content is untrusted and may be hostile; the control plane holds credentials and policy.
- **Verification:** Malicious fixture repository with hooks, filters and install scripts processed through intake; process auditing shows 0 child processes from repo content on control-plane hosts.
- **Related threats:** Remote code execution on the control plane; elevation of privilege via intake.
- **Phase:** 1 — P0.

### SEC-002 — Repository URL allow-list, HTTPS only, DNS-pinned, private-address rejection

- **Requirement:** Repository URLs shall use HTTPS, match the provider allow-list, resolve only to public addresses, and be fetched using the validated, pinned IP; redirects to non-allow-listed hosts are refused.
- **Rationale:** Prevents SSRF to internal services and metadata endpoints.
- **Verification:** SSRF test corpus (decimal and IPv6-mapped IPs, DNS rebinding, redirect chains, userinfo tricks) yields 100% rejection.
- **Related threats:** Server-side request forgery; information disclosure from internal networks.
- **Phase:** 1 — P0.

### SEC-003 — Sandbox isolation baseline (non-root, caps dropped, read-only FS, no socket, limits)

- **Requirement:** Workers shall run as UID 10001 under gVisor with all capabilities dropped, `no-new-privileges`, read-only root FS, default seccomp and AppArmor, no Docker socket, no host mounts or namespaces, and limits of 2 vCPU, 4 GiB, 512 PIDs and 10 GiB disk.
- **Rationale:** Test code is untrusted; containment limits blast radius.
- **Verification:** Policy check on every WorkerRun spec; escape test suite (fork bomb, disk fill, capability probes, socket access) contained in 100% of cases.
- **Related threats:** Sandbox escape; denial of service on worker hosts.
- **Phase:** 1 — P0. Firecracker microVM isolation is Future (Phase 4).

### SEC-004 — Network off during execution; allow-listed dependency-fetch phase only

- **Requirement:** Workers shall have no network during execution; dependencies are fetched in a separate phase through an egress proxy allow-listed to package registries.
- **Rationale:** Prevents exfiltration and uncontrolled outbound attacks from test code.
- **Verification:** Test that opens sockets during execution fails; proxy logs show only allow-listed hosts in the fetch phase.
- **Related threats:** Data exfiltration; abuse of the platform as an attack origin.
- **Phase:** 1 — P0.

### SEC-005 — Block cloud metadata, control-plane and internal networks from workers

- **Requirement:** Worker network policy shall deny cloud metadata IPs, RFC1918 ranges, link-local ranges and control-plane addresses in every phase, except explicitly authorized target hosts.
- **Rationale:** Metadata and internal services are the most valuable pivot targets.
- **Verification:** Network probes from a worker to 169.254.169.254, control-plane ports and RFC1918 ranges are all blocked.
- **Related threats:** Credential theft via metadata; lateral movement.
- **Phase:** 1 — P0.

### SEC-006 — Pinned worker images by digest, signed and SBOM-tracked

- **Requirement:** Worker images shall be referenced by digest, signature-verified before use, and accompanied by an SBOM.
- **Rationale:** Tampered images would compromise every result.
- **Verification:** Unsigned or tag-only image reference is refused by the Execution Service; SBOM present for each digest.
- **Related threats:** Supply-chain tampering of execution images.
- **Phase:** 2 — P0.

### SEC-007 — Secrets held only in Secrets Broker; short-lived scoped tokens; never to agents/LLMs

- **Requirement:** Credentials shall live only in the Secrets Broker, be issued as short-lived scoped tokens to Source Intake Service and Target Environment Manager, and never be visible to agents, prompts or workers (except authorized, scoped, short-lived non-production test-user credentials).
- **Rationale:** Agents process untrusted content and can be manipulated.
- **Verification:** Canary credentials seeded per job; scan of prompts, AgentOutput, logs and evidence finds 0 occurrences; token TTL checked.
- **Related threats:** Credential disclosure; prompt-injection-driven exfiltration.
- **Phase:** 2 — P0.

### SEC-008 — Redaction of secrets in logs, evidence, prompts and reports

- **Requirement:** All captured output shall pass through redaction (known secret values, entropy and pattern detectors) before storage, display, egress to models or export.
- **Rationale:** Test output often contains tokens and personal data.
- **Verification:** Canary corpus test across logs, SSE stream, evidence, prompts, reports, SARIF and JUnit: 0 unredacted canaries.
- **Related threats:** Information disclosure through artifacts.
- **Phase:** 1 — P0.

### SEC-009 — OIDC authentication, MFA delegated to IdP, session limits

- **Requirement:** Users shall authenticate via OIDC; MFA is enforced by the IdP; sessions expire after 12 h absolute and 30 min idle (proposed defaults); service accounts use client credentials.
- **Rationale:** Centralized identity avoids local password storage.
- **Verification:** Expired, wrongly signed or wrong-audience tokens receive 401; session timeout tests.
- **Related threats:** Spoofing; session hijacking.
- **Phase:** 1 — P0.

### SEC-010 — RBAC with least privilege; per-agent tool permissions

- **Requirement:** Each API operation shall be authorized by role (Org Admin, QA Lead, QA Engineer, Developer, Security Reviewer, Viewer, CI Service Account), and each agent may emit only the proposal types in its permission set.
- **Rationale:** Limits damage from compromised accounts or manipulated agents.
- **Verification:** Generated role-by-endpoint matrix test; agent emitting an unpermitted proposal is denied by the Policy Engine.
- **Related threats:** Elevation of privilege; confused-deputy agent actions.
- **Phase:** 1 — P0.

### SEC-011 — Tenant isolation via org_id + PostgreSQL row-level security

- **Requirement:** Every tenant-owned table shall carry `org_id` with row-level security enforced for application database roles.
- **Rationale:** Defense in depth against application-level authorization bugs.
- **Verification:** Cross-organization query tests through API and direct DB role return 0 foreign rows.
- **Related threats:** Cross-tenant information disclosure.
- **Phase:** 1 — P0 (multi-tenant SaaS operation is Future).

### SEC-012 — Encryption in transit (TLS 1.2+) and at rest

- **Requirement:** All external and inter-service traffic shall use TLS 1.2 or higher; database, object store and backups shall be encrypted at rest.
- **Rationale:** Evidence and source code are sensitive.
- **Verification:** TLS scanner on all endpoints; storage configuration review.
- **Related threats:** Eavesdropping; disclosure from stolen media.
- **Phase:** 1 — P0.

### SEC-013 — Append-only, hash-chained audit log

- **Requirement:** Audit events shall be append-only, each including the hash of its predecessor, with periodic anchoring of the chain head outside the database.
- **Rationale:** Approvals and decisions must be tamper-evident.
- **Verification:** Tampering test modifies one event; chain verification reports the break.
- **Related threats:** Repudiation; tampering with records.
- **Phase:** 1 — P0.

### SEC-014 — Prompt-injection resistance: repository content treated as untrusted data

- **Requirement:** Repository, requirement and tool-output content shall be passed to models only inside delimited data sections, and no model output may change policy, permissions or results without deterministic validation.
- **Rationale:** Injected instructions in code or docs can steer agents.
- **Verification:** Injection corpus in fixture repos; 0 policy, permission or verdict changes attributable to injected text.
- **Related threats:** Prompt injection; tampering with conclusions.
- **Phase:** 2 — P0.

### SEC-015 — Schema validation of all agent and worker outputs

- **Requirement:** Every AgentOutput and worker result shall be validated against a versioned schema before use; invalid outputs are rejected and recorded.
- **Rationale:** Untyped output is the main path from model error to wrong action.
- **Verification:** Fuzzed malformed outputs are rejected 100% with `invalid_output` or `infrastructure_error`.
- **Related threats:** Tampering via malformed output; injection into downstream services.
- **Phase:** 1 — P0.

### SEC-016 — Active security testing only against authorised targets (HA-01/HA-02)

- **Requirement:** API authorization checks and DAST shall run only against ephemeral targets or registered targets with an unexpired attestation (HA-01), and DAST additionally requires HA-02.
- **Rationale:** Testing without authorization may harm third parties and be unlawful.
- **Verification:** Jobs against unregistered or expired targets end `blocked`; egress logs show traffic only to authorized hosts.
- **Related threats:** Abuse of the platform against third parties.
- **Phase:** 2 — P0.

### SEC-017 — Load testing safety limits and automatic abort

- **Requirement:** Performance runs shall respect profile caps and abort automatically on error rate > 20% for 60 s, 3 consecutive failed health checks, or p95 > 5× baseline for 2 min.
- **Rationale:** Load tests can cause outages.
- **Verification:** Fault-injected target triggers each abort rule; generation stops within 15 s.
- **Related threats:** Denial of service against targets.
- **Phase:** 3 — P0.

### SEC-018 — No exploitation beyond proof of reachability; non-destructive defaults

- **Requirement:** Security tests shall stop at demonstrating reachability or precondition (for example reading a test user's own sample record), exclude destructive rules by default, and never extract real data.
- **Rationale:** Proof is sufficient for a finding; further exploitation adds harm.
- **Verification:** Review of tool rule sets; evidence inspection on DAST and IDOR fixtures.
- **Related threats:** Collateral damage; data exposure during testing.
- **Phase:** 2 — P0.

### SEC-019 — Evidence access control and signed, short-lived download URLs

- **Requirement:** Evidence downloads shall require project authorization and use signed URLs valid for at most 5 minutes (proposed), with every download audited.
- **Rationale:** Evidence can contain sensitive request data.
- **Verification:** Expired or tampered URLs are refused; unauthorized users receive 403 or 404.
- **Related threats:** Information disclosure via shared links.
- **Phase:** 1 — P0.

### SEC-020 — Supply-chain security of the platform itself (SBOM, signed releases, dependency scanning)

- **Requirement:** Platform releases shall be built reproducibly where feasible, signed, published with SBOMs, and dependency-scanned on every build.
- **Rationale:** A QA platform is a high-value supply-chain target.
- **Verification:** Release checklist; signature verification; SCA gate in the platform's own CI.
- **Related threats:** Tampered releases; vulnerable platform dependencies.
- **Phase:** 3 — P1.

### SEC-021 — Model Gateway data controls (provider allow-list, no training on data where contractually available, local-model option)

- **Requirement:** The Model Gateway shall be the only model egress, enforce a provider allow-list, apply redaction and token budgets, record hashes, and support local models; hosted providers should be configured with no-training terms where offered.
- **Rationale:** Source code and evidence may leave the operator's boundary.
- **Verification:** Egress test from agents bypassing the gateway fails; configuration review.
- **Related threats:** Data disclosure to third-party providers.
- **Phase:** 2 — P0.

### SEC-022 — Rate limiting and abuse protection on public API

- **Requirement:** The API Gateway shall rate-limit per identity and per IP, return 429 with `Retry-After`, and bound request size and job creation rate.
- **Rationale:** Prevents resource exhaustion and brute force.
- **Verification:** Load test above limits yields 429 without control-plane degradation for other users.
- **Related threats:** Denial of service; credential stuffing.
- **Phase:** 1 — P1.

## ISO/IEC 25010 mapping

The table maps each requirement to the ISO/IEC 25010 product-quality characteristic it primarily supports (2023 revision naming where it differs). Several requirements support more than one characteristic; only the primary is shown.

| ISO/IEC 25010 characteristic | Requirements |
|---|---|
| Performance efficiency | NFR-001, NFR-002, NFR-003, NFR-004, NFR-019 |
| Reliability (incl. availability, recoverability, fault tolerance) | NFR-005, NFR-006, NFR-008, SEC-017 |
| Functional suitability (correctness) | NFR-007, NFR-010 |
| Interaction capability (usability, accessibility) | NFR-012, NFR-020, NFR-009 |
| Flexibility (portability, scalability) | NFR-011, NFR-013, NFR-018 |
| Maintainability (modularity, analysability) | NFR-014, NFR-017 |
| Security — confidentiality | SEC-005, SEC-007, SEC-008, SEC-011, SEC-012, SEC-019, SEC-021 |
| Security — integrity | SEC-001, SEC-003, SEC-004, SEC-006, SEC-014, SEC-015, SEC-020 |
| Security — non-repudiation and accountability | SEC-013, NFR-016 |
| Security — authenticity | SEC-009, SEC-010 |
| Safety (operational risk to targets) | SEC-002, SEC-016, SEC-018, SEC-022 |
| Resource utilization (cost) | NFR-015 |

## Verification approach and limits

All requirements above are planned to be verified by automated checks in the platform's own CI wherever feasible, with restore drills (NFR-006), usability sessions (NFR-012) and the rolling false-positive metric (NFR-010) as the exceptions that require scheduled human activity. Results will be published with each release so the label **Implemented / Verified** can be applied per requirement. Passing these checks will show that specific controls work under the tested conditions; it will not establish that unknown weaknesses are absent, and residual risks are tracked in [Risks, limitations and decisions](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md).
