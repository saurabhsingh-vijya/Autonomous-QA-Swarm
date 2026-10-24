import { LIVE_STATES, STATE_TONES, TONE_CLASSES, stateLabel, type BadgeState } from "./status";

export function StatusBadge({ state, className = "" }: { state: BadgeState; className?: string }) {
  const tone = STATE_TONES[state] ?? "grey";
  const live = LIVE_STATES.has(state);
  return (
    <span
      data-state={state}
      data-tone={tone}
      className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded border px-2 py-px text-xs font-medium ${TONE_CLASSES[tone]} ${className}`}
    >
      <span
        aria-hidden="true"
        className={`h-1.5 w-1.5 rounded-full bg-current ${live ? "rao-pulse" : ""}`}
      />
      {stateLabel(state)}
    </span>
  );
}
