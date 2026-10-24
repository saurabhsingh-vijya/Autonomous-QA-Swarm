// Hand-written API types mirroring backend Pydantic schemas (slice 1a + phase 3).
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
  org_id?: string;
  state: JobState;
  repository_id: string;
  project_id: string;
  ref: string;
  commit_sha: string | null;
  profiles: JobProfiles;
  held_reason: string | null;
  require_plan_approval?: boolean;
  created_at: string;
  links?: { self: string; events: string };
}

export interface JobStage {
  stage: string;
  status: string;
  note?: string | null;
}

export interface JobDetail extends Job {
  inputs?: JobInputs;
  warnings?: { messages?: string[] };
  report_available?: boolean;
  plan_available?: boolean;
  deadline_at: string | null;
  version: number;
  updated_at: string;
  stages?: JobStage[];
  cancel_requested_at?: string | null;
  cancel_reason?: string | null;
  started_at?: string | null;
  ended_at?: string | null;
  current_stage?: string | null;
  created_by?: string;
  task_summary?: Record<string, number>;
}

export interface Capability {
  available: boolean;
  status: string;
  planned_slice?: string | null;
}

export interface Capabilities {
  product: string;
  version: string;
  local_only: boolean;
  external_ai_providers: string;
  telemetry_export: string;
  auth_mode: string;
  database: Capability;
  storage: { driver: string; host: string; port: number; database: string };
  execution_service: Capability;
  evidence_store: Capability;
  model_gateway: Capability;
  test_engines: string[];
  integrations: Record<string, Capability>;
  limits: Record<string, number>;
}

export interface JobCreate {
  repository_id: string;
  ref: string;
  profiles: JobProfiles;
  inputs?: JobInputs;
  require_plan_approval?: boolean;
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
  receivedAt?: string;
}

// ---- Phase 3: orchestration inputs and persisted results --------------------------------

export type ApiCheckMethod = "GET" | "HEAD" | "OPTIONS";

export interface ApiCheck {
  method: ApiCheckMethod;
  url: string;
  expected_status: number;
  priority: "P0" | "P1" | "P2";
  requirement_ref?: string | null;
}

export interface JobInputs {
  requirements: string[];
  api_checks: ApiCheck[];
}

export interface PlanNode {
  key: string;
  agent_id: string;
  task_type: string;
  stage: string;
  depends_on: string[];
  soft_depends_on: string[];
  critical: boolean;
  inputs?: Record<string, unknown>;
}

export interface Plan {
  id: string;
  job_id: string;
  revision: number;
  plan_hash: string;
  planner: string;
  approval_required: boolean;
  approved_at: string | null;
  nodes: PlanNode[];
}

