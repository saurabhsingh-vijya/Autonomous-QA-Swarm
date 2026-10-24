import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, eventsUrl } from "./client";
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
};

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

export type SseStatus = "connecting" | "live" | "closed" | "error";

const EVENT_TYPES = [
  "job.state_changed",
  "job.held",
  "job.pinned",
  "job.intake_failed",
  "task.state_changed",
  "task.enqueued",
  "task.retry_scheduled",
  "task.failed",
  "check.completed",
  "heartbeat",
  "stream.end",
];

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
        setEvents((prev) => [...prev, { id: e.lastEventId, type, data }]);
      }
      if (type === "job.state_changed") qc.invalidateQueries({ queryKey: keys.job(jobId) });
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
