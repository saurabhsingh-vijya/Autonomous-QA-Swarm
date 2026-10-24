import type { Delta } from "../api/types";
import type { BadgeTone } from "../components/ui";

export const DELTA_LABEL: Record<Delta, string> = {
  improved: "Improved",
  regressed: "Regressed",
  unchanged: "Unchanged",
  added: "New",
  removed: "Removed",
};

export const DELTA_TONE: Record<Delta, BadgeTone> = {
  improved: "ok",
  regressed: "danger",
  unchanged: "neutral",
  added: "info",
  removed: "warn",
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

/**
 * Human-readable finding location. Findings come from API checks (method + URL), pytest
 * failures (file / node id) or check engines (engine + file + rule); unknown shapes fall back
 * to their JSON so nothing is hidden.
 */
export function formatLocation(location: Record<string, unknown> | null | undefined): string {
  if (!location || Object.keys(location).length === 0) return "—";
  const s = (k: string) => (typeof location[k] === "string" ? (location[k] as string) : "");
  if (s("method") || s("url")) return `${s("method")} ${s("url")}`.trim();
  if (s("node_id")) return s("node_id");
  if (s("file")) {
    const parts = [s("engine"), s("file"), s("rule") ? `rule ${s("rule")}` : ""].filter(Boolean);
    return parts.join(" · ");
  }
  return JSON.stringify(location);
}
