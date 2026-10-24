// Phase 2 API types: tasks, checks, tests, evidence, reports, comparison, capabilities.
import type { JobState, TaskState, TestStatus } from "./types";

export type CheckOutcome = "passed" | "failed" | "skipped" | "error";
export const CHECK_OUTCOMES: CheckOutcome[] = ["passed", "failed", "skipped", "error"];

export type StageStatus =
  | "pending"
  | "held"
  | "running"
  | "succeeded"
  | "failed"
  | "skipped"
  | "cancelled"
  | "not_run";

export interface StageProgress {
  stage: string;
  status: StageStatus;
  note: string | null;
  tasks: number;
}

export interface TaskAttempt {
  id: string;
  attempt_no: number;
  lease_owner: string;
  outcome: string;
  error_code: string | null;
  error_class: string | null;
  started_at: string | null;
  ended_at: string | null;
}

export interface Task {
  id: string;
  job_id: string;
  stage: string;
  task_type: string;
  agent_id: string | null;
  state: TaskState;
  engine: string | null;
  depends_on: string[];
  priority: number;
  attempt_count: number;
  last_error_code: string | null;
  last_error_class: string | null;
  lease_owner: string | null;
  available_at: string;
  state_changed_at: string;
  created_at: string;
  attempts: TaskAttempt[];
}

export interface CheckRun {
  id: string;
  job_id: string;
  task_id: string;
  attempt_no: number;
  worker_run_id: string | null;
  engine_id: string;
  name: string;
  outcome: CheckOutcome;
  started_at: string;
  ended_at: string;
  duration_ms: number;
  failure_message: string | null;
  summary: Record<string, unknown>;
  tool_name: string;
  tool_version: string;
  executes_repository_code: boolean;
  log_evidence_id: string | null;
  evidence_ids: string[];
}

export interface TestExecution {
  id: string;
  job_id: string;
  check_run_id: string;
  node_id: string;
  file: string | null;
  name: string;
  status: TestStatus;
  duration_ms: number;
  message: string | null;
  purpose: string;
  provenance: string;
  tool_version: string;
  commit_sha: string | null;
}

export interface EvidenceItem {
  id: string;
  job_id: string;
  task_id: string | null;
  worker_run_id: string | null;
  kind: string;
  label: string;
  sha256: string;
  size_bytes: number;
  media_type: string;
  producer: string;
  redactions: number;
  truncated: boolean;
  original_bytes: number | null;
  deterministic: boolean;
  created_at: string;
}

export interface EvidenceContent {
  id: string;
  media_type: string;
  sha256: string;
  size_bytes: number;
  text: string | null;
  truncated_inline: boolean;
}

export interface WorkerRun {
  id: string;
  job_id: string;
  task_id: string;
  worker_id: string;
  runtime: string;
  isolation: string;
  image_digest: string;
  limits: Record<string, unknown>;
  network_policy: string;
  exit_code: number | null;
  outcome: string | null;
  output_bytes: number;
  truncated: boolean;
  started_at: string;
  ended_at: string | null;
  destroyed_at: string | null;
}

export interface Report {
  id: string;
  job_id: string;
  kind: string;
  verdict: string | null;
  digest: string;
  partial: boolean;
  created_at: string;
  updated_at: string;
  content: {
    job: Record<string, unknown>;
    summary: {
      tasks: Record<string, number>;
      checks: Record<string, number>;
      tests: Record<string, number>;
    };
    warnings: string[];
    limitations: string[];
    checks: unknown[];
    tests: unknown[];
    evidence: unknown[];
  };
}

export type Delta = "improved" | "regressed" | "unchanged" | "added" | "removed";

export interface CompareCheck {
  engine: string;
  name: string;
  base: CheckOutcome | null;
  other: CheckOutcome | null;
  delta: Delta;
}

export interface CompareTest {
  node_id: string;
  base: TestStatus | null;
  other: TestStatus | null;
  delta: Delta;
}

export interface CompareJobRef {
  id: string;
  display_id: string;
  state: JobState;
  ref: string;
  commit_sha: string | null;
  created_at: string;
}

export interface CompareResult {
  base: CompareJobRef;
  other: CompareJobRef;
  same_repository: boolean;
  same_commit: boolean;
  checks: CompareCheck[];
  tests: CompareTest[];
  check_deltas: Record<string, number>;
  test_deltas: Record<string, number>;
  test_counts: { base: Record<string, number>; other: Record<string, number> };
}

export interface Capabilities {
  version: string;
  phase: string;
  execution_enabled: boolean;
  repository_code_execution_allowed: boolean;
  sandbox: string;
  dev_fixture_repos: boolean;
  embedded_scheduler: boolean;
  embedded_exec_worker: boolean;
  engines: string[];
}
