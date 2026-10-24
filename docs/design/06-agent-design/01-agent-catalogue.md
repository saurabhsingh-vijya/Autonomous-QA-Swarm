# Agent Catalogue

> Autonomous QA Swarm · Documentation v0.1 (Concept) · Status: Proposed — nothing described here is implemented yet.

This catalogue specifies the eleven proposed agents of Autonomous QA Swarm (AG-01 to AG-11): what each is for, what it may read and emit, what it is explicitly denied, how its output is validated, how it fails, which human approvals constrain it and in which roadmap phase it is planned. It is the reference for agent permissions shown on SCR-05 (Agent Collaboration Graph) and SCR-15 (Settings & Integrations). Orchestration mechanics are in [Orchestration and recovery](02-orchestration-and-recovery.md); answers to cross-cutting design questions are in [Key design questions](03-key-design-questions.md). Nothing here is implemented; every agent is **Proposed**, and its phase indicates whether it is **Planned (MVP)** or **Future**.

## Agent versus deterministic service split

The platform's core principle is **"Agents propose, deterministic services dispose, humans approve."** The split is deliberate: language models are good at reading requirements, choosing what to test, explaining failures and drafting fixes, but they are non-deterministic, can be manipulated by untrusted repository content and cannot be held accountable. The design therefore confines them to producing **typed proposals**.

| Concern | Handled by agents | Handled by deterministic services |
|---|---|---|
| Deciding what to test | Propose scenarios, test selections, workloads | Policy Engine validates scope, budgets, targets |
| Running anything | Never | Execution Service in Sandbox Workers |
| Credentials | Never seen | Secrets Broker issues short-lived tokens to services only |
| Results and scores | Explain, correlate, summarize | Test runners, scanners, DCS calculator, gate evaluator |
| State changes | Request only | Workflow Engine state machines, human approvals |
| Repository changes | Propose a diff | None: no commit, push or merge (FR-041) |

Every agent call goes through the Model Gateway, which applies prompt templates, redaction (SEC-008), token budgets (NFR-015) and output schema validation (SEC-015), and logs prompt/response hashes. Every agent output is stored as an AgentOutput record with provenance (agent ID, template version, model route, input hashes) and is treated as untrusted until it passes schema validation and deterministic checks. Repository content is always passed to agents as delimited, untrusted data (SEC-014). An agent opinion alone can never lift a finding to Confirmed ("No evidence, no defect").

Common rules apply to all agents and are not repeated below: no secrets, no network egress, no code execution, no approval rights, maximum 1 corrective retry after invalid output then `invalid_output`, maximum 2 retries for transient errors, lease TTL 90 s with 30 s heartbeat.

## AG-01 Orchestrator Agent

**Kind:** Deterministic Workflow Engine plus LLM-assisted planner · **Stages:** 2 Planning and all stage transitions · **Phase:** 1, Planned (MVP)

**Purpose.** Turn a validated job request into an executable plan (DAG) and drive it to a terminal state.

**Responsibilities**

- Build the job plan from profiles, scope, change-impact output and scenario list; the LLM planner only proposes ordering and selection within a fixed task-type catalogue.
- Run the job and task state machines, leases, retries, timeouts and cancellation.
- Enforce dependencies, parallelism limits and the job resource and token budget.

**Inputs**

- `job` (Job) — profiles, scope, budgets, limits, pinned commit SHA.
- `source_snapshot` (SourceSnapshot ref) — file tree and diff statistics only, not file contents.
- `scenarios` (TestScenario list) — output of AG-02 after validation.
- `policy_version` (string) — the policy bundle the job is pinned to.

**Outputs**

- `job_plan` (JobPlan) — DAG of tasks with type, dependencies, budget and idempotency key.
- `tasks` (Task list) — enqueued in `pending`.
- `state_events` (event stream) — job and task transitions for `GET /jobs/{job_id}/events`.

**Allowed tools/actions:** create JobPlan and Task rows; call the Model Gateway for plan proposals; request Policy Engine evaluation.

**Explicitly denied:** adding task types outside the catalogue; raising budgets above profile caps; leasing execution tasks while the job is `awaiting_approval`; any approval.

