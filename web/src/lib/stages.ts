import type { JobDetail, JobStage } from "../api/types";

/** The 13 pipeline stages, in order, keyed by the API stage name. */
export const STAGES: { key: string; name: string }[] = [
  { key: "intake_and_pinning", name: "Intake & Pinning" },
  { key: "planning", name: "Planning" },
  { key: "environment_preparation", name: "Environment Preparation" },
  { key: "baseline_run", name: "Baseline Run" },
  { key: "functional_and_api_testing", name: "Functional & API Testing" },
  { key: "security_testing", name: "Security Testing" },
  { key: "performance_testing", name: "Performance Testing" },
  { key: "mutation_testing", name: "Mutation Testing" },
  { key: "evidence_correlation_and_triage", name: "Evidence Correlation & Triage" },
  { key: "patch_proposal", name: "Patch Proposal" },
  { key: "independent_verification", name: "Independent Verification" },
  { key: "quality_gates_and_reporting", name: "Quality Gates & Reporting" },
  { key: "cleanup_and_retention", name: "Cleanup & Retention" },
];

export type StageStatus = "pending" | "held" | "not_run" | "running" | "succeeded" | "failed";

export interface StageView {
  key: string;
  name: string;
  status: StageStatus;
  note: string | null;
}

/** Merge the API's `stages` array with the canonical list. Unknown statuses fall back to pending. */
export function stageViews(job: JobDetail): StageView[] {
  const byKey = new Map<string, JobStage>((job.stages ?? []).map((s) => [s.stage, s]));
  return STAGES.map((s) => {
    const api = byKey.get(s.key);
    const raw = api?.status ?? "pending";
    const status: StageStatus = (
      ["pending", "held", "not_run", "running", "succeeded", "failed"] as const
    ).includes(raw as StageStatus)
      ? (raw as StageStatus)
      : "pending";
    return { key: s.key, name: s.name, status, note: api?.note ?? null };
  });
}

export const STAGE_STATUS_LABEL: Record<StageStatus, string> = {
  pending: "Pending",
  held: "Held",
  not_run: "Not run",
  running: "Running",
  succeeded: "Done",
  failed: "Failed",
};
