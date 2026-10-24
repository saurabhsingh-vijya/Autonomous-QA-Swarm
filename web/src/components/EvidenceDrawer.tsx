import { useEvidenceContent } from "../api/hooks";
import type { EvidenceItem } from "../api/types";
import { formatTime } from "../lib/format";
import { Badge, Button, Dialog, KeyValue } from "./ui";

/**
 * Shows one persisted evidence item verbatim: its hashes, redaction status and content. Agent
 * evidence carries its JSON inline; Execution Service objects (logs, manifests, JUnit) are read
 * from the evidence store through `/evidence/{id}/content`.
 */
export function EvidenceDrawer({
  evidence,
  onClose,
}: {
  evidence: EvidenceItem | null;
  onClose: () => void;
}) {
  const needsFetch = Boolean(evidence) && evidence?.content == null;
  const stored = useEvidenceContent(needsFetch ? evidence?.id : null);
  return (
    <Dialog
      open={Boolean(evidence)}
      onClose={onClose}
      title={evidence ? `Evidence ${evidence.id}` : "Evidence"}
      size="lg"
      description="Content-addressed record written by the tool or agent that produced it. Secrets are redacted before storage."
      footer={<Button onClick={onClose}>Close</Button>}
    >
      {evidence ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-1.5">
            <Badge tone="accent">{evidence.kind}</Badge>
            {evidence.label && evidence.label !== evidence.kind ? (
              <Badge tone="neutral">{evidence.label}</Badge>
            ) : null}
            <Badge tone={evidence.redaction_status === "redacted" ? "ok" : "neutral"}>
              redaction {evidence.redaction_status}
              {evidence.redactions ? ` (${evidence.redactions})` : ""}
            </Badge>
            <Badge tone={evidence.deterministic ? "info" : "neutral"}>
              {evidence.deterministic ? "deterministic" : "non-deterministic"}
            </Badge>
            {evidence.truncated ? <Badge tone="warn">truncated</Badge> : null}
          </div>
          <KeyValue
            columns={2}
            items={[
              { label: "Producer", value: evidence.producer },
              { label: "Media type", value: evidence.media_type, mono: true },
              { label: "SHA-256", value: evidence.sha256, mono: true },
              { label: "Size", value: `${evidence.size_bytes} bytes` },
              { label: "Task", value: evidence.task_id ?? "—", mono: true },
              { label: "Recorded", value: formatTime(evidence.created_at) },
            ]}
          />
          {evidence.content != null ? (
            <pre
              className="max-h-80 overflow-auto rounded-md border border-line bg-canvas p-3 font-mono text-xs text-text"
              aria-label="Evidence content"
            >
              {JSON.stringify(evidence.content, null, 2)}
            </pre>
          ) : stored.isLoading ? (
            <p className="text-sm text-muted">Loading stored object…</p>
          ) : stored.isError ? (
            <p className="text-sm text-danger">
              The stored object could not be read (
              {stored.error instanceof Error ? stored.error.message : "unknown error"}).
            </p>
          ) : stored.data?.text != null ? (
            <>
              <pre
                className="max-h-80 overflow-auto whitespace-pre-wrap rounded-md border border-line bg-canvas p-3 font-mono text-xs text-text"
                aria-label="Evidence content"
              >
                {stored.data.text}
              </pre>
              {stored.data.truncated_inline ? (
                <p className="text-xs text-muted">
                  Inline preview truncated; the full object is available through the download
                  endpoint.
                </p>
              ) : null}
            </>
          ) : (
            <p className="text-sm text-muted">
              Binary object ({stored.data?.media_type ?? evidence.media_type}); no inline preview.
            </p>
          )}
        </div>
      ) : null}
    </Dialog>
  );
}