**Boundaries:** The deterministic Workflow Engine is authoritative; the planner's suggestions are discarded if invalid and the default plan template for the selected profiles is used instead.

**Validation:** JSON schema of the plan; acyclicity check; every node's task type in the catalogue; every dependency resolvable; total budget within job limits; Policy Engine evaluation of each task contract.

**Failure modes and handling:** planner invalid twice → fall back to the deterministic template plan and record a warning; LLM outage → template plan; control-plane restart → resume from persisted state (see orchestration document).

**Human gates:** HA-05 (plan approval when enabled); HA-03 and HA-02 approvals are collected before dependent tasks are leased.

## AG-02 Requirements Analysis Agent

**Kind:** LLM agent · **Stage:** 2 Planning · **Phase:** 2, Planned (MVP)

**Purpose.** Convert requirements, user stories, OpenAPI specifications and the change diff into testable, prioritized scenarios and acceptance criteria (FR-013, FR-014).

**Responsibilities**

- Extract Requirement records from linked documents and OpenAPI operations.
- Derive TestScenario records with P0/P1/P2 priority and expected oracle type.
- Map the diff to affected modules and existing tests (change-impact analysis).
- Report ambiguous or untestable requirements explicitly.

**Inputs**

- `requirements_sources` (document refs) — stories, acceptance criteria, specs from the snapshot or uploaded.
- `openapi_document` (file ref) — parsed by a deterministic parser first.
- `diff` (unified diff) — pinned commit versus base ref.
- `test_inventory` (TestCase list) — produced by deterministic test discovery.

**Outputs**

- `requirements` (Requirement list) — with source location.
- `scenarios` (TestScenario list) — ID, title, priority, linked requirement, oracle type.
- `impact_map` (module → tests map) — with rationale text.
- `gaps` (list) — requirements flagged ambiguous or untestable.

**Allowed tools/actions:** read snapshot documentation, specs and diff; call the Model Gateway.

**Explicitly denied:** proposing execution tasks directly; editing requirements; reading evidence.

**Boundaries:** Scenarios only become tasks through AG-01 and the Policy Engine.

**Validation:** schema; every scenario links to an existing Requirement or OpenAPI operation ID; every referenced test exists in the deterministic inventory; every referenced module path exists in the snapshot; priority is a valid enum.

**Failure modes and handling:** invalid twice → `invalid_output`, plan falls back to "run all existing suites on changed paths"; hallucinated references are removed by validation and counted in AgentOutput diagnostics.

**Human gates:** none directly; scenarios are visible in the plan reviewed under HA-05.

## AG-03 Functional Testing Agent

**Kind:** LLM agent plus deterministic runners · **Stages:** 4 Baseline Run, 5 Functional & API Testing · **Phase:** 1 (existing suites), 2 (generated tests), Planned (MVP)

**Purpose.** Select and, where useful, draft functional tests (unit, integration, UI/E2E), and request their execution (FR-015 to FR-018).

**Responsibilities**

- Propose execution of existing suites (pytest, Jest/Vitest, Playwright) for the Baseline Run.
- Select scenario-relevant tests and draft candidate tests with provenance.
- Request reruns for failures to support flaky classification.

**Inputs**

- `scenarios` (TestScenario list) — validated.
- `test_inventory` (TestCase list) — discovered deterministically.
- `snapshot` (SourceSnapshot ref) — read-only.
- `prior_results` (TestExecution list) — for rerun decisions.

**Outputs**

- `execution_proposals` (task contract list) — runner, test IDs, image digest, limits.
- `generated_tests` (TestCase list) — source text, provenance, `review_status=unreviewed`.
- `signals` (raw failure signal list) — for AG-08.

**Allowed tools/actions:** read snapshot; propose execution tasks; call Model Gateway; read its own TestExecution results.

**Explicitly denied:** running code itself; marking results passed or failed; promoting generated tests; changing flaky classification.

**Boundaries:** Test statuses come only from runner output parsed by the Execution Service. Generated tests run in the sandbox as advisory and never count toward QG-03 until reviewed.

