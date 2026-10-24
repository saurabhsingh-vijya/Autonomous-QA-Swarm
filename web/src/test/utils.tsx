import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

export function renderWithProviders(ui: ReactElement, { route = "/" } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

export function jsonResponse(body: unknown, status = 200, contentType = "application/json") {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": contentType } });
}

export function emptyPage() {
  return { items: [], next_cursor: null, limit: 50 };
}

/** fetch mock that returns an empty page for every list endpoint. */
export function mockFetchEmpty() {
  const fn = vi.fn(async () => jsonResponse(emptyPage()));
  vi.stubGlobal("fetch", fn);
  return fn;
}

export type Route = {
  /** Substring or regex matched against the request path (without query string). */
  match: string | RegExp;
  method?: string;
  body: unknown;
  status?: number;
  contentType?: string;
};

/**
 * fetch mock that routes by URL. Unmatched requests get an empty page so screens
 * never hang. The problem+json 501 shape mirrors the backend contract table.
 */
export function mockFetchRoutes(routes: Route[]) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = url.split("?")[0];
    const method = (init?.method ?? "GET").toUpperCase();
    const r = routes.find(
      (x) =>
        (x.method ?? "GET").toUpperCase() === method &&
        (typeof x.match === "string" ? path.includes(x.match) : x.match.test(path)),
    );
    if (!r) return jsonResponse(emptyPage());
    const ct = r.contentType ?? ((r.status ?? 200) >= 400 ? "application/problem+json" : undefined);
    return jsonResponse(r.body, r.status ?? 200, ct);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function notImplemented(planned_slice: string, detail = "Not implemented in this build.") {
  return {
    type: "https://raone.dev/problems/not_implemented",
    title: "Not implemented",
    status: 501,
    detail,
    error_code: "not_implemented",
    trace_id: "trace_test",
    planned_slice,
  };
}

export const capabilitiesFixture = {
  product: "RaOne",
  version: "0.1.0",
  local_only: true,
  external_ai_providers: "disabled",
  telemetry_export: "none",
  auth_mode: "dev-headers",
  database: { available: true, status: "ok" },
  storage: { driver: "postgresql+psycopg", host: "localhost", port: 5432, database: "raone" },
  execution_service: { available: false, status: "not deployed", planned_slice: "1c" },
  evidence_store: { available: false, status: "not configured", planned_slice: "1b" },
  model_gateway: { available: false, status: "disabled", planned_slice: "2c" },
  test_engines: [],
  integrations: {
    github: { available: false, status: "not connected", planned_slice: "3e" },
    slack: { available: false, status: "not connected", planned_slice: "3e" },
  },
  limits: {
    job_wall_clock_seconds: 7200,
    task_wall_clock_seconds: 1800,
    lease_ttl_seconds: 60,
    heartbeat_seconds: 15,
    task_max_retries: 2,
  },
};

export const projectFixture = {
  id: "prj_01",
  org_id: "org_01",
  org_name: "Local org",
  name: "Payments",
  description: null,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
  version: 1,
  repository_count: 1,
};

export const repositoryFixture = {
  id: "repo_01",
  project_id: "prj_01",
  provider: "github",
  url: "https://github.com/acme/payments",
  default_branch: "main",
  validation_status: "pending_validation",
  validation_note: null,
  last_pinned_sha: null,
  language_support: null,
  created_at: "2026-10-20T10:05:00Z",
};

export function jobFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "job_01HZZZZZZZZZZZZZZZZZZZZZZZ",
    display_id: "QA-0001",
    state: "validating",
    repository_id: "repo_01",
    project_id: "prj_01",
    ref: "main",
    commit_sha: null,
    profiles: { functional: "standard", security: "quick", performance: "none" },
    held_reason: "intake arrives in slice 1b",
    created_at: "2026-10-21T09:00:00Z",
    updated_at: "2026-10-21T09:00:00Z",
    deadline_at: "2026-10-21T11:00:00Z",
    version: 1,
    stages: [{ stage: "intake_and_pinning", status: "held", note: "intake arrives in slice 1b" }],
    ...overrides,
  };
}

