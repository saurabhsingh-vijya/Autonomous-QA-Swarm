# Technology Options

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document records the proposed technology choice for each architectural concern of Autonomous QA Swarm, the alternatives considered, the license as currently understood, and whether the choice is free or carries cost. Every choice is **Proposed**; items intended for Phases 1–3 are additionally marked **Planned (MVP)**, later items **Future**. No item is **Implemented / Verified**, and that label will only be applied after code exists and acceptance tests pass. Licenses are recorded as listed in the design basis or as publicly stated by the projects; all of them must be **re-verified at adoption**, because projects change licenses. No performance or benchmark claims are made here; comparative measurements are a Phase 1 activity.

## Selection principles

The choices below follow five principles derived from the requirements in [Non-functional requirements](../03-requirements/02-non-functional-requirements.md):

1. **OSS-only end-to-end operation (NFR-018).** Every concern must have a free, open-source option that lets the full pipeline run without a paid service.
2. **Paid services as optional adapters.** Hosted LLMs, managed databases, managed object storage and SaaS CI plug in behind versioned adapter interfaces (NFR-017); none is required.
3. **Deterministic core, replaceable edges.** The Workflow Engine, Policy Engine, Execution Service and Evidence Store are deterministic services; tools and model providers are swappable.
4. **License hygiene.** Copyleft components (AGPL-3.0) are used only as separately deployed processes or services, not linked into the platform code base, so the proposed Apache-2.0 project license (DEC-01, still open) is not affected. Legal review is still required.
5. **Portability (NFR-013).** Everything must run on a single Linux host with Docker Compose and on Kubernetes.

## Choice summary

The two tables below summarise the proposed choice per concern. Detailed rationale follows in the next section.

### Platform concerns

| Concern | Proposed choice | Alternatives | License (re-verify at adoption) | Free vs paid |
|---|---|---|---|---|
| Language/runtime | Python 3.12 | Go, Kotlin/JVM | PSF License | Free |
| API framework | FastAPI + Pydantic | Django REST Framework, Litestar | MIT (both) | Free |
| Workflow/queue | PostgreSQL state machine with `SELECT … FOR UPDATE SKIP LOCKED` (MVP); Temporal (Future, if needed) | Celery + Redis, RabbitMQ, Argo Workflows | PostgreSQL License; Temporal MIT | Free; Temporal Cloud is paid optional |
| Database | PostgreSQL 16+ | MySQL, CockroachDB | PostgreSQL License | Free; managed PostgreSQL optional paid |
| Object storage | Any S3-compatible store: SeaweedFS or Ceph RGW self-hosted, cloud S3 optional | MinIO | SeaweedFS Apache-2.0; Ceph LGPL family; MinIO AGPL-3.0 | Free self-hosted; cloud S3 paid optional |
| Frontend | React + TypeScript + Vite | Vue, Svelte | MIT; TypeScript Apache-2.0 | Free |
| AuthN | OIDC via Keycloak | Any OIDC IdP (Authentik, cloud IdPs) | Keycloak Apache-2.0 | Free; commercial IdPs optional |
| Secrets | OpenBao | HashiCorp Vault | OpenBao MPL-2.0; Vault BUSL-1.1 (not OSI open source) | Free; Vault Enterprise/HCP paid |
| Policy engine | Open Policy Agent (Rego) | Cedar, hand-written Python rules | Apache-2.0 | Free |

### Execution and tooling concerns

