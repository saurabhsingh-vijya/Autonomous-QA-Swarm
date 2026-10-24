// Hand-written API types mirroring backend Pydantic schemas (slice 1a).
// openapi-typescript generation is a follow-up once the API stabilises.

export type JobState =
  | "created"
  | "validating"
  | "queued"
  | "planning"
  | "awaiting_approval"
  | "running"
  | "analyzing"
  | "reporting"
  | "cancelling"
  | "completed"
  | "completed_with_warnings"
  | "failed"
  | "cancelled"
  | "timed_out"
  | "blocked";

export const JOB_STATES: JobState[] = [
  "created",
  "validating",
  "queued",
  "planning",
  "awaiting_approval",
  "running",
  "analyzing",
  "reporting",
  "cancelling",
  "completed",
  "completed_with_warnings",
  "failed",
  "cancelled",
  "timed_out",
  "blocked",
];

export const TERMINAL_JOB_STATES: JobState[] = [
  "completed",
  "completed_with_warnings",
  "failed",
  "cancelled",
  "timed_out",
  "blocked",
];

export type TaskState =
  | "pending"
  | "leased"
  | "running"
  | "succeeded"
  | "failed_retryable"
  | "retry_scheduled"
  | "failed"
  | "invalid_output"
  | "timed_out"
  | "cancelled"
  | "skipped";

export type TestStatus =
  | "passed"
  | "failed"
  | "skipped"
  | "blocked"
  | "timed_out"
  | "infrastructure_error";

export type FindingStatus =
  | "candidate"
  | "triaging"
  | "reproducing"
  | "confirmed"
  | "not_reproducible"
  | "false_positive"
  | "duplicate"
  | "accepted_risk"
  | "fix_proposed"
  | "fix_verified"
  | "fix_failed"
  | "reopened";

export type PatchStatus =
  | "proposed"
  | "awaiting_review"
  | "approved_for_verification"
  | "verification_running"
  | "verified"
  | "verification_failed"
  | "rejected";

export type GateResult =
  | "passed"
  | "failed"
  | "advisory_failed"
  | "inconclusive"
  | "not_applicable"
  | "pending";

export type Verdict = "READY" | "READY_WITH_RISKS" | "NOT_READY" | "INCONCLUSIVE";

export type Severity = "critical" | "high" | "medium" | "low" | "informational";

export type RepositoryProvider = "github" | "gitlab" | "other";
export type RepositoryValidationStatus =
  | "pending_validation"
  | "validating"
  | "valid"
  | "validation_failed";

export interface Paginated<T> {
  items: T[];
  next_cursor: string | null;
  limit: number;
}

export interface ProblemError {
  pointer?: string;
  code?: string;
  message: string;
}

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  error_code: string;
  trace_id?: string;
  errors?: ProblemError[];
  reason?: string;
  hint?: string;
  planned_slice?: string;
  existing_job?: { id: string; display_id: string; state: JobState };
}

export interface Project {
  id: string;
  org_id: string;
  org_name?: string;
  name: string;
  description: string | null;
  created_at: string;
  updated_at: string;
  version: number;
  repository_count?: number;
}

export interface ProjectCreate {
  name: string;
  description?: string | null;
}

export type ProjectUpdate = Partial<ProjectCreate>;

export interface Repository {
  id: string;
  project_id: string;
  provider: RepositoryProvider;
  url: string;
  default_branch: string | null;
  validation_status: RepositoryValidationStatus;
  validation_note: string | null;
  last_pinned_sha: string | null;
  language_support: string | null;
  created_at: string;
}

export interface RepositoryCreate {
  project_id: string;
  provider: RepositoryProvider;
  url: string;
  default_branch?: string | null;
}

export interface JobProfiles {
  functional: "none" | "standard";
  security: "none" | "quick" | "standard";
  performance: "none" | "smoke" | "baseline";
}

export interface Job {
  id: string;
  display_id: string;
  state: JobState;
  repository_id: string;
  project_id: string;
  ref: string;
  commit_sha: string | null;
  profiles: JobProfiles;
  held_reason: string | null;
  created_at: string;
  links?: { self: string; events: string };
}

export interface JobStage {
  stage: string;
  status: string;
  note?: string | null;
  tasks?: number;
}

export interface JobDetail extends Job {
  deadline_at: string | null;
  version: number;
  updated_at: string;
  stages?: JobStage[];
  cancel_requested_at?: string | null;
  // Phase 2
  snapshot_sha256?: string | null;
  warnings?: string[];
  task_summary?: Record<string, number>;
  check_summary?: Record<string, number>;
  test_summary?: Record<string, number>;
}

export interface JobCreate {
  repository_id: string;
  ref: string;
  profiles: JobProfiles;
  force_new?: boolean;
}

export interface JobListParams {
  state?: JobState[];
  repository_id?: string;
  project_id?: string;
  limit?: number;
  cursor?: string;
}

export interface JobEvent {
  id: string;
  type: string;
  data: unknown;
}
