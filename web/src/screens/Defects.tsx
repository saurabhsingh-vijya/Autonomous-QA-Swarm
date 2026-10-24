import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useFindingEvidence, useFindings } from "../api/hooks";
import type { EvidenceItem, Finding } from "../api/types";
import {
  Badge,
  Button,
  EmptyState,
  ErrorState,
  KeyValue,
  PageHeader,
  SeverityChip,
  SkeletonRows,
  StatusBadge,
} from "../components";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { JobSelect } from "../components/JobSelect";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime } from "../lib/format";
import { useJobSelection } from "../lib/useJobSelection";
import { screenById } from "./registry";

const screen = screenById("SCR-11");

const DCS_LABEL: Record<string, string> = {
  reproduced: "Reproduced",
  evidence: "Evidence attached",
  oracle: "Oracle defined",
  occurrences: "Occurrences",
  independent: "Independent runs",
  severity: "Severity signal",
};

export function DcsBar({ value, breakdown }: { value: number; breakdown: Record<string, number> }) {
  const tone = value >= 80 ? "bg-ok" : value >= 50 ? "bg-info" : "bg-warn";
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted">Defect Confidence Score</span>
        <span className="tabular-nums font-medium text-text">{value} / 100</span>
      </div>
      <div
        className="mt-1 h-2 w-full overflow-hidden rounded bg-raised"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        aria-label="Defect Confidence Score"
      >
        <span className={`block h-full ${tone}`} style={{ width: `${value}%` }} />
      </div>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-2xs text-muted">
        {Object.entries(breakdown).map(([k, v]) => (
          <li key={k}>
            {DCS_LABEL[k] ?? k.replace(/_/g, " ")}{" "}
            <span className="tabular-nums text-text">{v}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function FindingCard({ finding, onEvidence }: { finding: Finding; onEvidence: () => void }) {
  const facts = finding.facts.items ?? [];
  const inferred = finding.inferred.items ?? [];
  const evidenceCount = finding.evidence_ids.items?.length ?? 0;
  return (
    <article className="card p-4" aria-labelledby={`f-${finding.id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityChip severity={finding.severity} />
        <h2 id={`f-${finding.id}`} className="text-sm font-semibold text-text">
          <span className="mono text-muted">{finding.display_id}</span> {finding.title}
        </h2>
        <StatusBadge state={finding.confidence} />
        <Badge tone="neutral">{finding.status.replace(/_/g, " ")}</Badge>
        <span className="ml-auto text-xs text-muted">{formatTime(finding.created_at)}</span>
      </div>
      <div className="mt-3 grid gap-4 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <DcsBar value={finding.dcs} breakdown={finding.dcs_breakdown} />
          <div className="mt-4 grid gap-4 md:grid-cols-2">
            <section aria-label="Verified facts">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-ok">
                Facts (observed)
              </h3>
              {facts.length ? (
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-text">
                  {facts.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm text-muted">No facts recorded.</p>
              )}
            </section>
            <section aria-label="Inferred notes">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-warn">
                Inferred (not verified)
              </h3>
              {inferred.length ? (
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-muted">
                  {inferred.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm text-muted">No inference recorded.</p>
              )}
            </section>
          </div>
        </div>
        <div>
          <KeyValue
            items={[
              { label: "Category", value: finding.category, mono: true },
              { label: "Location", value: JSON.stringify(finding.location), mono: true },
              { label: "Occurrences", value: finding.occurrences },
              { label: "Evidence items", value: evidenceCount },
              {
                label: "Executions",
                value: finding.test_execution_ids.items?.length ?? 0,
              },
              { label: "Fingerprint", value: finding.fingerprint.slice(0, 16) + "…", mono: true },
            ]}
          />
          <div className="mt-3 flex flex-wrap gap-2">
            <Button size="sm" onClick={onEvidence} disabled={evidenceCount === 0}>
              View evidence ({evidenceCount})
            </Button>
          </div>
          <p className="mt-3 text-xs text-muted">
            Triage decisions (confirm, false positive, accepted risk) arrive in slice 2b; there is
            no endpoint for them yet, so none is offered here.
          </p>
        </div>
      </div>
    </article>
  );
}

export function DefectsScreen() {
  const { jobs, items, jobId, job, setJobId } = useJobSelection();
  const [params] = useSearchParams();
  const findings = useFindings(jobId || undefined);
  const [evidenceFor, setEvidenceFor] = useState<string | null>(null);
  const [open, setOpen] = useState<EvidenceItem | null>(null);
  const evidence = useFindingEvidence(evidenceFor ?? undefined);
  const rows: Finding[] = Array.isArray(findings.data?.items) ? findings.data.items : [];
  const highlighted = params.get("finding");

  useEffect(() => {
    if (evidenceFor && evidence.data && Array.isArray(evidence.data.items)) {
      setOpen(evidence.data.items[0] ?? null);
    }
  }, [evidenceFor, evidence.data]);

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Findings and fixes" }, { label: screen.navLabel }]}
        title={screen.name}
        subtitle="Findings the Evidence Analysis Agent derived from persisted test executions. Facts are what was observed; inferences are labelled as such. A single-run finding cannot score as confirmed."
        badge={rows.length ? <Badge tone="info">{rows.length} findings</Badge> : null}
      />
      <div className="card mb-5 p-4">
        <JobSelect items={items} value={jobId} onChange={setJobId} loading={jobs.isLoading} />
      </div>

      {!jobId && !jobs.isLoading ? (
        <EmptyState
          title="No jobs yet"
          description="Findings are produced by jobs; create one with API checks to see defects here."
        />
      ) : findings.isLoading || jobs.isLoading ? (
        <SkeletonRows label="Loading findings" />
      ) : findings.isError ? (
        <ErrorState error={findings.error} onRetry={() => findings.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No findings for this job"
          description={
            job
              ? `${job.display_id} has no persisted finding. Either every executed check passed, nothing executed, or the Evidence Analysis task has not run.`
              : "No finding has been persisted."
          }
        />
      ) : (
        <div className="space-y-4">
          {rows.map((f) => (
            <div
              key={f.id}
              className={highlighted === f.id ? "rounded-lg ring-2 ring-accent/60" : ""}
            >
              <FindingCard finding={f} onEvidence={() => setEvidenceFor(f.id)} />
            </div>
          ))}
        </div>
      )}
      <EvidenceDrawer
        evidence={open}
        onClose={() => {
          setOpen(null);
          setEvidenceFor(null);
        }}
      />
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
