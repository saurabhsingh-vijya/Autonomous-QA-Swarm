# Observability and Operations

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This document describes how a self-hosted Autonomous QA Swarm deployment is proposed to be observed and operated: telemetry, dashboards, alerts and service-level objectives, cost tracking, capacity planning, backup and restore, upgrades, and a troubleshooting runbook. It targets operators running the reference deployment on a single Linux host (Docker Compose) or on Kubernetes (NFR-013). All items are **Proposed** or **Planned (MVP)**; none has the status **Implemented / Verified**. Numbers below are proposed starting points to be calibrated once the platform exists.

## Telemetry

Every platform service, including the API Gateway, Workflow Engine, Policy Engine, Source Intake Service, Execution Service, Target Environment Manager, Model Gateway, Secrets Broker integration and Notification Service, is planned to emit OpenTelemetry traces, metrics and logs with shared correlation identifiers (NFR-014). The Observability Stack is proposed as OpenTelemetry Collector, Prometheus, Grafana, and Loki or OpenSearch.

### Traces and correlation IDs

- Each API request starts or continues a W3C trace context. The trace ID is returned to clients in a response header to help support requests.
- Every span carries `org_id`, and where applicable `job_id`, `task_id`, `task_attempt`, `worker_run_id`, `agent_id` (for example `AG-08`) and `stage`. Display IDs such as `QJ-1042` are added as attributes for human search.
- A job has a long-lived root span; each task attempt is a child span linked to the job span, so a slow job can be broken down by stage, agent and attempt.
- Model Gateway calls are spans with model name, token counts, latency and prompt and response hashes. Prompt and response text are never stored as span attributes.
- Worker telemetry is collected by the Execution Service after the run from bounded output; workers have no network during execution and do not export telemetry directly.

### Metrics catalogue

Metric names follow Prometheus conventions with the prefix `aqs_`. Labels are kept low-cardinality: `org_id` is included only where the deployment has few organizations, and job or task IDs are never metric labels.

| Metric | Type | Labels | Meaning |
|---|---|---|---|
| `aqs_api_request_duration_seconds` | Histogram | route, method, status | API latency; source for NFR-001 |
| `aqs_jobs_total` | Counter | terminal_state, profile | Jobs reaching each terminal state |
| `aqs_job_start_latency_seconds` | Histogram | profile | Creation to first task `running`; NFR-002 |
| `aqs_jobs_active` | Gauge | state | Jobs per non-terminal state |
| `aqs_task_queue_depth` | Gauge | task_type | Tasks in `pending` or `retry_scheduled` |
| `aqs_task_attempts_total` | Counter | task_type, outcome | Attempts by outcome (`succeeded`, `failed_retryable`, `invalid_output`, `timed_out`) |
| `aqs_task_lease_expired_total` | Counter | task_type | Leases expiring without heartbeat |
| `aqs_worker_runs_active` | Gauge | pool | Running sandbox workers |
| `aqs_worker_cleanup_seconds` | Histogram | pool | Terminal state to worker destroyed; NFR-008 |
| `aqs_worker_orphans_reaped_total` | Counter | pool | Workers removed by the orphan reaper |
| `aqs_image_pull_failures_total` | Counter | image_name, reason | Worker image pull errors |
| `aqs_sse_connections` | Gauge | none | Open Server-Sent Events streams |
| `aqs_event_delivery_lag_seconds` | Histogram | event_type | State change to SSE emission; NFR-003 |
| `aqs_model_gateway_request_duration_seconds` | Histogram | provider, model, outcome | LLM call latency and timeouts |
| `aqs_llm_tokens_total` | Counter | provider, model, direction | Input and output tokens |
| `aqs_policy_decisions_total` | Counter | policy, decision | Allow and deny counts |
| `aqs_evidence_bytes_total` | Counter | evidence_type | Evidence bytes written |
| `aqs_evidence_store_used_ratio` | Gauge | bucket | Used fraction of evidence capacity |
| `aqs_evidence_digest_mismatch_total` | Counter | none | Integrity check failures on read |
| `aqs_audit_chain_verification_failures_total` | Counter | none | Hash-chain breaks detected |
| `aqs_report_generation_seconds` | Histogram | format | Report generation time; NFR-019 |
| `aqs_gate_overrides_total` | Counter | gate_id | HA-09 overrides recorded |

### Structured logs and redaction

Logs are JSON lines with a fixed envelope: `timestamp` (UTC), `level`, `service`, `trace_id`, `span_id`, `org_id`, optional `job_id`, `task_id`, `worker_run_id`, `event`, `message` and a bounded `attributes` object. Proposed rules:

- Redaction runs in the logging library and again in the OpenTelemetry Collector (SEC-008), using the same rule set as evidence redaction plus the values currently issued by the Secrets Broker.
- Authorization headers, cookies, tokens, credential references' resolved values and LLM prompt bodies are never logged.
- Live log tails on the Live Job Execution screen (SCR-04) show redacted worker output only.
- Platform logs are operational data and are kept separate from evidence; evidence lives in the Evidence Store and has its own chain of custody (see [Evidence and defect analysis](01-evidence-and-defect-analysis.md)).
- Proposed log retention is 30 days, shorter than evidence (90 days) and audit (1 year).

