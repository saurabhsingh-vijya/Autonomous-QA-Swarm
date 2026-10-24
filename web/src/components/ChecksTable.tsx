import { FileText } from "lucide-react";
import type { CheckRun, EvidenceItem } from "../api/types.phase2";
import { formatDuration } from "../lib/compare";
import { DataTable } from "./DataTable";
import { OutcomeBadge } from "./OutcomeBadge";

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
          render: (c) => (
            <div>
              <div className="font-medium text-slate-900">{c.name}</div>
              <div className="font-mono text-xs text-slate-500">
                {c.engine_id} · {c.tool_version}
                {c.executes_repository_code ? " · executes repository code" : ""}
              </div>
            </div>
          ),
        },
        { key: "outcome", header: "Outcome", render: (c) => <OutcomeBadge outcome={c.outcome} /> },
        { key: "duration", header: "Duration", render: (c) => formatDuration(c.duration_ms) },
        {
          key: "message",
          header: "Message / summary",
          render: (c) => (
            <div className="max-w-xl">
              {c.failure_message ? (
                <p className="text-sm text-slate-800">{c.failure_message}</p>
              ) : (
                <p className="text-sm text-slate-500">
                  {Object.entries(c.summary)
                    .filter(([, v]) => typeof v !== "object")
                    .slice(0, 4)
                    .map(([k, v]) => `${k}: ${String(v)}`)
                    .join(" · ") || "—"}
                </p>
              )}
            </div>
          ),
        },
        {
          key: "evidence",
          header: "Evidence",
          render: (c) => (
            <div className="flex flex-wrap gap-1">
              {c.evidence_ids.map((id) => {
                const item = byId.get(id);
                return (
                  <button
                    key={id}
                    type="button"
                    className="inline-flex items-center gap-1 rounded border border-slate-200 bg-white px-2 py-0.5 text-xs text-primary hover:bg-slate-50"
                    onClick={() => item && onOpenEvidence(item)}
                    disabled={!item}
                    title={item ? item.label : id}
                  >
                    <FileText className="h-3 w-3" aria-hidden="true" />
                    {item ? item.kind : id.slice(0, 10)}
                  </button>
                );
              })}
            </div>
          ),
        },
      ]}
    />
  );
}
