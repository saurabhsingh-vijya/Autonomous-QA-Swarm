import type { JobProfiles } from "../api/types";

export function formatTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

const SHORT: Record<string, string> = {
  standard: "Std",
  quick: "Quick",
  smoke: "Smoke",
  baseline: "Baseline",
};

export function profilesSummary(p: JobProfiles | undefined): string {
  if (!p) return "—";
  const parts: string[] = [];
  if (p.functional !== "none") parts.push(`Func ${SHORT[p.functional] ?? p.functional}`);
  if (p.security !== "none") parts.push(`Sec ${SHORT[p.security] ?? p.security}`);
  if (p.performance !== "none") parts.push(`Perf ${SHORT[p.performance] ?? p.performance}`);
  return parts.length ? parts.join(" · ") : "No profiles";
}

export function repoShortName(url: string): string {
  try {
    const u = new URL(url);
    return u.pathname.replace(/^\//, "").replace(/\.git$/, "");
  } catch {
    return url;
  }
}