## Dashboards

Grafana dashboards are proposed to ship with the deployment templates:

- **Platform overview:** API latency and error rate, active jobs by state, queue depth, worker utilization, event delivery lag.
- **Job pipeline:** job outcomes by terminal state, stage durations, retry and lease-expiry rates, `invalid_output` rate per agent.
- **Execution plane:** worker starts, cleanup time, orphans reaped, image pull failures, resource saturation per pool.
- **Model Gateway:** latency, timeouts, token usage per model and project, budget utilization.
- **Evidence and data:** evidence growth, store capacity, digest mismatches, backup age, audit chain verification.
- **Quality signals:** infrastructure-error share (the QG-08 input), override counts, false-positive rate of Confirmed findings (NFR-010 input).

The in-product Dashboard (SCR-01) is a separate, user-facing view of QA health and is not a replacement for operator dashboards.

## Alerts and proposed SLOs

SLOs are derived from the non-functional requirements in [Non-functional requirements](../03-requirements/02-non-functional-requirements.md). They are proposed targets for the reference deployment; operators should adjust them to their hardware.

| SLO | Target | Source | Alert condition |
|---|---|---|---|
| Read API latency | p95 ≤ 300 ms at 50 concurrent users | NFR-001 | p95 > 300 ms for 10 min |
| Job start latency | ≤ 60 s to first running task (warm pool) | NFR-002 | p95 > 60 s for 15 min |
| Event delivery | ≤ 2 s state change to UI | NFR-003 | p95 lag > 2 s for 10 min |
| Control-plane availability | 99.5% monthly | NFR-005 | Error budget burn rate > 2× over 1 h |
| Worker cleanup | 100% within 60 s | NFR-008 | Any worker alive > 60 s after terminal state |
| Report generation | ≤ 30 s for ≤ 10,000 executions | NFR-019 | p95 > 30 s for 3 consecutive reports |
| Infrastructure health | ≤ 5% of tasks `infrastructure_error`/`timed_out` | QG-08 | Share > 5% over 1 h across jobs |

Additional proposed alerts without SLOs: any audit chain verification failure (page immediately), any evidence digest mismatch, evidence store above 80% used (warning) and 90% (critical), most recent successful backup older than 15 minutes for the database WAL archive, Secrets Broker sealed or unreachable, and any Policy Engine evaluation error (fail-closed means jobs block, which operators must know about).

## Cost and usage tracking

NFR-015 requires per-job LLM token budgets and compute budgets to be enforced and reported.

- **LLM tokens:** the Model Gateway counts input and output tokens per call and attributes them to org, project, job, task and agent. When a job reaches its token budget, further LLM-assisted tasks end `skipped` with reason `budget_exhausted`; deterministic tasks continue. Hosted-provider cost is estimated from an operator-maintained price table; local models record tokens and GPU time instead.
- **Compute:** the Execution Service records vCPU-seconds, memory GiB-seconds and wall-clock time per WorkerRun. Performance runs also record generator resources.
- **Storage:** evidence bytes per job and per project, with projected retention cost.
- **Reporting:** each job report includes a usage section; the Settings & Integrations screen (SCR-15) shows project budgets and month-to-date usage.

Cost is the operator's responsibility. The platform reports and enforces limits but does not bill.

## Capacity planning

The reference deployment for NFR-004 is 8 workers of 2 vCPU each supporting at least 10 concurrent jobs. A proposed sizing method:

1. Estimate tasks per job by profile from the JobPlan (a Functional Standard plus Security Standard plus Performance Baseline job might run tens of tasks).
2. Multiply average task duration by tasks per job to get worker-minutes per job.
3. Divide available worker-minutes per hour by worker-minutes per job to get sustainable jobs per hour; keep 20 to 30% headroom for reproduction runs and flaky reruns.
4. Size the Evidence Store from evidence bytes per job multiplied by jobs per day and by 90 days of retention, plus 30% margin.
5. Size Model Gateway capacity from tokens per job and provider rate limits; for local models, from tokens per second per GPU.

Workers scale horizontally without control-plane changes (NFR-011). The control plane (PostgreSQL task queue with `SELECT … FOR UPDATE SKIP LOCKED`) is expected to be the first scaling constraint at high task rates; the trigger for considering Temporal is captured as an open decision in [Risks, limitations and decisions](../12-risks-and-roadmap/01-risks-limitations-and-decisions.md).

## Backup and restore

NFR-006 requires no loss of committed job state or evidence on single-node failure, with RPO ≤ 15 minutes and RTO ≤ 4 hours.