// ---- Phase 3 fixtures: shapes mirror backend/src/qaswarm/api/routers/results.py ---------

export const JOB_ID = "job_01HZZZZZZZZZZZZZZZZZZZZZZZ";

const AGENT_ROWS: [string, string, string, boolean, string | null, string | null][] = [
  ["AG-01", "Orchestrator Agent", "deterministic", true, "deterministic", null],
  ["AG-02", "Requirements Analysis Agent", "deterministic_with_llm", true, "deterministic", null],
  ["AG-03", "Functional Testing Agent", "deterministic", true, "deterministic", null],
  ["AG-04", "API Testing Agent", "deterministic", true, "deterministic", null],
  ["AG-05", "Security Testing Agent", "deterministic_with_llm", false, null, "2a"],
  ["AG-06", "Performance Testing Agent", "deterministic_with_llm", false, null, "3b"],
  ["AG-07", "Mutation Testing Agent", "deterministic_with_llm", false, null, "3c"],
  ["AG-08", "Evidence and Defect Analysis Agent", "deterministic", true, "deterministic", null],
  ["AG-09", "Patch Proposal Agent", "llm_assisted", false, null, "3d"],
  ["AG-10", "Independent Verification Agent", "deterministic", false, null, "3d"],
  ["AG-11", "QA Report Agent", "deterministic_with_llm", true, "deterministic", null],
];

export const agentsFixture = {
  llm_provider: "none",
  note: "Agents labelled deterministic never call a model.",
  items: AGENT_ROWS.map(([agent_id, name, kind, implemented, adapter, planned_slice]) => ({
    agent_id,
    name,
    kind,
    stage: "various",
    implemented,
    adapter,
    planned_slice,
    task_types: implemented ? [`${agent_id.toLowerCase()}.task`] : [],
  })),
};

export const planFixture = {
  id: "pln_01",
  job_id: JOB_ID,
  revision: 1,
  plan_hash: "a".repeat(64),
  planner: "deterministic-template/1.0",
  approval_required: false,
  approved_at: null,
  nodes: [
    {
      key: "requirements",
      agent_id: "AG-02",
      task_type: "requirements.analyze",
      stage: "planning",
      depends_on: [],
      soft_depends_on: [],
      critical: true,
    },
    {
      key: "api",
      agent_id: "AG-04",
      task_type: "api.check",
      stage: "functional_and_api_testing",
      depends_on: ["requirements"],
      soft_depends_on: [],
      critical: false,
    },
    {
      key: "evidence",
      agent_id: "AG-08",
      task_type: "evidence.correlate",
      stage: "evidence_correlation_and_triage",
      depends_on: [],
      soft_depends_on: ["api"],
      critical: false,
    },
    {
      key: "report",
      agent_id: "AG-11",
      task_type: "report.build",
      stage: "quality_gates_and_reporting",
      depends_on: [],
      soft_depends_on: ["evidence"],
      critical: false,
    },
  ],
};

function taskFixture(id: string, agent: string, type: string, stage: string, state: string) {
  return {
    id,
    stage,
    task_type: type,
    agent_id: agent,
    state,
    attempt_count: state === "pending" ? 0 : 1,
    depends_on: { tasks: [], soft: [] },
    inputs: {},
    last_error_code: state === "failed" ? "E-MODEL-001" : null,
    last_error_class: state === "failed" ? "infrastructure_error" : null,
    available_at: "2026-10-21T09:00:00Z",
    state_changed_at: "2026-10-21T09:01:00Z",
    created_at: "2026-10-21T09:00:00Z",
    attempts:
      state === "pending"
        ? []
        : [
            {
              id: `${id}-a1`,
              attempt_no: 1,
              lease_owner: "raone-runner",
              outcome: state,
              error_code: state === "failed" ? "E-MODEL-001" : null,
              error_class: state === "failed" ? "infrastructure_error" : null,
              started_at: "2026-10-21T09:00:30Z",
              ended_at: "2026-10-21T09:01:00Z",
            },
          ],
    outputs:
      state === "succeeded"
        ? [
            {
              id: `${id}-o1`,
              attempt_no: 1,
              agent_id: agent,
              agent_kind: "deterministic",
              adapter: "deterministic",
              model_ref: null,
              schema_name: type.replace(".", "_"),
              schema_version: "1.0",
              validation_status: "valid",
              input_sha256: "b".repeat(64),
              output_sha256: "c".repeat(64),
              tokens_in: 0,
              tokens_out: 0,
              duration_ms: 12,
              payload: { ok: true },
              created_at: "2026-10-21T09:01:00Z",
            },
          ]
        : [],
  };
}

