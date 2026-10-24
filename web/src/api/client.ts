import type {
  AgentRegistry,
  Capabilities,
  EvidenceItem,
  Finding,
  FindingFilters,
  Job,
  JobCreate,
  JobDetail,
  JobListParams,
  Paginated,
  Plan,
  PlanApprovalResult,
  Problem,
  Project,
  ProjectCreate,
  ProjectUpdate,
  QualityGates,
  Report,
  TriageRequest,
  Repository,
  RepositoryCreate,
  TaskRecord,
  TestExecution,
} from "./types";

export const API_BASE = "/api/v1";

/** ETag format the API uses for mutable resources: `"<id>:v<version>"`. */
export function etagFor(id: string, version: number): string {
  return `"${id}:v${version}"`;
}
export const DEV_USER = "dev-qa-lead";
export const DEV_ROLE = "QA Lead";

export class ApiError extends Error {
  problem: Problem;
  constructor(problem: Problem) {
    super(problem.detail ?? problem.title);
    this.name = "ApiError";
    this.problem = problem;
  }
}

function uuid(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return Math.random().toString(16).slice(2) + Date.now().toString(16);
}

async function toProblem(res: Response): Promise<Problem> {
  const ct = res.headers.get("content-type") ?? "";
  if (ct.includes("json")) {
    try {
      const body = (await res.json()) as Partial<Problem>;
      return {
        type: body.type ?? "about:blank",
        title: body.title ?? res.statusText ?? "Request failed",
        status: body.status ?? res.status,
        error_code: body.error_code ?? "unknown_error",
        ...body,
      } as Problem;
    } catch {
      /* fall through */
    }
  }
  return {
    type: "about:blank",
    title: res.statusText || "Request failed",
    status: res.status,
    detail: `The server returned HTTP ${res.status} without a problem body.`,
    error_code: "unknown_error",
  };
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Accept", "application/json, application/problem+json");
  headers.set("X-Dev-User", DEV_USER);
  headers.set("X-Dev-Role", DEV_ROLE);
  headers.set("X-Correlation-ID", uuid());
  if (init.body && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...init, headers });
  } catch (err) {
    throw new ApiError({
      type: "about:blank",
      title: "API unreachable",
      status: 0,
      detail: err instanceof Error ? err.message : "Network error",
      error_code: "network_error",
    });
  }
  if (!res.ok) throw new ApiError(await toProblem(res));
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listProjects: () => request<Paginated<Project>>("/projects?limit=200"),
  createProject: (body: ProjectCreate) =>
    request<Project>("/projects", { method: "POST", body: JSON.stringify(body) }),
  getProject: (id: string) => request<Project>(`/projects/${id}`),
  updateProject: (id: string, body: ProjectUpdate) =>
    request<Project>(`/projects/${id}`, { method: "PATCH", body: JSON.stringify(body) }),
  deleteProject: (id: string) => request<void>(`/projects/${id}`, { method: "DELETE" }),

  listRepositories: (projectId?: string) =>
    request<Paginated<Repository>>(
      `/repositories?limit=200${projectId ? `&project_id=${encodeURIComponent(projectId)}` : ""}`,
    ),
  createRepository: (body: RepositoryCreate) =>
    request<Repository>("/repositories", { method: "POST", body: JSON.stringify(body) }),
  getRepository: (id: string) => request<Repository>(`/repositories/${id}`),

  listJobs: (params: JobListParams = {}) => {
    const q = new URLSearchParams();
    if (params.state?.length) q.set("state", params.state.join(","));
    if (params.repository_id) q.set("repository_id", params.repository_id);
    if (params.project_id) q.set("project_id", params.project_id);
    q.set("limit", String(params.limit ?? 50));
    if (params.cursor) q.set("cursor", params.cursor);
    return request<Paginated<Job>>(`/jobs?${q.toString()}`);
  },
  getJob: (id: string) => request<JobDetail>(`/jobs/${id}`),
  createJob: (body: JobCreate) =>
    request<Job>("/jobs", {
      method: "POST",
      body: JSON.stringify(body),
      headers: { "Idempotency-Key": uuid() },
    }),
  getCapabilities: () => request<Capabilities>("/system/capabilities"),
  cancelJob: (id: string, reason?: string) =>
    request<{ id: string; state: string }>(`/jobs/${id}/cancel`, {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    }),

  // Phase 3: orchestration results, all read from persisted records.
  getPlan: (jobId: string) => request<Plan>(`/jobs/${jobId}/plan`),
  approvePlan: (jobId: string, decision: "approve" | "reject", reason?: string) =>
    request<PlanApprovalResult>(`/jobs/${jobId}/plan/approval`, {
      method: "POST",
      body: JSON.stringify({ decision, reason: reason ?? null }),
    }),
  listTasks: (jobId: string) => request<Paginated<TaskRecord>>(`/jobs/${jobId}/tasks`),
  listExecutions: (jobId: string, status?: string[]) =>
    request<Paginated<TestExecution>>(
      `/jobs/${jobId}/test-executions${status?.length ? `?status=${status.join(",")}` : ""}`,
    ),
  listFindings: (jobId: string, filters: FindingFilters = {}) => {
    const q = new URLSearchParams();
    if (filters.severity?.length) q.set("severity", filters.severity.join(","));
    if (filters.confidence?.length) q.set("confidence", filters.confidence.join(","));
    if (filters.status?.length) q.set("status", filters.status.join(","));
    const qs = q.toString();
    return request<Paginated<Finding>>(`/jobs/${jobId}/findings${qs ? `?${qs}` : ""}`);
  },
  getFinding: (findingId: string) => request<Finding>(`/findings/${findingId}`),
  getFindingHistory: (findingId: string) =>
    request<Paginated<Finding>>(`/findings/${findingId}/history`),
  /** Sends `If-Match` built from the version the caller last read, so a stale read is a 412. */
  triageFinding: (findingId: string, version: number, body: TriageRequest) =>
    request<Finding>(`/findings/${findingId}/triage`, {
      method: "POST",
      headers: { "If-Match": etagFor(findingId, version) },
      body: JSON.stringify(body),
    }),
  listFindingEvidence: (findingId: string) =>
    request<Paginated<EvidenceItem>>(`/findings/${findingId}/evidence`),
  listJobEvidence: (jobId: string) => request<Paginated<EvidenceItem>>(`/jobs/${jobId}/evidence`),
  getQualityGates: (jobId: string) => request<QualityGates>(`/jobs/${jobId}/quality-gates`),
  getReport: (jobId: string) => request<Report>(`/jobs/${jobId}/report`),
  listAgents: () => request<AgentRegistry>("/system/agents"),
};

/** Same-origin URL of the HTML report; the dev auth travels as query parameters like SSE. */
export function reportHtmlUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/report?format=html&dev_user=${DEV_USER}&dev_role=${encodeURIComponent(DEV_ROLE)}`;
}

/**
 * Call an endpoint that is expected to be unavailable in this build and return its problem+json
 * (for example `planned_slice` on a 501). Returns null if the endpoint unexpectedly succeeded.
 */
export async function probe(path: string): Promise<Problem | null> {
  const headers = new Headers({
    Accept: "application/json, application/problem+json",
    "X-Dev-User": DEV_USER,
    "X-Dev-Role": DEV_ROLE,
    "X-Correlation-ID": uuid(),
  });
  try {
    const res = await fetch(`${API_BASE}${path}`, { headers });
    if (res.ok) return null;
    return await toProblem(res);
  } catch (err) {
    return {
      type: "about:blank",
      title: "API unreachable",
      status: 0,
      detail: err instanceof Error ? err.message : "Network error",
      error_code: "network_error",
    };
  }
}

export function eventsUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/events?dev_user=${DEV_USER}&dev_role=${encodeURIComponent(DEV_ROLE)}`;
}