| Data | Proposed backup method | RPO contribution |
|---|---|---|
| Metadata DB (PostgreSQL) | Continuous WAL archiving plus daily base backup | Minutes (WAL shipping interval ≤ 5 min) |
| Evidence Store | Replication to a second location or bucket versioning with object lock | Asynchronous replication ≤ 15 min |
| Audit Log | Stored in PostgreSQL and exported hourly to object storage with chain head digest | Covered by DB backup; export for independent verification |
| Secrets Broker | Backend snapshot per vendor guidance, encrypted | Daily plus on change |
| Configuration | Deployment manifests and policies in version control | Not runtime data |

Proposed restore procedure: restore PostgreSQL to the latest consistent point, verify the audit hash chain, reconcile EvidenceItem rows against stored objects (missing objects flagged, not silently deleted), mark tasks that were `leased` or `running` at failure time as `failed_retryable` so they resume within retry budgets, and destroy any surviving workers. A restore drill is proposed at least once per quarter, with the measured RTO recorded.

## Upgrades and migrations

- Releases follow semantic versioning with signed artifacts and SBOMs (SEC-020).
- Database migrations are forward-only and run before the new service version starts; each migration must be compatible with the previous service version for one release, allowing rolling upgrades.
- Worker images are pinned by digest. Upgrading a tool changes the image digest, which affects reproducibility (NFR-007); reports always record the digest used.
- Agent prompts, output schemas and adapters are versioned (NFR-017). A job records the versions it started with and keeps them until it finishes.
- Recommended procedure: drain (stop accepting new jobs), wait for active jobs or cancel them, back up, migrate, upgrade services, run a smoke job, resume.

## Troubleshooting runbook

| Symptom | Likely cause | Checks | Action |
|---|---|---|---|
| Job stuck in `queued` | No free workers, or Workflow Engine scheduler not running | `aqs_task_queue_depth`, `aqs_worker_runs_active`, scheduler logs | Scale worker pool; restart scheduler; check resource budgets |
| Job stuck in `validating` | Source Intake cannot reach Git provider or credential expired | Intake logs, `POST /repositories/{repository_id}/validate` result | Fix network or rotate credential (HA-11) |
| Job ends `blocked` | Policy denied: target not authorized or credential revoked | Policy decision log, AuditEvent for the job | Record authorization (HA-01) or fix credential, then create a new job |
| Frequent lease expiries | Worker host overloaded, heartbeat path congested, clock skew | `aqs_task_lease_expired_total`, host CPU, NTP status | Reduce concurrency; fix time sync; investigate network between workers and control plane |
| Image pull failures | Registry unreachable, digest missing, credentials for registry expired | `aqs_image_pull_failures_total`, registry logs | Pre-pull images to hosts; mirror registry; verify digest exists |
| High infrastructure error rate | Host disk full, sandbox runtime failure, gVisor incompatibility | Task error reasons, host disk, runtime logs | Fix host; isolate failing pool; rerun job (QG-08 will report INCONCLUSIVE until fixed) |
| Model gateway timeouts | Provider rate limit, outage, local GPU saturation | `aqs_model_gateway_request_duration_seconds`, provider status | Lower concurrency; switch to fallback model; raise timeout within limits |
| Many `invalid_output` tasks | Prompt or schema version mismatch, weak model | Validation error samples, schema version per task | Roll back prompt version; select stronger model; review schema change |
| SSE disconnects in UI | Proxy idle timeout, load balancer buffering | Proxy config, `aqs_sse_connections` drops | Disable buffering for `/jobs/{job_id}/events`; send keep-alive comments; client reconnects with last event ID |
| Evidence store full | Retention not running, unexpectedly large artifacts | `aqs_evidence_store_used_ratio`, retention job status | Run retention; add capacity; review video capture settings |
| Evidence digest mismatch | Storage corruption or tampering | `aqs_evidence_digest_mismatch_total`, object metadata | Treat as security incident; restore from replica; review audit trail |
| Orphan workers | Execution Service crash between run and destroy | `aqs_worker_orphans_reaped_total`, host container list | Confirm reaper runs every 5 min; destroy manually; investigate crash |
| Cancellation slow | Workers not responding to stop signal | Job in `cancelling`, worker runtime state | Force-kill after grace period; reaper confirms destruction |
| Report generation slow | Very large job, PDF rendering bottleneck | `aqs_report_generation_seconds` by format | Generate JSON first; scale renderer; paginate large sections |
| Performance runs marked invalid | Load generator CPU above 90% | Generator CPU metrics in PerformanceRun | Give generator its own worker; reduce VUs within profile |
| Dependency fetch fails | Registry not on egress allow-list | Egress proxy deny logs | Request allow-list entry (HA-04) or use a mirror |

## Operational security notes

Operators have privileged access to evidence and logs. Access to Grafana, log search and the Evidence Store console should require the same OIDC identity provider as the platform, and operator actions on evidence should be audited. See [Identity, secrets, audit and data protection](../10-security-and-threat-model/02-identity-secrets-audit-and-data-protection.md) and [Sandboxed execution](../10-security-and-threat-model/03-sandboxed-execution.md).
