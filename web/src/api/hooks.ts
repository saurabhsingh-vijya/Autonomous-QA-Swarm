import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, eventsUrl, probe } from "./client";
import type {
  JobCreate,
  JobEvent,
  JobListParams,
  ProjectCreate,
  ProjectUpdate,
  RepositoryCreate,
} from "./types";

export const keys = {
  projects: ["projects"] as const,
  project: (id: string) => ["projects", id] as const,
  repositories: (projectId?: string) => ["repositories", projectId ?? "all"] as const,
  jobs: (params: JobListParams = {}) => ["jobs", params] as const,
  job: (id: string) => ["jobs", "detail", id] as const,
  capabilities: ["system", "capabilities"] as const,
  agents: ["system", "agents"] as const,
  probe: (path: string) => ["probe", path] as const,
  results: (jobId: string, kind: string) => ["jobs", "results", jobId, kind] as const,
  finding: (id: string) => ["findings", id] as const,
};

const notFound = (err: unknown) =>
  err instanceof ApiError && (err.problem.status === 404 || err.problem.status === 501);

export const useCapabilities = () =>
  useQuery({ queryKey: keys.capabilities, queryFn: api.getCapabilities, staleTime: 30_000 });

/** Probe an endpoint that is not implemented yet; resolves to its problem+json (or null). */
export const useProbe = (path: string | null) =>
  useQuery({
    queryKey: keys.probe(path ?? ""),
    queryFn: () => probe(path ?? ""),
    enabled: Boolean(path),
    staleTime: 60_000,
  });

export const useProjects = () => useQuery({ queryKey: keys.projects, queryFn: api.listProjects });

export function useCreateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreate) => api.createProject(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.projects }),
  });
}

export function useUpdateProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, body }: { id: string; body: ProjectUpdate }) => api.updateProject(id, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: keys.projects }),
  });
}

export function useDeleteProject() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteProject(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.projects });
      qc.invalidateQueries({ queryKey: ["repositories"] });
    },
  });
}

export const useRepositories = (projectId?: string) =>
  useQuery({
    queryKey: keys.repositories(projectId),
    queryFn: () => api.listRepositories(projectId),
  });

export function useCreateRepository() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RepositoryCreate) => api.createRepository(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["repositories"] });
      qc.invalidateQueries({ queryKey: keys.projects });
    },
  });
}

export const useJobs = (params: JobListParams = {}) =>
  useQuery({ queryKey: keys.jobs(params), queryFn: () => api.listJobs(params) });

export const useJob = (id: string) =>
  useQuery({ queryKey: keys.job(id), queryFn: () => api.getJob(id), enabled: Boolean(id) });

export function useCreateJob() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: JobCreate) => api.createJob(body),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["jobs"] }),
  });
}

export function useCancelJob(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (reason?: string) => api.cancelJob(id, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.job(id) });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export const useAgents = () =>
  useQuery({ queryKey: keys.agents, queryFn: api.listAgents, staleTime: 60_000 });

/** Plan for a job; a 404 (no plan yet) resolves to null instead of an error. */
export const usePlan = (jobId: string | undefined, enabled = true) =>
  useQuery({
    queryKey: keys.results(jobId ?? "", "plan"),
    queryFn: () => api.getPlan(jobId!).catch((e) => (notFound(e) ? null : Promise.reject(e))),
    enabled: Boolean(jobId) && enabled,
  });

export const useTasks = (jobId: string | undefined) =>
  useQuery({
    queryKey: keys.results(jobId ?? "", "tasks"),
    queryFn: () => api.listTasks(jobId!),
    enabled: Boolean(jobId),
  });

export const useExecutions = (jobId: string | undefined, status?: string[]) =>
  useQuery({
    queryKey: keys.results(jobId ?? "", `executions:${status?.join(",") ?? "all"}`),
    queryFn: () => api.listExecutions(jobId!, status),
    enabled: Boolean(jobId),
  });

export const useFindings = (jobId: string | undefined) =>
  useQuery({
    queryKey: keys.results(jobId ?? "", "findings"),
    queryFn: () => api.listFindings(jobId!),
    enabled: Boolean(jobId),
  });

export const useFindingEvidence = (findingId: string | undefined) =>
  useQuery({
    queryKey: [...keys.finding(findingId ?? ""), "evidence"],
    queryFn: () => api.listFindingEvidence(findingId!),
    enabled: Boolean(findingId),
  });

export const useJobEvidence = (jobId: string | undefined) =>
  useQuery({
    queryKey: keys.results(jobId ?? "", "evidence"),
    queryFn: () => api.listJobEvidence(jobId!),
    enabled: Boolean(jobId),
  });

export const useQualityGates = (jobId: string | undefined) =>
  useQuery({
    queryKey: keys.results(jobId ?? "", "gates"),
    queryFn: () => api.getQualityGates(jobId!),
    enabled: Boolean(jobId),
  });

/** Report for a job; a 404 (not generated) resolves to null. */
export const useReport = (jobId: string | undefined, enabled = true) =>
  useQuery({
    queryKey: keys.results(jobId ?? "", "report"),
    queryFn: () => api.getReport(jobId!).catch((e) => (notFound(e) ? null : Promise.reject(e))),
    enabled: Boolean(jobId) && enabled,
  });

export function useApprovePlan(jobId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ decision, reason }: { decision: "approve" | "reject"; reason?: string }) =>
      api.approvePlan(jobId, decision, reason),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: keys.job(jobId) });
      qc.invalidateQueries({ queryKey: ["jobs", "results", jobId] });
      qc.invalidateQueries({ queryKey: ["jobs"] });
    },
  });
}

export type SseStatus = "connecting" | "live" | "closed" | "error";

const EVENT_TYPES = ["job.state_changed", "task.state_changed", "heartbeat", "stream.end"];

export function useJobEvents(jobId: string | undefined) {
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [status, setStatus] = useState<SseStatus>("connecting");
  const qc = useQueryClient();

  useEffect(() => {
    if (!jobId || typeof EventSource === "undefined") return;
    setEvents([]);
    setStatus("connecting");
    const es = new EventSource(eventsUrl(jobId));
    const push = (type: string) => (e: MessageEvent) => {
      let data: unknown = e.data;
      try {
        data = JSON.parse(e.data);
      } catch {
        /* keep raw */
      }
      if (type !== "heartbeat") {
        setEvents((prev) => [
          ...prev,
          { id: e.lastEventId, type, data, receivedAt: new Date().toISOString() },
        ]);
      }
      if (type === "job.state_changed" || type === "task.state_changed") {
        qc.invalidateQueries({ queryKey: keys.job(jobId) });
        qc.invalidateQueries({ queryKey: ["jobs", "results", jobId] });
      }
      if (type === "stream.end") {
        es.close();
        setStatus("closed");
      }
    };
    es.onopen = () => setStatus("live");
    es.onerror = () => setStatus(es.readyState === EventSource.CLOSED ? "closed" : "error");
    const handlers = EVENT_TYPES.map((t) => [t, push(t)] as const);
    handlers.forEach(([t, h]) => es.addEventListener(t, h as EventListener));
    es.onmessage = push("message");
    return () => es.close();
  }, [jobId, qc]);

  return { events, status };
}
