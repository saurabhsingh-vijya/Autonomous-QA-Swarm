import type { GateResult, JobState, TaskState, TestStatus } from "../api/types";

export type BadgeState = JobState | TaskState | TestStatus | GateResult | string;

type Tone = "grey" | "blue" | "green" | "amber" | "red" | "slate" | "violet" | "orange" | "indigo";

const TONES: Record<Tone, string> = {
  grey: "bg-slate-100 text-slate-700 border-slate-200",
  slate: "bg-slate-200 text-slate-800 border-slate-300",
  blue: "bg-sky-50 text-sky-700 border-sky-200",
  indigo: "bg-indigo-50 text-indigo-700 border-indigo-200",
  green: "bg-emerald-50 text-emerald-700 border-emerald-200",
  amber: "bg-amber-50 text-amber-800 border-amber-300",
  red: "bg-red-50 text-red-700 border-red-200",
  violet: "bg-violet-50 text-violet-700 border-violet-200",
  orange: "bg-orange-50 text-orange-700 border-orange-200",
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
  // Repository validation
  pending_validation: "amber",
  valid: "green",
  validation_failed: "red",
};

export function stateLabel(state: string): string {
  return state
    .split("_")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

export function StatusBadge({ state, className = "" }: { state: BadgeState; className?: string }) {
  const tone = STATE_TONES[state] ?? "grey";
  const live = ["running", "analyzing", "validating", "planning", "reporting", "leased"].includes(
    state,
  );
  return (
    <span
      data-state={state}
      data-tone={tone}
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-medium ${TONES[tone]} ${className}`}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full bg-current ${live ? "animate-pulse" : ""}`}
      />
      {stateLabel(state)}
    </span>
  );
}
