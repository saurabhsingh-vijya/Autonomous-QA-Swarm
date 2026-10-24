import type { Severity } from "../api/types";

const STYLES: Record<Severity, string> = {
  critical: "bg-red-900 text-white",
  high: "bg-orange-600 text-white",
  medium: "bg-amber-500 text-white",
  low: "bg-slate-500 text-white",
  informational: "bg-slate-200 text-slate-700",
};

export function SeverityChip({ severity }: { severity: Severity }) {
  return (
    <span
      className={`inline-flex rounded px-2 py-0.5 text-xs font-semibold capitalize ${STYLES[severity]}`}
    >
      {severity}
    </span>
  );
}
