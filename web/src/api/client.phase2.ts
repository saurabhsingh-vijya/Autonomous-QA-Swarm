import { API_BASE, ApiError, DEV_ROLE, DEV_USER } from "./client";
import type { JobDetail, Paginated, Problem } from "./types";
import type {
  Capabilities,
  CheckRun,
  CompareResult,
  EvidenceContent,
  EvidenceItem,
  Report,
  Task,
  TestExecution,
  WorkerRun,
} from "./types.phase2";

async function get<T>(path: string): Promise<T> {
  const headers = new Headers({
    Accept: "application/json, application/problem+json",
    "X-Dev-User": DEV_USER,
    "X-Dev-Role": DEV_ROLE,
  });
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { headers });
  } catch (err) {
    throw new ApiError({
      type: "about:blank",
      title: "API unreachable",
      status: 0,
      detail: err instanceof Error ? err.message : "Network error",
      error_code: "network_error",
    });
  }
  if (!res.ok) {
    let problem: Partial<Problem> = {};
    try {
      problem = (await res.json()) as Partial<Problem>;
    } catch {
      /* no body */
    }
    throw new ApiError({
      type: problem.type ?? "about:blank",
      title: problem.title ?? res.statusText,
      status: problem.status ?? res.status,
      error_code: problem.error_code ?? "unknown_error",
      ...problem,
    } as Problem);
  }
  return (await res.json()) as T;
}

export interface TestPage extends Paginated<TestExecution> {
  counts: Record<string, number>;
}

export const api2 = {
  capabilities: () => get<Capabilities>("/system/capabilities"),
  tasks: (jobId: string) => get<Task[]>(`/jobs/${jobId}/tasks`),
  checks: (jobId: string) => get<CheckRun[]>(`/jobs/${jobId}/checks`),
  evidence: (jobId: string) => get<EvidenceItem[]>(`/jobs/${jobId}/evidence`),
  workerRuns: (jobId: string) => get<WorkerRun[]>(`/jobs/${jobId}/worker-runs`),
  evidenceContent: (id: string) => get<EvidenceContent>(`/evidence/${id}/content`),
  report: (jobId: string) => get<Report>(`/jobs/${jobId}/report`),
  compare: (jobId: string, withId: string) =>
    get<CompareResult>(`/jobs/${jobId}/compare?with=${encodeURIComponent(withId)}`),
  jobDetail: (jobId: string) => get<JobDetail>(`/jobs/${jobId}`),
  tests: async (jobId: string, status?: string[]): Promise<TestPage> => {
    const q = new URLSearchParams({ limit: "200" });
    if (status?.length) q.set("status", status.join(","));
    const headers = new Headers({
      Accept: "application/json",
      "X-Dev-User": DEV_USER,
      "X-Dev-Role": DEV_ROLE,
    });
    const res = await fetch(`${API_BASE}/jobs/${jobId}/test-executions?${q}`, { headers });
    if (!res.ok) throw new ApiError((await res.json()) as Problem);
    const page = (await res.json()) as Paginated<TestExecution>;
    const counts: Record<string, number> = {};
    for (const part of (res.headers.get("X-Test-Counts") ?? "").split(",")) {
      const [k, v] = part.split("=");
      if (k && v) counts[k] = Number(v);
    }
    return { ...page, counts };
  },
};

export function reportHtmlUrl(jobId: string): string {
  return `${API_BASE}/jobs/${jobId}/report?format=html`;
}