export const tasksFixture = {
  items: [
    taskFixture("tsk_01", "AG-02", "requirements.analyze", "planning", "succeeded"),
    taskFixture("tsk_02", "AG-04", "api.check", "functional_and_api_testing", "succeeded"),
    taskFixture(
      "tsk_03",
      "AG-08",
      "evidence.correlate",
      "evidence_correlation_and_triage",
      "succeeded",
    ),
    taskFixture("tsk_04", "AG-11", "report.build", "quality_gates_and_reporting", "succeeded"),
  ],
  next_cursor: null,
  limit: 4,
};

export const executionsFixture = {
  items: [
    {
      id: "tex_01",
      scenario_id: "SCN-API-001",
      test_type: "api",
      name: "GET http://localhost:8000/healthz responds 200",
      provenance: "supplied",
      purpose: "contract",
      status: "passed",
      duration_ms: 8,
      message: null,
      meta: {
        method: "GET",
        url: "http://localhost:8000/healthz",
        expected_status: 200,
        observed_status: 200,
      },
      tool: "raone-http-checker",
      tool_version: "1.0",
      evidence_id: "evd_01",
      created_at: "2026-10-21T09:01:00Z",
    },
    {
      id: "tex_02",
      scenario_id: "SCN-API-002",
      test_type: "api",
      name: "GET http://localhost:8000/missing responds 200",
      provenance: "supplied",
      purpose: "contract",
      status: "failed",
      duration_ms: 5,
      message: "expected HTTP 200, observed 404",
      meta: {
        method: "GET",
        url: "http://localhost:8000/missing",
        expected_status: 200,
        observed_status: 404,
      },
      tool: "raone-http-checker",
      tool_version: "1.0",
      evidence_id: "evd_02",
      created_at: "2026-10-21T09:01:01Z",
    },
    {
      id: "tex_03",
      scenario_id: "SCN-API-003",
      test_type: "api",
      name: "GET https://example.com/ responds 200",
      provenance: "supplied",
      purpose: "contract",
      status: "blocked",
      duration_ms: 0,
      message: "host example.com is not in the local allow-list",
      meta: {
        method: "GET",
        url: "https://example.com/",
        expected_status: 200,
        observed_status: null,
      },
      tool: "raone-http-checker",
      tool_version: "1.0",
      evidence_id: null,
      created_at: "2026-10-21T09:01:02Z",
    },
    {
      id: "tex_04",
      scenario_id: "SCN-REQ-001-abcdef",
      test_type: "functional",
      name: "The service must answer health checks",
      provenance: "derived",
      purpose: "acceptance",
      status: "skipped",
      duration_ms: 0,
      message: "no functional execution engine in this build",
      meta: {},
      tool: "none",
      tool_version: "0",
      evidence_id: null,
      created_at: "2026-10-21T09:01:03Z",
    },
  ],
  next_cursor: null,
  limit: 4,
};

