import { useQuery } from "@tanstack/react-query";
import { api2 } from "./client.phase2";

const ACTIVE = new Set([
  "queued",
  "planning",
  "running",
  "analyzing",
  "reporting",
  "cancelling",
  "validating",
]);

/** Poll while the job is active; SSE invalidation keeps it fresh, polling is the safety net. */
function refetchWhileActive(state: string | undefined) {
  return state && ACTIVE.has(state) ? 3000 : false;
}

export const useCapabilities = () =>
  useQuery({
    queryKey: ["capabilities"],
    queryFn: api2.capabilities,
    staleTime: 60_000,
    retry: false,
  });

export const useJobTasks = (jobId: string, state?: string) =>
  useQuery({
    queryKey: ["jobs", jobId, "tasks"],
    queryFn: () => api2.tasks(jobId),
    enabled: Boolean(jobId),
    refetchInterval: refetchWhileActive(state),
  });

export const useJobChecks = (jobId: string, state?: string) =>
  useQuery({
    queryKey: ["jobs", jobId, "checks"],
    queryFn: () => api2.checks(jobId),
    enabled: Boolean(jobId),
    refetchInterval: refetchWhileActive(state),
  });

export const useJobTests = (jobId: string, status?: string[]) =>
  useQuery({
    queryKey: ["jobs", jobId, "tests", status ?? []],
    queryFn: () => api2.tests(jobId, status),
    enabled: Boolean(jobId),
  });

export const useJobEvidence = (jobId: string) =>
  useQuery({
    queryKey: ["jobs", jobId, "evidence"],
    queryFn: () => api2.evidence(jobId),
    enabled: Boolean(jobId),
  });

export const useJobWorkerRuns = (jobId: string) =>
  useQuery({
    queryKey: ["jobs", jobId, "worker-runs"],
    queryFn: () => api2.workerRuns(jobId),
    enabled: Boolean(jobId),
  });

export const useEvidenceContent = (id: string | null) =>
  useQuery({
    queryKey: ["evidence", id],
    queryFn: () => api2.evidenceContent(id!),
    enabled: Boolean(id),
  });

export const useJobReport = (jobId: string) =>
  useQuery({
    queryKey: ["jobs", jobId, "report"],
    queryFn: () => api2.report(jobId),
    enabled: Boolean(jobId),
  });

export const useCompare = (jobId: string, withId: string) =>
  useQuery({
    queryKey: ["jobs", jobId, "compare", withId],
    queryFn: () => api2.compare(jobId, withId),
    enabled: Boolean(jobId && withId),
  });