**Validation:** schema; runner and image digest from the allowed list; test IDs exist; generated test files restricted to test directories; limits within sandbox defaults (2 vCPU, 4 GiB, 30 min).

**Failure modes and handling:** invalid output → corrective retry then `invalid_output` (existing suites still run from the template plan); worker infrastructure errors handled by the Execution Service retry budget.

**Human gates:** review of generated tests before promotion (FR-016); HA-12 for exporting generated tests as a pull request (Future).

## AG-04 API Testing Agent

**Kind:** LLM agent plus deterministic runners · **Stage:** 5 Functional & API Testing · **Phase:** 2, Planned (MVP)

**Purpose.** Test API schema conformance, authentication, object-level authorization and negative or property-based inputs against an authorized target (FR-019 to FR-021).

**Responsibilities**

- Generate Schemathesis/OpenAPI-driven test configurations.
- Design authz checks using two or more scoped test identities.
- Propose boundary values derived from schema constraints.

**Inputs**

- `openapi_document` (parsed spec) — operations, schemas, security schemes.
- `target` (TargetEnvironment ref) — ephemeral or authorized; base URL only.
- `test_identities` (identity labels) — names of test users; credential values are injected by the Secrets Broker into the worker, never into the agent.
- `scenarios` (TestScenario list) — API-related subset.

**Outputs**

- `execution_proposals` (task contract list) — tool, operations, request budget.
- `signals` (raw signal list) — schema violations, unexpected status codes, authz anomalies.

**Allowed tools/actions:** read snapshot and spec; propose execution tasks; call Model Gateway; read its own results.

**Explicitly denied:** contacting any host other than the bound target; destructive methods against external targets unless the target is ephemeral; seeing credential values.

**Boundaries:** Non-destructive by default; checks stop at proof of reachability (SEC-018).

**Validation:** schema; operations exist in the spec; target ID has active TargetAuthorization; request budget within profile; HTTP methods within the target's allowed set.

**Failure modes and handling:** target unhealthy → tasks `blocked` with reason; invalid output → template configuration (schema conformance only).

**Human gates:** HA-01 for external targets; HA-11 for target credentials.

## AG-05 Security Testing Agent

**Kind:** LLM agent plus deterministic scanners · **Stage:** 6 Security Testing · **Phase:** 2 (Quick profile and Standard's API checks), 3 (Standard's IaC/configuration scanning, FR-025), 4 (Deep profile with DAST); Planned (MVP) and Future

**Purpose.** Orchestrate SAST, SCA, secret detection, IaC/config checks and, when authorized, DAST, and triage scanner output (FR-022 to FR-026).

**Responsibilities**

- Select scanners and rule sets for the profile (Semgrep CE, Bandit, Gitleaks, OSV-Scanner, Trivy, Checkov, OWASP ZAP).
- Propose reachability or precondition checks for scanner alerts.
- Suggest likely false positives with reasons, for human decision.

**Inputs**

- `security_profile` (enum Quick, Standard, Deep).
- `snapshot` (SourceSnapshot ref).
- `scanner_results` (normalized SARIF) — from deterministic scanners.
- `suppressions` (Suppression list) — active scoped suppressions.

**Outputs**

- `execution_proposals` (task contract list) — scanner, version, rules.
- `triage_notes` (per-alert notes) — reachability hypothesis, suggested source class.
- `signals` (raw signal list) — for AG-08.

**Allowed tools/actions:** read snapshot; propose scanner and check tasks; call Model Gateway; read scanner results.

**Explicitly denied:** promoting any alert beyond "Probable vulnerability" on its own; marking false positives; creating suppressions; exploitation beyond reachability proof; DAST without HA-02.

**Boundaries:** Detected secrets are redacted before any prompt; no profile is presented as comprehensive coverage.

**Validation:** schema; scanner and version in the profile's allowed list; DAST tasks require HA-01, HA-02 and HA-05 records and a 60 min bound; triage notes cannot set status fields.

**Failure modes and handling:** scanner crash → `infrastructure_error` with retries; agent failure → raw scanner alerts still flow to AG-08 as Scanner alert / Candidate.