export const evidenceFixture = {
  items: [
    {
      id: "evd_02",
      job_id: JOB_ID,
      task_id: "tsk_02",
      kind: "http_exchange",
      media_type: "application/json",
      sha256: "d".repeat(64),
      size_bytes: 210,
      producer: "raone-http-checker 1.0",
      deterministic: true,
      redaction_status: "redacted",
      content: {
        request: { method: "GET", url: "http://localhost:8000/missing" },
        response: {
          status: 404,
          headers: { authorization: "[REDACTED]" },
          body_excerpt: "not found",
        },
        expected: { status: 200 },
      },
      created_at: "2026-10-21T09:01:01Z",
    },
    {
      id: "evd_01",
      job_id: JOB_ID,
      task_id: "tsk_02",
      kind: "http_exchange",
      media_type: "application/json",
      sha256: "e".repeat(64),
      size_bytes: 120,
      producer: "raone-http-checker 1.0",
      deterministic: true,
      redaction_status: "redacted",
      content: {
        request: { method: "GET", url: "http://localhost:8000/healthz" },
        response: { status: 200 },
      },
      created_at: "2026-10-21T09:01:00Z",
    },
  ],
  next_cursor: null,
  limit: 2,
};

export const findingsFixture = {
  items: [
    {
      id: "fnd_01",
      display_id: "FND-0001",
      job_id: JOB_ID,
      category: "api.contract",
      title: "GET http://localhost:8000/missing returned 404, expected 200",
      severity: "medium",
      status: "candidate",
      confidence: "probable",
      dcs: 63,
      dcs_breakdown: { reproduced: 0, evidence: 25, oracle: 20, occurrences: 8, severity: 10 },
      fingerprint: "f".repeat(64),
      location: { method: "GET", url: "http://localhost:8000/missing" },
      occurrences: 1,
      facts: { items: ["Observed HTTP 404 where 200 was expected (evidence evd_02)."] },
      inferred: { items: ["Inference: the route may not be registered on this target."] },
      evidence_ids: { items: ["evd_02"] },
      test_execution_ids: { items: ["tex_02"] },
      created_at: "2026-10-21T09:01:02Z",
      version: 1,
    },
  ],
  next_cursor: null,
  limit: 1,
};

export const gatesFixture = {
  job_id: JOB_ID,
  display_id: "QA-0001",
  evaluated_at: "2026-10-21T09:01:05Z",
  verdict: "NOT_READY",
  verdict_reason: "Blocking gate(s) failed: QG-03.",
  gates: [
    {
      gate_id: "QG-01",
      result: "passed",
      blocking: true,
      measured: { open_confirmed_critical: 0 },
    },
    {
      gate_id: "QG-02",
      result: "passed",
      blocking: true,
      measured: { open_confirmed_high_security: 0 },
    },
    {
      gate_id: "QG-03",
      result: "failed",
      blocking: true,
      measured: { pass_rate: 0.5, executed: 2 },
    },
    {
      gate_id: "QG-04",
      result: "inconclusive",
      blocking: true,
      note: "No scenarios were planned.",
    },
    {
      gate_id: "QG-05",
      result: "not_applicable",
      blocking: true,
      note: "Not measured in this build (arrives in slice 2a).",
    },
    {
      gate_id: "QG-06",
      result: "not_applicable",
      blocking: false,
      note: "Not measured in this build (arrives in slice 3b).",
    },
    {
      gate_id: "QG-07",
      result: "not_applicable",
      blocking: true,
      note: "Not measured in this build (arrives in slice 3c).",
    },
    {
      gate_id: "QG-08",
      result: "passed",
      blocking: true,
      measured: { infra_error_ratio: 0, tasks: 4 },
    },
  ],
  accepted_risks: [],
  release_decision: null,
  report_digest: "9".repeat(64),
};

export const pendingGatesFixture = {
  job_id: JOB_ID,
  display_id: "QA-0001",
  evaluated_at: null,
  verdict: null,
  verdict_reason: "Gates are evaluated when the report is produced.",
  gates: Array.from({ length: 8 }, (_, i) => ({
    gate_id: `QG-0${i + 1}`,
    result: "pending",
    blocking: i !== 5,
  })),
  accepted_risks: [],
  release_decision: null,
};

