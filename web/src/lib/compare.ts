import type { Delta } from "../api/types.phase2";

export const DELTA_LABEL: Record<Delta, string> = {
  improved: "Improved",
  regressed: "Regressed",
  unchanged: "Unchanged",
  added: "New",
  removed: "Removed",
};

export const DELTA_TONE: Record<Delta, string> = {
  improved: "bg-emerald-50 text-emerald-700 border-emerald-200",
  regressed: "bg-red-50 text-red-700 border-red-200",
  unchanged: "bg-slate-100 text-slate-600 border-slate-200",
  added: "bg-sky-50 text-sky-700 border-sky-200",
  removed: "bg-amber-50 text-amber-800 border-amber-300",
};

/** One-line verdict of a comparison from its delta counts (pure, unit-tested). */
export function summarizeDeltas(deltas: Record<string, number>): string {
  const improved = deltas.improved ?? 0;
  const regressed = deltas.regressed ?? 0;
  const added = deltas.added ?? 0;
  const removed = deltas.removed ?? 0;
  if (!improved && !regressed && !added && !removed) return "No differences";
  const parts: string[] = [];
  if (regressed) parts.push(`${regressed} regressed`);
  if (improved) parts.push(`${improved} improved`);
  if (added) parts.push(`${added} new`);
  if (removed) parts.push(`${removed} removed`);
  return parts.join(" · ");
}

export function formatDuration(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m} m ${s} s`;
}