**Human gates:** HA-01, HA-02, HA-05, HA-07, HA-08.

## AG-06 Performance Testing Agent

**Kind:** LLM agent plus deterministic load tools · **Stage:** 7 Performance Testing · **Phase:** 3 (Smoke, Baseline), 4 (Load and above)

**Purpose.** Plan and run bounded workloads and analyze metrics against thresholds and baseline (FR-027 to FR-029).

**Responsibilities**

- Propose k6 (or Locust) scripts and workload shapes within profile caps.
- Analyze percentiles, error rates and baseline deltas; flag sample-size limits.
- Explain likely causes of regressions as hypotheses.

**Inputs**

- `performance_profile` (enum Smoke to Soak) — with caps.
- `target` (TargetEnvironment ref).
- `thresholds` (per-endpoint p95, error rate).
- `baseline` (PerformanceRun ref) — previous accepted baseline.

**Outputs**

- `workload_proposal` (task contract) — VUs, ramp, duration, endpoints.
- `analysis` (structured) — per-endpoint comparison, warnings, hypotheses.
- `signals` (raw signal list) — threshold breaches.

**Allowed tools/actions:** propose load tasks; call Model Gateway; read PerformanceMetric data.

**Explicitly denied:** exceeding caps; disabling abort rules; targeting unauthorized hosts; declaring a breach without measured metrics.

**Boundaries:** Automatic abort (error rate > 20% for 60 s, 3 failed health checks, p95 > 5× baseline for 2 min, generator CPU > 90%) is enforced by the Execution Service, not the agent.

**Validation:** schema; workload ≤ profile cap; duration ≤ cap; approvals present; numeric claims in analysis must match stored metrics.

**Failure modes and handling:** aborted run → recorded with reason; generator-bound → run invalid; agent failure → deterministic comparison still produced without narrative.

**Human gates:** HA-03; HA-05 for Stress, Spike and Soak; HA-01 for external targets.

## AG-07 Mutation Testing Agent

**Kind:** Deterministic tool wrapper plus LLM analysis · **Stage:** 8 Mutation Testing · **Phase:** 3, Planned (MVP)

**Purpose.** Run mutation tools on changed modules, compute a valid score and explain surviving mutants (FR-030, FR-031).

**Responsibilities**

- Configure mutmut (Python) or Stryker (JS/TS) for changed modules; PIT is Future for Java.
- Explain survivors and suggest assertions; flag equivalent-mutant suspicion.

**Inputs**

- `changed_modules` (path list) — from deterministic diff analysis.
- `baseline_test_time` (duration) — for per-mutant timeout.
- `mutant_results` (MutantResult list) — from the tool.

**Outputs**

- `mutation_proposal` (task contract) — tool, modules, mutant cap.
- `survivor_analysis` (per-mutant notes) — explanation, suggested assertion, equivalence suspicion.

**Allowed tools/actions:** read snapshot; propose mutation tasks; call Model Gateway for analysis.

**Explicitly denied:** computing the score; marking mutants equivalent (humans do); exporting mutants outside the sandbox.

**Boundaries:** Score = killed / (killed + survived) × 100, computed deterministically over valid, completed mutants; maximum 500 mutants; per-mutant timeout 2 × baseline + 10 s.

**Validation:** schema; modules ⊆ changed modules; mutant IDs in analysis exist; suggestions marked unreviewed.

**Failure modes and handling:** failing baseline → stage `skipped`; timeouts → excluded and reported; agent failure → score still reported without explanations.

**Human gates:** review of suggested tests; QG-06 is advisory.

## AG-08 Evidence and Defect Analysis Agent

**Kind:** LLM agent plus deterministic correlator · **Stage:** 9 Evidence Correlation & Triage · **Phase:** 1 (evidence capture), 2 (correlation), Planned (MVP)

**Purpose.** Turn raw signals into deduplicated, evidence-backed findings with confidence, and reconcile conflicting conclusions (FR-032 to FR-036).

**Responsibilities**

- Normalize signals, compute fingerprints, merge exact duplicates, suggest near duplicates.
- Request reproduction runs in fresh sandboxes.
- Apply the precedence order for conflicts and flag Disputed findings.

