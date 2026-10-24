import { ShieldCheck } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useChecks, useFindings, useJobEvidence } from "../api/hooks";
import type { CheckRun, EvidenceItem, Finding } from "../api/types";
import { ChecksTable } from "../components/ChecksTable";
import {
  Badge,
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  SeverityChip,
  SkeletonRows,
  StatusBadge,
} from "../components";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { JobSelect } from "../components/JobSelect";
import { ScreenFooter } from "../layout/AppShell";
import { formatLocation } from "../lib/compare";
import { useJobSelection } from "../lib/useJobSelection";
import { ENGINE_SCREENS, type EngineKind } from "../lib/engines";
import type { ScreenDef } from "./registry";

function outcomeCounts(checks: CheckRun[]): Record<string, number> {
  return checks.reduce<Record<string, number>>((acc, c) => {
    acc[c.outcome] = (acc[c.outcome] ?? 0) + 1;
    return acc;
  }, {});
}

/**
 * SCR-08 Security Testing Center and SCR-09 Performance Testing Lab. Both read the job's check
 * runs filtered to their engines and (for security) the findings in their category. A job that
 * planned none of these engines says why instead of showing an empty table as "clean".
 */
export function EngineResultsScreen({ screen, kind }: { screen: ScreenDef; kind: EngineKind }) {
  const spec = ENGINE_SCREENS[kind];
  const { jobs, items, jobId, job, setJobId } = useJobSelection();
  const checks = useChecks(jobId || undefined);
  const evidence = useJobEvidence(jobId || undefined);
  const findings = useFindings(spec.findingPrefix && jobId ? jobId : undefined);
  const [open, setOpen] = useState<EvidenceItem | null>(null);

  const allChecks: CheckRun[] = Array.isArray(checks.data) ? checks.data : [];
  const rows = allChecks.filter((c) => (spec.engines as readonly string[]).includes(c.engine_id));
  const evidenceRows = Array.isArray(evidence.data?.items) ? evidence.data.items : [];
  const findingRows: Finding[] = (
    Array.isArray(findings.data?.items) ? findings.data.items : []
  ).filter((f) => spec.findingPrefix && f.category.startsWith(spec.findingPrefix));
  const counts = outcomeCounts(rows);
  const checksLoaded = Boolean(jobId) && !checks.isLoading && !jobs.isLoading;

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Results" }, { label: screen.navLabel }]}
        title={screen.name}
        subtitle={spec.subtitle}
        badge={
          checksLoaded && rows.length > 0 ? (
            <Badge tone={counts.failed ? "danger" : counts.skipped ? "warn" : "ok"}>
              {Object.entries(counts)
                .map(([k, v]) => `${v} ${k}`)
                .join(" · ")}
            </Badge>
          ) : null
        }
      />

      <div className="card mb-5 p-4">
        <JobSelect items={items} value={jobId} onChange={setJobId} loading={jobs.isLoading} />
      </div>

      <section className="card mb-5" aria-labelledby={`${kind}-checks-heading`}>
        <div className="border-b border-line px-3.5 py-2.5">
          <h2 id={`${kind}-checks-heading`} className="text-sm font-semibold text-text">
            Engine runs{job ? ` for ${job.display_id}` : ""}
          </h2>
        </div>
        {!jobId && !jobs.isLoading ? (
          <div className="p-4">
            <EmptyState
              icon={ShieldCheck}
              title="No jobs yet"
              description="Create a QA job; its engine runs appear here with their evidence."
              action={
                <Link to="/jobs/new" className="text-sm text-accent hover:underline">
                  Create a job
                </Link>
              }
            />
          </div>
        ) : checks.isLoading || jobs.isLoading ? (
          <SkeletonRows label="Loading engine runs" />
        ) : checks.isError ? (
          <div className="p-4">
            <ErrorState error={checks.error} onRetry={() => void checks.refetch()} />
          </div>
        ) : rows.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={ShieldCheck}
              title={`No ${kind} engine ran for this job`}
              description={
                allChecks.length === 0
                  ? "This job planned no repository checks (no pinned commit, or the Execution Service is disabled), so nothing was measured."
                  : `The job ran ${allChecks.length} check(s) but none of ${spec.engines.join(", ")}: the profile or the target configuration did not request them. Nothing was measured; this is not a clean result.`
              }
            />
          </div>
        ) : (
          <ChecksTable checks={rows} evidence={evidenceRows} onOpenEvidence={setOpen} />
        )}
      </section>

      {spec.findingPrefix ? (
        <section className="card mb-5" aria-labelledby={`${kind}-findings-heading`}>
          <div className="flex items-center justify-between border-b border-line px-3.5 py-2.5">
            <h2 id={`${kind}-findings-heading`} className="text-sm font-semibold text-text">
              Security findings{job ? ` for ${job.display_id}` : ""}
            </h2>
            {findingRows.length > 0 ? (
              <Link to={`/defects?job=${jobId}`} className="text-xs text-accent hover:underline">
                Triage in Defects &amp; evidence
              </Link>
            ) : null}
          </div>
          {!jobId ? null : findings.isLoading ? (
            <SkeletonRows label="Loading findings" />
          ) : findings.isError ? (
            <div className="p-4">
              <ErrorState error={findings.error} onRetry={() => void findings.refetch()} />
            </div>
          ) : findingRows.length === 0 ? (
            <p className="p-4 text-sm text-muted">
              No security finding was derived for this job. A finding needs a failed engine run with
              evidence; a job without a security engine run cannot have one.
            </p>
          ) : (
            <DataTable<Finding>
              rows={findingRows}
              rowKey={(f) => f.id}
              columns={[
                {
                  key: "id",
                  header: "Finding",
                  render: (f) => (
                    <Link to={`/defects?job=${jobId}`} className="mono text-xs text-accent">
                      {f.display_id}
                    </Link>
                  ),
                },
                { key: "title", header: "Title", render: (f) => f.title },
                { key: "category", header: "Category", render: (f) => f.category },
                {
                  key: "location",
                  header: "Location",
                  render: (f) => <span className="mono text-xs">{formatLocation(f.location)}</span>,
                },
                {
                  key: "severity",
                  header: "Severity",
                  render: (f) => <SeverityChip severity={f.severity} />,
                },
                {
                  key: "confidence",
                  header: "Confidence · DCS",
                  render: (f) => (
                    <span className="inline-flex items-center gap-2">
                      <StatusBadge state={f.confidence} /> {f.dcs}
                    </span>
                  ),
                },
                {
                  key: "status",
                  header: "Status",
                  render: (f) => <StatusBadge state={f.status} />,
                },
              ]}
            />
          )}
        </section>
      ) : null}

      <section className="card p-4" aria-labelledby={`${kind}-limits-heading`}>
        <h2 id={`${kind}-limits-heading`} className="mb-2 text-sm font-semibold text-text">
          What this build does and does not measure
        </h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
          {spec.limits.map((l) => (
            <li key={l}>{l}</li>
          ))}
        </ul>
      </section>

      <EvidenceDrawer evidence={open} onClose={() => setOpen(null)} />
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