export interface PlanApprovalResult {
  job_id: string;
  state: JobState;
  approval_id: string;
  decision: "approved" | "rejected";
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

export type AgentKind = "deterministic" | "llm_assisted" | "deterministic_with_llm";

export interface AgentOutputRecord {
  id: string;
  attempt_no: number;
  agent_id: string;
  agent_kind: AgentKind | string;
  adapter: string;
  model_ref: string | null;
  schema_name: string;
  schema_version: string;
  validation_status: "valid" | "failed" | string;
  input_sha256: string;
  output_sha256: string;
  tokens_in: number;
  tokens_out: number;
  duration_ms: number;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface TaskRecord {
  id: string;
  stage: string;
  task_type: string;
  agent_id: string | null;
  state: TaskState;
  attempt_count: number;
  depends_on: { tasks?: string[]; soft?: string[] };
  inputs: Record<string, unknown>;
  last_error_code: string | null;
  last_error_class: string | null;
  available_at: string;
  state_changed_at: string;
  created_at: string;
  attempts: TaskAttempt[];
  outputs: AgentOutputRecord[];
}

export interface TestExecution {
  id: string;
  scenario_id: string | null;
  test_type: "api" | "functional" | string;
  name: string;
  provenance: string;
  purpose: string;
  status: TestStatus;
  duration_ms: number;
  message: string | null;
  meta: {
    method?: string;
    url?: string;
    expected_status?: number;
    observed_status?: number | null;
    [k: string]: unknown;
  };
  tool: string;
  tool_version: string;
  evidence_id: string | null;
  created_at: string;
}

export type Confidence =
  | "confirmed"
  | "probable"
  | "candidate"
  | "rejected"
  | "possible"
  | "unverified"
  | string;

export type Uncertainty = "low" | "medium" | "high";

export interface RootCauseHypothesis {
  hypothesis: string;
  basis: string;
  uncertainty: Uncertainty;
  supporting_evidence: string[];
  source: string;
  verified: boolean;
}

export interface PriorityBreakdown {
  formula: string;
  severity: string;
  severity_weight: number;
  confidence: string;
  confidence_factor: number;
  exposure: string;
  exposure_factor: number;
  value: number;
  note: string;
}

export interface PriorOccurrence {
  finding_id: string;
  display_id: string;
  job_id: string;
  job_display_id: string;
  job_ref: string;
  status: FindingStatus;
  confidence: Confidence;
  dcs: number;
  seen_at: string;
}

export interface FindingHistory {
  prior_occurrences?: PriorOccurrence[];
  times_seen_before?: number;
  first_seen?: PriorOccurrence | null;
  recurring?: boolean;
  scope?: string;
}

export interface StatusHistoryEntry {
  from: string | null;
  to: string;
  action: string;
  at: string;
  actor_id: string;
  role: string;
  reason: string | null;
}

export interface TriageRecord {
  action?: string;
  reason?: string | null;
  actor_id?: string;
  role?: string;
  at?: string;
  expires_at?: string | null;
  duplicate_of?: string | null;
}

export interface AffectedTest {
  execution_id: string;
  name: string;
  scenario_id: string | null;
  status: TestStatus | string;
  test_type: string;
}

export interface Reproducibility {
  attempted?: boolean;
  runs?: number;
  reproduced?: number;
  fresh_workers?: boolean;
  note?: string;
}

export type TriageAction =
  | "mark_false_positive"
  | "accept_risk"
  | "mark_duplicate"
  | "reopen"
  | "request_reproduction";

export interface TriageRequest {
  action: TriageAction;
  reason?: string | null;
  duplicate_of?: string | null;
  expires_at?: string | null;
}

export interface FindingFilters {
  severity?: string[];
  confidence?: string[];
  status?: string[];
}

export interface Finding {
  id: string;
  display_id: string;
  job_id: string;
  category: string;
  title: string;
  severity: Severity;
  status: FindingStatus;
  confidence: Confidence;
  dcs: number;
  dcs_breakdown: Record<string, number>;
  fingerprint: string;
  location: Record<string, unknown>;
  occurrences: number;
  facts: { items?: string[] };
  inferred: { items?: string[] };
  evidence_ids: { items?: string[] };
  test_execution_ids: { items?: string[] };
  description?: string;
  affected_tests?: { items?: AffectedTest[] };
  reproducibility?: Reproducibility;
  root_causes?: { items?: RootCauseHypothesis[] };
  risk_priority?: number;
  priority_breakdown?: PriorityBreakdown | Record<string, never>;
  history?: FindingHistory;
  status_history?: { items?: StatusHistoryEntry[] };
  triage?: TriageRecord;
  duplicate_of?: string | null;
  disputed?: boolean;
  created_at: string;
  version: number;
}

export interface FindingByPriority {
  id: string;
  display_id: string;
  title: string;
  severity: Severity;
  confidence: Confidence;
  status: FindingStatus;
  dcs: number;
  risk_priority: number;
}

export interface EvidenceItem {
  id: string;
  job_id: string;
  task_id: string | null;
  kind: string;
  media_type: string;
  sha256: string;
  size_bytes: number;
  producer: string;
  deterministic: boolean;
  redaction_status: string;
  content: Record<string, unknown>;
  created_at: string;
}

export interface QualityGate {
  gate_id: string;
  result: GateResult;
  blocking: boolean;
  measured?: Record<string, unknown>;
  note?: string | null;
}

export interface QualityGates {
  job_id: string;
  display_id: string;
  evaluated_at: string | null;
  verdict: Verdict | null;
  verdict_reason: string;
  gates: QualityGate[];
  accepted_risks: unknown[];
  release_decision: unknown | null;
  report_digest?: string;
}

export interface ReportContent {
  verdict: Verdict;
  verdict_reason: string;
  gates: QualityGate[];
  test_summary: Record<string, number>;
  residual_risk: string[];
  narrative: string;
  narrative_source: string;
  generated_at?: string;
  finding_summary?: Record<string, number>;
  findings_by_priority?: FindingByPriority[];
  [k: string]: unknown;
}

export interface Report {
  id: string;
  job_id: string;
  kind: string;
  verdict: Verdict;
  generator: string;
  digest: string;
  created_at: string;
  content: ReportContent;
}

export interface AgentCatalogueEntry {
  agent_id: string;
  name: string;
  kind: AgentKind | string;
  stage: string;
  implemented: boolean;
  adapter: string | null;
  planned_slice: string | null;
  task_types: string[];
}

export interface AgentRegistry {
  llm_provider: string;
  note: string;
  items: AgentCatalogueEntry[];
}