**Inputs**

- `signals` (raw signal list) — from AG-03 to AG-07.
- `evidence_items` (EvidenceItem refs) — content-addressed.
- `flaky_register` (FlakyTestRecord list).
- `existing_findings` (Finding list) — for deduplication.

**Outputs**

- `findings` (Finding list) — in `candidate` or `triaging`, with evidence links.
- `reproduction_proposals` (task contract list).
- `correlation_notes` (structured) — rationale, suspected relations.

**Allowed tools/actions:** read evidence and snapshot; write findings in non-terminal statuses; propose reproduction tasks; call Model Gateway.

**Explicitly denied:** setting `false_positive`, `accepted_risk` or Confirmed directly; computing DCS; deleting evidence.

**Boundaries:** DCS and level mapping (Confirmed ≥ 80 and reproduced) are deterministic. LLM judgement ranks lowest in the precedence order.

**Validation:** schema; every evidence reference resolves to a stored SHA-256 object; fingerprints recomputed deterministically; reproduction contracts reuse the original task's inputs.

**Failure modes and handling:** agent failure → deterministic correlator still fingerprints and links signals; findings stay Candidate; Evidence Store unavailable → no promotion.

**Human gates:** HA-07, HA-08; Disputed findings go to human triage.

## AG-09 Patch Proposal Agent

**Kind:** LLM agent · **Stage:** 10 Patch Proposal · **Phase:** 3, Planned (MVP)

**Purpose.** Propose minimal diffs for Confirmed findings, for human review only (FR-038, FR-041).

**Responsibilities**

- Draft a diff, rationale, risk notes and, where possible, a regression test.
- Link the patch to the finding's evidence.

**Inputs**

- `finding` (Finding) — Confirmed only.
- `evidence_items` (EvidenceItem refs) — the finding's evidence.
- `snapshot` (SourceSnapshot ref) — relevant files.

**Outputs**

- `patch` (Patch) — unified diff, rationale, risk notes, status `proposed`.

**Allowed tools/actions:** read snapshot and the finding's evidence; call Model Gateway; write Patch records.

**Explicitly denied:** commit, push, merge, branch creation; running the patch; changing finding status; editing CI configuration or deleting tests without an explicit reviewer flag.

**Boundaries:** Its reasoning is stored but never shown to AG-10.

**Validation:** schema; diff parses; touched paths exist in the snapshot; dry-run apply check in a sandbox; deterministic flags for deleted assertions, deleted tests, or changes to build/CI files.

**Failure modes and handling:** invalid twice → `invalid_output`; finding remains `confirmed` with no patch.

**Human gates:** HA-06; HA-12 for exporting as a pull request (Future).

## AG-10 Independent Verification Agent

**Kind:** Deterministic service plus LLM summary · **Stage:** 11 Independent Verification · **Phase:** 3, Planned (MVP)

**Purpose.** Re-run relevant checks on the pinned commit plus the approved patch in a fresh sandbox and produce a verdict (FR-040).

**Responsibilities**

- Select the original reproduction and relevant functional, API, security and performance checks.
- Compare original and patched results; state what was not re-run and why.

**Inputs**

- `patch_diff` (Patch diff only) — no rationale or reasoning.
- `snapshot` (SourceSnapshot ref).
- `original_evidence` (EvidenceItem refs) — reproduction recipe.

**Outputs**

- `verification_run` (VerificationRun) — results, fresh-sandbox metadata.
- `verdict` (enum `verified`, `verification_failed`) — deterministic.
- `summary` (text) — LLM narrative citing result IDs.

**Allowed tools/actions:** propose verification tasks; read evidence of the original finding; call Model Gateway for summary.

**Explicitly denied:** reading AG-09 rationale or prompts; altering the patch; reusing workers from the original job.

**Boundaries:** Verdict logic is deterministic; the summary cannot change it.

**Validation:** schema; verdict recomputed from results; summary cites only existing result IDs.

**Failure modes and handling:** flaky results → not verified; patch apply failure → `verification_failed`; LLM outage → verdict without narrative.

