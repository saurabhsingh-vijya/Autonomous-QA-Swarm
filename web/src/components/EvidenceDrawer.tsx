import type { EvidenceItem } from "../api/types";
import { formatTime } from "../lib/format";
import { Badge, Button, Dialog, KeyValue } from "./ui";

/** Shows one persisted evidence item verbatim: its hashes, redaction status and content. */
export function EvidenceDrawer({
  evidence,
  onClose,
}: {
  evidence: EvidenceItem | null;
  onClose: () => void;
}) {
  return (
    <Dialog
      open={Boolean(evidence)}
      onClose={onClose}
      title={evidence ? `Evidence ${evidence.id}` : "Evidence"}
      size="lg"
      description="Content-addressed record written by the agent that produced it. Secrets are redacted before storage."
      footer={<Button onClick={onClose}>Close</Button>}
    >
      {evidence ? (
        <div className="space-y-3">
          <div className="flex flex-wrap gap-1.5">
            <Badge tone="accent">{evidence.kind}</Badge>
            <Badge tone={evidence.redaction_status === "redacted" ? "ok" : "neutral"}>
              redaction {evidence.redaction_status}
            </Badge>
            <Badge tone={evidence.deterministic ? "info" : "neutral"}>
              {evidence.deterministic ? "deterministic" : "non-deterministic"}
            </Badge>
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
          <pre
            className="max-h-80 overflow-auto rounded-md border border-line bg-canvas p-3 font-mono text-xs text-text"
            aria-label="Evidence content"
          >
            {JSON.stringify(evidence.content, null, 2)}
          </pre>
        </div>
      ) : null}
    </Dialog>
  );
}
