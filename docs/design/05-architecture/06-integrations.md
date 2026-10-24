# Integrations

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document describes how Autonomous QA Swarm is proposed to integrate with Git providers, CI/CD systems, test frameworks, browsers, API specifications, observability tools, notification channels and issue trackers. Each integration carries a phase label (**Planned (MVP)** for Phases 1–3, **Future** for Phase 4+) and its security considerations. No integration is **Implemented / Verified** yet. All integrations are adapters behind versioned interfaces (NFR-017), configured on SCR-15 Settings & Integrations, and governed by FR-052. The overriding rule is the one from [System context](01-system-context.md): integrations may *read* source and *report* results; the platform never commits, pushes or merges code (FR-041).

## Integration principles

1. **Read-only to source.** Git credentials are scoped to read repository contents and metadata, plus write access only to commit statuses or check runs. Posting a status is allowed; pushing code is not.
2. **Credentials by reference.** Every token is stored in the Secrets Broker; the Metadata DB holds only a CredentialReference. Registering or rotating credentials requires HA-11 (Org Admin).
3. **Inbound events are untrusted.** Webhook payloads are authenticated, schema-validated and only ever cause the platform to *create a job request* through the same Policy Engine path as a user action.
4. **Outbound calls are allow-listed.** Notification and integration egress goes through the control plane's egress allow-list, never from sandbox workers.
5. **Results are normalized.** Tool-specific outputs are mapped to the platform's status taxonomy and finding model before any agent or gate consumes them.

## Integration overview

| Integration | Direction | Phase | Credential type | Key security control |
|---|---|---|---|---|
| GitHub | Inbound webhooks, outbound read + status | Planned (MVP) | GitHub App installation token | Minimal App permissions, webhook HMAC |
| GitLab | Inbound webhooks, outbound read + status | Planned (MVP) | Project/group access token, `read_repository` + `read_api` | Secret token header, scoped token |
| GitHub Actions | CI calls platform | Planned (MVP) | CI Service Account token | Short-lived OIDC exchange preferred |
| GitLab CI | CI calls platform | Planned (MVP) | CI Service Account token | Masked, protected variable |
| Jenkins | CI calls platform | Planned (MVP) | CI Service Account token | Jenkins credentials store |
| Test frameworks | Inside sandbox | Planned (MVP) | None | Runner adapters, output size limits |
| Playwright browsers | Inside sandbox | Planned (MVP) | None | Network off, pinned images |
| OpenAPI 3.x | Import | Planned (MVP) | None or Git read | Spec treated as untrusted data |
| OTel / Prometheus / Grafana | Outbound telemetry | Planned (MVP) | Collector credentials | Redaction before export |
| Slack / Teams / email | Outbound notifications | Planned (MVP) | Webhook URL or SMTP credential | No secrets or code in payloads |
| Generic webhooks | Outbound | Planned (MVP) | Shared HMAC secret | HMAC-SHA256 signatures, replay window |
| Jira / GitHub Issues | Outbound, human-triggered | Future | Scoped API token | Human trigger only, preview before send |

## Git providers

### GitHub (GitHub App)

**Planned (MVP).** The platform is proposed to integrate with GitHub as a GitHub App installed per organization or per repository. Requested permissions are deliberately minimal:

| Permission | Level | Why |
|---|---|---|
| Contents | Read | Fetch the pinned commit for the source snapshot |
| Metadata | Read | Resolve default branch, refs, repository visibility |
| Pull requests | Read | Resolve PR head SHA and changed files for change-impact analysis |
| Commit statuses | Read and write | Post `pending`, `success`, `failure`, `error` statuses |
| Checks | Read and write | Post check runs with summary and annotations |

Contents write, Workflows, Administration and Secrets permissions are never requested. The Source Intake Service requests a short-lived installation token from the Secrets Broker at intake time, clones the exact commit into a read-only snapshot (tarball + SHA-256) and discards the token. Public repositories may be read without a token, still through SSRF-safe URL validation (FR-001, SEC-002).

**Webhooks.** The App subscribes to `pull_request` (opened, synchronize, reopened), `push` on configured branches and `installation` events. Each delivery is verified with the `X-Hub-Signature-256` HMAC header using a secret held in the Secrets Broker; deliveries are deduplicated by `X-GitHub-Delivery` id. A valid PR event is converted into a job request with the PR head SHA pinned, the project's default profiles and an idempotency key derived from repository, SHA and profile hash, so redelivered webhooks never create duplicate jobs (FR-006).

**Reporting.** The platform will create a check run per job ("Autonomous QA Swarm"), updated as the job progresses, with the release-readiness verdict as the conclusion: `READY` → success, `READY_WITH_RISKS` → neutral by default (configurable to success), `NOT_READY` → failure, `INCONCLUSIVE` → neutral or action_required. Annotations are generated from Confirmed and Probable findings with file locations, capped at 50 per check run, linking to SCR-11 for evidence. Where check runs are unavailable, a commit status with a target URL to the report is posted instead.