**Human gates:** HA-06 is a precondition.

## AG-11 QA Report Agent

**Kind:** Deterministic aggregator plus LLM narrative · **Stage:** 12 Quality Gates & Reporting · **Phase:** 1 (basic report), 2 (gates), Planned (MVP)

**Purpose.** Produce evidence-backed reports, coverage analysis, quality-gate results and the release-readiness recommendation (FR-042 to FR-046).

**Responsibilities**

- Aggregate results; evaluate QG-01 to QG-08 deterministically; compute the verdict.
- Write a narrative of key risks, coverage gaps and limitations.
- Export JSON, HTML, PDF, JUnit XML and SARIF.

**Inputs**

- `job_results` (aggregates) — executions, findings, runs, patches.
- `gate_config` (project thresholds).

**Outputs**

- `quality_gate_results` (QualityGateResult list).
- `verdict` (enum READY, READY_WITH_RISKS, NOT_READY, INCONCLUSIVE).
- `report` (Report) — with narrative.

**Allowed tools/actions:** read evidence and results; call Model Gateway for narrative.

**Explicitly denied:** changing verdicts or gate results; recording release decisions.

**Boundaries:** The platform recommends; a named human decides (HA-10).

**Validation:** every number in the narrative is cross-checked against aggregates; narrative may not state a verdict different from the computed one; every finding links to evidence (NFR-009).

**Failure modes and handling:** narrative failure → report without narrative, labelled.

**Human gates:** HA-09, HA-10.

## Agent permission matrix

The matrix is split into two tables for readability. "Signals only" means the agent emits raw signals that only AG-08 can turn into findings. Three permissions are denied to every agent without exception and are not configurable on SCR-15: **access secrets**, **network egress** and **approve anything**.

| Agent | Read source snapshot | Propose execution tasks | Call Model Gateway | Read evidence |
|---|---|---|---|---|
| AG-01 Orchestrator | Metadata only | Yes (plan tasks) | Yes | Status only |
| AG-02 Requirements Analysis | Yes | No | Yes | No |
| AG-03 Functional Testing | Yes | Yes | Yes | Own results |
| AG-04 API Testing | Yes | Yes | Yes | Own results |
| AG-05 Security Testing | Yes | Yes | Yes | Own results |
| AG-06 Performance Testing | Yes | Yes | Yes | Own results |
| AG-07 Mutation Testing | Yes | Yes | Yes | Own results |
| AG-08 Evidence and Defect Analysis | Yes | Reproduction only | Yes | Yes |
| AG-09 Patch Proposal | Yes | No | Yes | Finding evidence |
| AG-10 Independent Verification | Yes | Verification only | Yes (summary) | Original finding only |
| AG-11 QA Report | No | No | Yes (narrative) | Yes |

| Agent | Write findings | Propose patch | Access secrets | Network egress | Approve anything |
|---|---|---|---|---|---|
| AG-01 Orchestrator | No | No | Denied | Denied | Denied |
| AG-02 Requirements Analysis | No | No | Denied | Denied | Denied |
| AG-03 Functional Testing | Signals only | No | Denied | Denied | Denied |
| AG-04 API Testing | Signals only | No | Denied | Denied | Denied |
| AG-05 Security Testing | Signals only | No | Denied | Denied | Denied |
| AG-06 Performance Testing | Signals only | No | Denied | Denied | Denied |
| AG-07 Mutation Testing | Signals only | No | Denied | Denied | Denied |
| AG-08 Evidence and Defect Analysis | Yes (non-terminal) | No | Denied | Denied | Denied |
| AG-09 Patch Proposal | No | Yes | Denied | Denied | Denied |
| AG-10 Independent Verification | Verification result | No | Denied | Denied | Denied |
| AG-11 QA Report | No | No | Denied | Denied | Denied |

"Call Model Gateway" is not network egress: agents run on the control plane and reach providers only through the Model Gateway, which is the single semi-trusted egress point and enforces provider allow-lists (SEC-021). Sandbox Workers that execute proposed tasks have network off during execution (SEC-004); their separate dependency-fetch phase is a deterministic Execution Service function, not an agent permission.