| Concern | Proposed choice | Alternatives | License (re-verify at adoption) | Free vs paid |
|---|---|---|---|---|
| Sandbox isolation | Rootless Docker/Podman + gVisor `runsc` (MVP); Firecracker microVMs (Future) | Kata Containers, nsjail | gVisor Apache-2.0; Firecracker Apache-2.0; Podman Apache-2.0 | Free |
| LLM access | Provider-agnostic Model Gateway; local open-weight models via Ollama or vLLM, hosted APIs optional | Direct provider SDKs (rejected) | Ollama MIT; vLLM Apache-2.0; model weights vary | Local free license but compute cost; hosted APIs paid |
| Observability | OpenTelemetry, Prometheus, Grafana, Loki or OpenSearch | Jaeger, VictoriaMetrics | OTel/Prometheus Apache-2.0; Grafana/Loki AGPL-3.0; OpenSearch Apache-2.0 | Free; Grafana Cloud paid optional |
| Test runners | pytest, Jest/Vitest, Playwright, JUnit | Mocha, TestNG, Cypress | pytest MIT; Jest/Vitest MIT; Playwright Apache-2.0; JUnit 5 EPL-2.0 | Free |
| API testing | Schemathesis + Hypothesis; REST Assured optional | Dredd, Postman/Newman | Schemathesis MIT; Hypothesis MPL-2.0; REST Assured Apache-2.0 | Free |
| Security tools | Semgrep CE, Bandit, Gitleaks, OSV-Scanner, Trivy, Checkov, OWASP ZAP | CodeQL, Grype, TruffleHog | Semgrep engine LGPL-2.1 (rules under Semgrep Rules License, check terms); Bandit Apache-2.0; Gitleaks MIT; OSV-Scanner, Trivy, Checkov, ZAP Apache-2.0 | Free; commercial scanner tiers optional |
| Performance tools | k6 (default), Locust (alternative) | Gatling, JMeter | k6 AGPL-3.0 (separate process); Locust MIT | Free; k6 Cloud paid optional |
| Mutation tools | mutmut (Python), Stryker (JS/TS, C#, Scala), PIT (Java) | cosmic-ray, Major | mutmut BSD-3; Stryker Apache-2.0; PIT Apache-2.0 | Free |
| Reporting formats | JSON, HTML, PDF, SARIF 2.1.0, JUnit XML | Allure, CycloneDX VEX | Open formats; PDF renderer e.g. WeasyPrint BSD-3-Clause | Free |

## Rationale per concern

### Language, runtime and API framework

Python 3.12 is proposed because the MVP targets Python and JavaScript/TypeScript repositories, most test, security and LLM tooling exposes Python interfaces, and Pydantic models can serve as one source for API schemas, agent task contracts and output validation (SEC-015). FastAPI generates OpenAPI 3.1 from the same models, which keeps [API contracts](../08-api-specifications/01-api-contracts.md) and code aligned. Go remains an option for worker-host components if a lower footprint is needed. **Planned (MVP).**

### Workflow and task queue

The MVP is planned to use a PostgreSQL-backed state machine: tasks are rows, workers claim them with `SELECT … FOR UPDATE SKIP LOCKED`, and leases (90 s TTL, 30 s heartbeat), retry budgets and idempotency keys live in the same transactional store as job state. This removes a broker from the deployment and makes state transitions and audit events atomic. The trade-off is throughput ceiling and polling load; NFR-004 (≥ 10 concurrent jobs) is well within the expected range for this pattern, but this must be measured in Phase 1 rather than assumed. Temporal (MIT) is the **Future** escalation path if workflows become long-running with many timers or the queue becomes a bottleneck. Celery with Redis was rejected because state would be split across two stores.

### Database and object storage

PostgreSQL 16+ provides row-level security for tenant isolation (SEC-011), JSONB for bounded tool metadata, and partitioning for high-volume tables (see [Data model and ERD](../07-data-model/01-data-model-and-erd.md)). Evidence is stored in any S3-compatible service, content-addressed by SHA-256. SeaweedFS or Ceph RGW are proposed self-hosted defaults; cloud S3 is an optional paid adapter. MinIO is not excluded, but it is AGPL-3.0 and its open-source distribution model has changed over time, so operators should review it before adoption. The platform will only use the S3 API subset (put, get, head, lifecycle, presigned GET, object lock where available) so stores remain interchangeable.

### Frontend

React + TypeScript + Vite is proposed for the 15-screen SPA described in the [UI screen inventory](../02-prd-frd/03-ui-screen-inventory.md). TypeScript client types will be generated from the OpenAPI document to prevent contract drift. Accessibility (WCAG 2.2 AA, NFR-012) depends on component choice; an accessible headless component library is preferred over a styled framework. **Planned (MVP).**

### Authentication, secrets and policy

Authentication is delegated to an OIDC provider; Keycloak is the reference IdP so a self-hosted install needs no external account, and MFA is enforced at the IdP (SEC-009). Secrets are held by OpenBao, an MPL-2.0 fork of Vault, because HashiCorp Vault moved to BUSL-1.1, which is not OSI open source. Vault remains supported through the same Secrets Broker adapter for organizations that already run it. Policies are written in Rego and evaluated by Open Policy Agent, which allows policy-as-code review, unit tests for policies and a decision log that feeds the Audit Log. **Planned (MVP).**

### Sandbox isolation

The MVP is planned to run each task in a rootless container under gVisor `runsc`, with the hardening baseline from [Sandboxed execution](../10-security-and-threat-model/03-sandboxed-execution.md). gVisor intercepts system calls in a user-space kernel, which reduces host kernel exposure compared with plain containers, at the cost of compatibility gaps for some workloads; these will be tracked per worker image. Firecracker microVMs (or Kata Containers) are **Future** for hostile-code tenancy in multi-tenant deployments. Neither option is claimed to make escape impossible; isolation is one layer combined with network-off execution and short-lived workers.

### LLM access

All model calls go through the Model Gateway, which supports two adapter classes: hosted commercial APIs (paid, per-token) and local open-weight models served by Ollama or vLLM (free software license, but GPU or CPU compute cost and model-specific weight licenses that must be checked individually). The gateway applies prompt templating, redaction, token budgets and output schema validation regardless of provider, so changing a model never bypasses controls. Outputs from any model are treated as untrusted proposals and validated before use.

### Observability

OpenTelemetry SDKs in every service emit traces, metrics and logs with correlation IDs (NFR-014). Prometheus stores metrics; Grafana and Loki are AGPL-3.0 and are deployed as separate services, which is the common pattern; OpenSearch (Apache-2.0) is the alternative log store for organizations avoiding AGPL components. See [Observability and operations](../11-quality-gates-and-reporting/03-observability-and-operations.md).

### Test runners and API testing

Runner choice follows the target repository, not platform preference: pytest for Python, Jest or Vitest for JavaScript/TypeScript, Playwright for browser E2E, and JUnit for Java (Java support is **Future**, Phase 4). Schemathesis drives schema conformance and property-based API tests from OpenAPI 3.x, using Hypothesis underneath; REST Assured is an optional adapter for Java teams. Each runner is wrapped by an adapter that normalises results into the platform's status taxonomy (see [Integrations](06-integrations.md)).

### Security, performance and mutation tools

Security tools are grouped by profile (Quick, Standard, Deep). The Semgrep CE engine is LGPL-2.1, but its registry rules are distributed under the Semgrep Rules License, which restricts some uses; the platform will ship with a pinned, reviewed rule set and document the license terms rather than bundling registry rules by default. k6 is AGPL-3.0 and will only run as a separate process inside the sandbox worker, never imported into platform code; Locust (MIT) is the alternative where AGPL is not acceptable. Mutation tools are chosen per language: mutmut and Stryker in the MVP, PIT in **Future** with Java support. Every tool version is pinned in the worker image digest so results are reproducible (NFR-007).

### Reporting formats

JSON is the canonical report; HTML and PDF are rendered from it; SARIF 2.1.0 is exported for code-scanning integrations and JUnit XML for CI test reporters. NFR-019 (report generation ≤ 30 s for ≤ 10,000 test executions) is a target to be measured, not a known result.

## Running fully with free and open-source components

A reference self-hosted deployment is proposed to use only free/OSS components:

| Layer | OSS-only configuration | Optional paid adapter |
|---|---|---|
| Identity | Keycloak | Commercial OIDC IdP |
| Secrets | OpenBao | HashiCorp Vault Enterprise, cloud secret managers |
| Metadata | Self-managed PostgreSQL 16+ | Managed PostgreSQL |
| Evidence | SeaweedFS or Ceph RGW | Cloud S3 |
| Models | Ollama or vLLM with an open-weight model | Hosted LLM APIs |
| Observability | OpenTelemetry Collector, Prometheus, Grafana, Loki or OpenSearch | Hosted observability SaaS |
| CI trigger | Self-hosted Jenkins, GitLab CE runners or self-hosted GitHub runners | SaaS CI minutes |
| Load generation | k6 or Locust inside sandbox workers | Hosted load-testing services (not integrated in MVP) |

Two caveats apply. First, quality of LLM-assisted steps (scenario derivation, triage narratives, patch proposals) depends on the model; smaller local models may produce more `invalid_output` tasks or weaker proposals, which the platform will surface rather than hide. Deterministic stages (test execution, scanners, mutation, gates) do not depend on the model. Second, cost is the operator's responsibility: "free license" does not mean free to run.

## Cost awareness

### LLM tokens

Each job will carry a token budget enforced by the Model Gateway (NFR-015). When the budget is exhausted, remaining LLM-assisted tasks end `skipped` with a budget reason, the job ends `completed_with_warnings` if other work finished, and the report states which analyses were not performed. Cost drivers are scenario derivation over large diffs and specifications, triage of large scanner outputs and patch proposals; the design reduces them by sending bounded, redacted excerpts rather than whole repositories, and by caching outputs keyed by the task idempotency key so retried tasks do not repeat paid calls. Per-job and per-project usage will be reported; the platform will not estimate provider prices, because they change.

### Compute for local models

Local models shift spend from tokens to hardware: GPU memory, power and operator time. A CPU-only deployment is possible for small models but slows LLM-assisted stages and can push jobs towards the 4 h wall-clock default. Operators should size model serving separately from sandbox workers so a busy model server cannot starve test execution.

### Sandbox compute

The reference deployment assumes 8 workers × 2 vCPU (NFR-004). Reruns for flaky detection (up to 2 per failed test), reproduction runs (3 for confirmation), mutation (up to 500 mutants per job) and performance profiles are the main multipliers; resource budgets per job and per profile are enforced by the Policy Engine before work is scheduled.

### CI minutes

CI integration is designed so that heavy work runs on platform workers, not on CI runners. A CI job that polls for 4 h still consumes SaaS CI minutes, so the integration supports a short "submit and exit" mode with results reported back as commit statuses or check runs, in addition to "submit and wait" (see [Integrations](06-integrations.md)). Teams on metered CI should prefer the asynchronous mode.

## Open points

License of every component, including transitive dependencies, will be re-verified at adoption and tracked through the platform's own SBOM (SEC-020). The choice between Loki and OpenSearch, the reference open-weight model, and whether Temporal is needed are open and are tracked with other decisions in [Risks, limitations and decisions](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md).
