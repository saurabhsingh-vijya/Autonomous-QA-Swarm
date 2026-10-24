import { StatusBadge } from "./StatusBadge";

/** Check outcome badge: passed | failed | skipped | error (shares tones with StatusBadge). */
export function OutcomeBadge({ outcome }: { outcome: string }) {
  const tone = outcome === "error" ? "orange" : undefined;
  return (
    <StatusBadge
      state={outcome}
      className={tone === "orange" ? "!border-orange-200 !bg-orange-50 !text-orange-700" : ""}
    />
  );
}
