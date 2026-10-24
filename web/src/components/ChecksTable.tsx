import { FileSearch } from "lucide-react";
import type { CheckRun, EvidenceItem } from "../api/types";
import { formatDuration } from "../lib/compare";
import { StatusBadge } from "./StatusBadge";
import { Button, DataTable } from "./ui";

/**
 * Check runs of the Execution Service engines for one job. Outcomes are the persisted values;
 * each row links to the log and any other evidence object the engine uploaded.
 */
export function ChecksTable({
  checks,
  evidence,
  onOpenEvidence,
}: {
  checks: CheckRun[];
  evidence: EvidenceItem[];
  onOpenEvidence: (item: EvidenceItem) => void;
}) {
  const byId = new Map(evidence.map((e) => [e.id, e]));
  return (
    <DataTable<CheckRun>
      caption="Check runs"
      rows={checks}
      rowKey={(c) => c.id}
      columns={[
        {
          key: "check",
          header: "Check",
          sortValue: (c) => c.engine_id,
          render: (c) => (
            <div>
              <div className="font-medium text-text">{c.name}</div>
              <div className="mono text-2xs text-muted">
                {c.engine_id} · {c.tool_name} {c.tool_version}
                {c.executes_repository_code ? " · executes repository code" : ""}
              </div>
            </div>
          ),
        },
        {
          key: "outcome",
          header: "Outcome",
          sortValue: (c) => c.outcome,
          render: (c) => <StatusBadge state={c.outcome} />,
        },
        {
          key: "duration",
          header: "Duration",
          align: "right",
          sortValue: (c) => c.duration_ms,
          render: (c) => <span className="tabular-nums">{formatDuration(c.duration_ms)}</span>,
        },
        {
          key: "message",
          header: "Message / summary",
          render: (c) =>
            c.failure_message ? (
              <span className="text-sm text-text">{c.failure_message}</span>
            ) : (
              <span className="text-sm text-muted">
                {Object.entries(c.summary ?? {})
                  .filter(([, v]) => typeof v !== "object")
                  .slice(0, 4)
                  .map(([k, v]) => `${k}: ${String(v)}`)
                  .join(" · ") || "—"}
              </span>
            ),
        },
        {
          key: "evidence",
          header: "Evidence",
          render: (c) => {
            const ids = [
              ...(c.log_evidence_id ? [c.log_evidence_id] : []),
              ...c.evidence_ids.filter((id) => id !== c.log_evidence_id),
            ];
            if (ids.length === 0) return <span className="text-xs text-muted">none</span>;
            return (
              <div className="flex flex-wrap gap-1">
                {ids.map((id) => {
                  const item = byId.get(id);
                  return (
                    <Button
                      key={id}
                      size="sm"
                      variant="ghost"
                      disabled={!item}
                      onClick={() => item && onOpenEvidence(item)}
                      aria-label={`View ${item?.kind ?? "evidence"} for ${c.name}`}
                      title={item ? item.label || item.kind : id}
                    >
                      <FileSearch className="h-3.5 w-3.5" aria-hidden="true" />
                      {item ? item.kind : id.slice(0, 10)}
                    </Button>
                  );
                })}
              </div>
            );
          },
        },
      ]}
    />
  );
}
