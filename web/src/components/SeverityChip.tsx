import type { Severity } from "../api/types";

const STYLES: Record<Severity, string> = {
  critical: "bg-danger text-white",
  high: "bg-orange text-white",
  medium: "bg-warn text-black/80",
  low: "bg-neutral text-white",
  informational: "bg-neutral/20 text-muted",
};

export function SeverityChip({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex rounded px-1.5 py-px text-2xs font-semibold capitalize ${STYLES[severity]}`}
    >
      {severity}
    </span>
  );
}