export const reportFixture = {
  id: "rpt_01",
  job_id: JOB_ID,
  kind: "main",
  verdict: "NOT_READY",
  generator: "AG-11 deterministic/1.0",
  digest: "9".repeat(64),
  created_at: "2026-10-21T09:01:05Z",
  content: {
    verdict: "NOT_READY",
    verdict_reason: "Blocking gate(s) failed: QG-03.",
    gates: gatesFixture.gates,
    test_summary: { passed: 1, failed: 1, skipped: 1, blocked: 1, executed: 2 },
    residual_risk: ["Functional scenarios were not executed (no engine)."],
    narrative: "One of two executed API checks failed.",
    narrative_source: "deterministic template (no LLM narrative in this build)",
    generated_at: "2026-10-21T09:01:05Z",
  },
};

/** A finished job whose orchestration ran: the shape GET /jobs/{id} returns after phase 3. */
export function finishedJobFixture(overrides: Record<string, unknown> = {}) {
  return jobFixture({
    state: "completed_with_warnings",
    held_reason: null,
    started_at: "2026-10-21T09:00:10Z",
    ended_at: "2026-10-21T09:01:05Z",
    inputs: {
      requirements: ["The service must answer health checks"],
      api_checks: [
        {
          method: "GET",
          url: "http://localhost:8000/healthz",
          expected_status: 200,
          priority: "P0",
        },
      ],
    },
    warnings: { messages: ["Functional scenarios skipped: no execution engine in this build."] },
    report_available: true,
    plan_available: true,
    require_plan_approval: false,
    task_summary: { succeeded: 4 },
    stages: [
      {
        stage: "intake_and_pinning",
        status: "not_run",
        note: "Repository intake arrives in slice 1b",
      },
      { stage: "planning", status: "succeeded", note: "agents AG-02" },
      { stage: "environment_preparation", status: "not_planned" },
      { stage: "baseline_run", status: "not_planned" },
      { stage: "functional_and_api_testing", status: "succeeded", note: "agents AG-04" },
      { stage: "security_testing", status: "not_planned" },
      { stage: "performance_testing", status: "not_planned" },
      { stage: "mutation_testing", status: "not_planned" },
      { stage: "evidence_correlation_and_triage", status: "succeeded", note: "agents AG-08" },
      { stage: "patch_proposal", status: "not_planned" },
      { stage: "independent_verification", status: "not_planned" },
      { stage: "quality_gates_and_reporting", status: "succeeded", note: "agents AG-11" },
      { stage: "cleanup_and_retention", status: "succeeded", note: "no workers to destroy" },
    ],
    ...overrides,
  });
}

/** Routes for a finished job with every phase 3 endpoint answered from fixtures. */
export function phase3Routes(job = finishedJobFixture()): Route[] {
  return [
    { match: "/system/capabilities", body: capabilitiesFixture },
    { match: "/system/agents", body: agentsFixture },
    { match: "/projects", body: { items: [projectFixture], next_cursor: null, limit: 50 } },
    { match: "/repositories/repo_01", body: repositoryFixture },
    { match: "/repositories", body: { items: [repositoryFixture], next_cursor: null, limit: 50 } },
    { match: `/jobs/${JOB_ID}/plan`, body: planFixture },
    { match: `/jobs/${JOB_ID}/tasks`, body: tasksFixture },
    { match: `/jobs/${JOB_ID}/test-executions`, body: executionsFixture },
    { match: `/jobs/${JOB_ID}/findings`, body: findingsFixture },
    { match: `/jobs/${JOB_ID}/evidence`, body: evidenceFixture },
    { match: `/jobs/${JOB_ID}/quality-gates`, body: gatesFixture },
    { match: `/jobs/${JOB_ID}/report`, body: reportFixture },
    { match: "/findings/fnd_01/evidence", body: evidenceFixture },
    { match: `/jobs/${JOB_ID}`, body: job },
    { match: "/jobs", body: { items: [job], next_cursor: null, limit: 50 } },
  ];
}