### GitLab (access tokens)

**Planned (MVP).** GitLab.com and self-managed GitLab are supported with a project or group access token carrying `read_repository` and `read_api`. Commit status reporting needs the `api` scope on GitLab, which is broader than ideal; the design therefore proposes a second, separately stored reporter token with the Reporter or Developer role limited to the target project, used only for the commit status endpoint. Webhooks for merge request and push events are authenticated with the `X-Gitlab-Token` secret, compared in constant time.

### Git provider security considerations

- Self-managed provider URLs pass the same SSRF checks as repository URLs: HTTPS only, DNS pinned, private and metadata addresses rejected unless an Org Admin has explicitly allow-listed an internal Git host.
- Webhook endpoints accept only expected event types, enforce a payload size limit (proposed 1 MiB) and are rate-limited per installation (SEC-022).
- PR titles, branch names and commit messages are treated as untrusted data (SEC-014); they are never interpolated into commands and are escaped in UI and prompts.
- PRs from forks are not run automatically by default; a QA Lead must approve a fork-triggered job, because fork content may be crafted to attack the pipeline.

## CI/CD systems

### Common pattern

CI systems call the platform rather than the platform calling CI. A pipeline step authenticates as a CI Service Account, creates a job with `POST /jobs` and an `Idempotency-Key`, then either waits or exits:

1. **Submit and wait.** The step polls `GET /jobs/{job_id}` with backoff (proposed 15 s start, 60 s max) or follows `GET /jobs/{job_id}/events`, until a terminal state or a CI-side timeout.
2. **Submit and exit.** The step exits after `202 Accepted`; results arrive later as a commit status or check run, or via an outbound webhook that can trigger a downstream pipeline.

On completion the step downloads `GET /jobs/{job_id}/report?format=junit` and `?format=sarif` and publishes them with the CI system's native test and code-scanning reporters. Optionally the step fails the pipeline when the verdict is `NOT_READY` (and, if configured, `INCONCLUSIVE`). This is an advisory build signal; the release decision itself is still recorded by a human under HA-10.

The CI Service Account role can create jobs, read jobs, reports and quality gates, and nothing else: it cannot triage findings, approve patches, approve plans, override gates or record release decisions.

### GitHub Actions

**Planned (MVP).** A composite action is proposed. Preferred authentication is a GitHub OIDC token exchanged at the platform for a short-lived CI Service Account token bound to the repository and workflow; a long-lived token stored as an encrypted repository secret is the fallback.

```yaml
- name: Autonomous QA Swarm
  uses: qa-swarm/submit-job@v1   # illustrative name
  with:
    api-url: https://qa.example.internal/api/v1
    repository-id: rep_01JB8Q2W6V3K9X4M7N5P2R8T1A
    ref: ${{ github.sha }}
    profiles: functional:standard,security:standard
    mode: wait
    fail-on: NOT_READY
```

### GitLab CI

**Planned (MVP).** A reusable CI template uses the same parameters; the CI Service Account token is stored as a masked, protected CI/CD variable so it is only exposed on protected branches. JUnit output is published through `artifacts:reports:junit`; SARIF can be published as a job artifact or converted to GitLab's security report format in a later phase.

### Jenkins

**Planned (MVP).** A shared library step (`qaSwarmSubmit`) is proposed for declarative pipelines on Linux or Windows agents. The token is held in the Jenkins credentials store and injected with `withCredentials`, never echoed. The step publishes JUnit through the `junit` step and SARIF through a warnings or code-scanning plugin of the operator's choice. In wait mode the step should run on a lightweight agent, because platform jobs can take up to the 4 h default wall clock.

### CI security considerations

- CI tokens are scoped per project, rotated under HA-11 and revocable; revocation of a token mid-job does not cancel the job but blocks further API calls.
- `force_new=true` is unavailable to CI Service Accounts (QA Lead only), so a retrying pipeline cannot bypass duplicate prevention.

## Test frameworks

**Planned (MVP)** for pytest, Jest, Vitest and Playwright; **Future** (Phase 4) for JUnit 5 with Java support. Each framework is wrapped by a runner adapter executed inside the sandbox worker. The adapter declares how to discover tests, how to run a selected subset, how to emit machine-readable results (pytest `--junitxml`, Jest/Vitest JUnit reporters or JSON, Playwright JSON reporter, JUnit XML from Surefire) and which artifacts to collect.

### Result normalization

Results are normalized to the status taxonomy of TestExecution before any agent sees them:

| Framework outcome | Normalized status | Notes |
|---|---|---|
| Pass | `passed` | |
| Assertion failure or error in test body | `failed` | Rerun up to 2 times in fresh workers; pass on rerun → `flaky` |
| Skip, xfail-as-expected, `test.skip`, `@Disabled` | `skipped` | Skip reason recorded |
| Fixture or setup cannot run due to missing authorized target or policy | `blocked` | Counts against QG-04 coverage |
| Per-test or per-task timeout exceeded | `timed_out` | Counts towards QG-08 |
| Runner crash, OOM kill, image pull or worker loss | `infrastructure_error` | Retried as infrastructure, not as a defect |

Ambiguous setup-versus-test errors are recorded as `failed` with an adapter note so they are never silently excluded. Output beyond the 50 MiB per-task cap is truncated with a marker and the truncation is shown in the report.

### Security considerations

Test suites are repository code and therefore untrusted. They run only in sandbox workers with network off during execution (SEC-004), never on the control plane (SEC-001). Adapter parsers treat result files as untrusted input, enforce size and depth limits, and reject XML external entities.

## Browsers

**Planned (MVP).** UI and E2E tests run with Playwright's bundled Chromium, Firefox and WebKit inside the sandbox worker image, pinned by image digest (SEC-006). Browsers run headless as the non-root worker UID under gVisor; the application under test is started by the Target Environment Manager inside the same isolated network namespace, so browser traffic reaches only the ephemeral target. Screenshots, videos and traces are captured as content-hashed EvidenceItems. WebKit compatibility under gVisor is a known risk to validate in Phase 1; if a browser cannot run, its tests end `infrastructure_error` rather than being dropped.

## API specifications

**Planned (MVP).** OpenAPI 3.0 and 3.1 documents are imported from the repository snapshot or uploaded by a user. The Requirements Analysis Agent derives scenarios from operations, and the API Testing Agent drives Schemathesis against an ephemeral target in the sandbox, or against a registered non-production target authorized under HA-01. Imported specs are treated as untrusted: remote `$ref` resolution is disabled by default (it would be an SSRF vector), document size is capped, and server URLs in the spec are ignored in favour of the authorized target's base URL. GraphQL and gRPC are **Future**.

## Observability tools

**Planned (MVP).** Platform services export OpenTelemetry traces, metrics and logs to an OTel Collector, from which operators route data to Prometheus, Grafana, Loki or OpenSearch. Correlation IDs link API requests, jobs, tasks and worker runs (NFR-014). A Prometheus scrape endpoint exposes queue depth, lease expiries, task outcomes by status, worker pool utilization and Model Gateway token usage; a reference Grafana dashboard is proposed. Target metrics during performance runs may be read from an operator-provided Prometheus endpoint with a read-only credential, for authorized targets only. Telemetry passes through redaction processors before export (SEC-008), and prompt and response bodies are never exported, only their hashes. See [Observability and operations](../11-quality-gates-and-reporting/03-observability-and-operations.md).

## Notifications

**Planned (MVP).** The Notification Service sends events to Slack (incoming webhook or bot token), Microsoft Teams (Workflows webhook), email (SMTP) and generic HTTPS webhooks. Subscribable events include job state changes, approval requests (HA-02, HA-03, HA-05, HA-06), new Confirmed Critical or High findings, quality-gate verdicts and verification results. Messages carry identifiers, severity, verdict and a link back to the relevant screen; they never carry secrets, source code excerpts, evidence content or prompt text.

### Webhook signing

Generic webhooks are signed with HMAC-SHA256 using a per-subscription secret held in the Secrets Broker. The signature covers the timestamp and body, and receivers should reject messages older than 5 minutes to limit replay:

```http
POST /hooks/qa HTTP/1.1
Content-Type: application/json
X-QASwarm-Event: job.completed
X-QASwarm-Delivery: dlv_01JB9C4D7F2G6H8J3K5M9N1P4Q
X-QASwarm-Timestamp: 1761300000
X-QASwarm-Signature: sha256=5d1f…e9a0
```

The signature is `HMAC_SHA256(secret, timestamp + "." + raw_body)`, hex-encoded. Failed deliveries are retried with exponential backoff (proposed 5 attempts over about 30 minutes) and then marked failed on the subscription. The payload format is defined in [API contracts](../08-api-specifications/01-api-contracts.md).

### Notification security considerations

Destination URLs are validated against SSRF rules and an Org Admin-managed allow-list; redirects are not followed. Chat messages escape user-controlled fields to prevent mention or markup injection.

## Issue trackers

**Future**, human-triggered only. Exporting a Confirmed finding to Jira or GitHub Issues will be an explicit action by a QA Engineer, QA Lead or Security Reviewer from SCR-11. The user sees a preview of the exact title and body before sending; the body contains the finding summary, severity, confidence, DCS, reproduction steps and a link to evidence in the platform, not raw evidence files. Security findings default to a restricted project or private issue and require Security Reviewer action. The platform will never open or close tickets automatically, and the export is recorded as an AuditEvent.

Automatic pull request creation for patches or generated tests (HA-12) is likewise **Future** and requires Developer (code owner) approval each time.
