import { X } from "lucide-react";
import { useEvidenceContent } from "../api/hooks.phase2";
import type { EvidenceItem } from "../api/types.phase2";
import { LoadingState } from "./LoadingState";
import { ProblemAlert } from "./ProblemAlert";

export function EvidenceDrawer({
  item,
  onClose,
}: {
  item: EvidenceItem | null;
  onClose: () => void;
}) {
  const content = useEvidenceContent(item?.id ?? null);
  if (!item) return null;
  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="evidence-title"
      className="fixed inset-y-0 right-0 z-40 flex w-full max-w-2xl flex-col border-l border-slate-200 bg-white shadow-xl"
    >
      <div className="flex items-start justify-between border-b border-slate-200 px-5 py-4">
        <div className="min-w-0">
          <h2 id="evidence-title" className="text-sm font-semibold text-slate-900">
            {item.label || item.kind}
          </h2>
          <p className="mt-0.5 truncate font-mono text-xs text-slate-500">
            {item.id} · {item.media_type} · {item.size_bytes} B · sha256 {item.sha256.slice(0, 16)}…
          </p>
          <p className="mt-0.5 text-xs text-slate-500">
            {item.redactions > 0
              ? `${item.redactions} redaction(s) applied · `
              : "redaction: no matches · "}
            {item.truncated ? "truncated at the output cap · " : ""}
            {item.deterministic ? "deterministic tool output" : "agent output"}
          </p>
        </div>
        <button
          type="button"
          className="btn-secondary"
          onClick={onClose}
          aria-label="Close evidence"
        >
          <X className="h-4 w-4" aria-hidden="true" />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-auto p-4">
        {content.isLoading ? <LoadingState label="Loading evidence" /> : null}
        {content.isError ? <ProblemAlert error={content.error} /> : null}
        {content.data ? (
          content.data.text != null ? (
            <pre className="whitespace-pre-wrap break-all rounded-lg bg-slate-900 p-3 font-mono text-xs leading-5 text-slate-100">
              {content.data.text || "(empty)"}
              {content.data.truncated_inline
                ? "\n… (inline preview truncated; download for the full object)"
                : ""}
            </pre>
          ) : (
            <p className="text-sm text-slate-600">Binary evidence; use the download link.</p>
          )
        ) : null}
      </div>
      <div className="border-t border-slate-200 px-5 py-3 text-xs text-slate-500">
        Evidence is content-addressed and immutable; secrets are redacted before storage (SEC-008).
      </div>
    </div>
  );
}
