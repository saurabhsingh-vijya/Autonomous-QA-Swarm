import type { GateResult, JobState, TaskState, TestStatus } from "../api/types";

export type BadgeState = JobState | TaskState | TestStatus | GateResult | string;

export type Tone =
  | "grey"
  | "blue"
  | "green"
  | "amber"
  | "red"
  | "slate"
  | "violet"
  | "orange"
  | "indigo";

export const TONE_CLASSES: Record<Tone, string> = {
  grey: "bg-neutral/15 text-muted border-line",
  slate: "bg-neutral/25 text-text border-line-strong",
  blue: "bg-info/15 text-info border-info/40",
  indigo: "bg-accent/15 text-accent border-accent/40",
  green: "bg-ok/15 text-ok border-ok/40",
  amber: "bg-warn/15 text-warn border-warn/40",
  red: "bg-danger/15 text-danger border-danger/40",
  violet: "bg-violet/15 text-violet border-violet/40",
  orange: "bg-orange/15 text-orange border-orange/40",
};

/** One tone per state value; shared vocabularies (e.g. `failed`) map to the same tone. */
export const STATE_TONES: Record<string, Tone> = {
  // Job states
  created: "grey",
  validating: "blue",
  queued: "grey",
  planning: "blue",
  awaiting_approval: "amber",
  running: "blue",
  analyzing: "blue",
  reporting: "indigo",
  cancelling: "orange",
  completed: "green",
  completed_with_warnings: "amber",
  failed: "red",
  cancelled: "slate",
  timed_out: "orange",
  blocked: "violet",
  // Task states
  pending: "grey",
  leased: "indigo",
  succeeded: "green",
  failed_retryable: "amber",
  retry_scheduled: "amber",
  invalid_output: "red",
  skipped: "slate",
  // Test statuses
  passed: "green",
  infrastructure_error: "orange",
  // Gate results
  advisory_failed: "amber",
  inconclusive: "slate",
  not_applicable: "grey",
  // Stage-only statuses
  held: "amber",
  not_run: "slate",
  not_planned: "grey",
  // Finding confidence
  confirmed: "green",
  probable: "blue",
  possible: "amber",
  unverified: "grey",
  // Repository validation
  pending_validation: "amber",
  valid: "green",
  validation_failed: "red",
};

export const LIVE_STATES = new Set([
  "running",
  "analyzing",
  "validating",
  "planning",
  "reporting",
  "leased",
]);

export function stateLabel(state: string): string {
  return state
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
