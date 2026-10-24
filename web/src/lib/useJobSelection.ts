import { useSearchParams } from "react-router-dom";
import { useJobs } from "../api/hooks";
import type { Job } from "../api/types";

/**
 * Result screens are scoped to one job. The job comes from `?job=` or defaults to the newest
 * job the API returns; nothing is selected when there are no jobs.
 */
export function useJobSelection() {
  const [params, setParams] = useSearchParams();
  const jobs = useJobs({ limit: 50 });
  const items: Job[] = jobs.data?.items ?? [];
  const param = params.get("job") ?? "";
  const jobId = param || items[0]?.id || "";
  const job = items.find((j) => j.id === jobId);
  const setJobId = (id: string) =>
    setParams((prev) => {
      const next = new URLSearchParams(prev);
      if (id) next.set("job", id);
      else next.delete("job");
      return next;
    });
  return { jobs, items, jobId, job, setJobId };
}
