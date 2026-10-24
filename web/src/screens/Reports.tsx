import { Download, ExternalLink } from "lucide-react";
import { Link } from "react-router-dom";
import { useState } from "react";
import { openHtmlReport, reportHtmlUrl } from "../api/client";
import { useQualityGates, useReport } from "../api/hooks";
import type {
  FindingByPriority,
  PartialReportContent,
  QualityGate,
  ReportCheck,
  ReportContent,
  Verdict,
} from "../api/types";
import { isPartialReport } from "../api/types";
import { SeverityChip } from "../components/SeverityChip";
import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  KeyValue,
  PageHeader,
  SkeletonRows,
  StatusBadge,
} from "../components";
import { buttonClass } from "../components/ui/Button";
import { JobSelect } from "../components/JobSelect";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime } from "../lib/format";
import { useJobSelection } from "../lib/useJobSelection";
import { screenById } from "./registry";

const screen = screenById("SCR-14");

const GATE_NAME: Record<string, string> = {
  "QG-01": "No open confirmed critical findings",
  "QG-02": "No open confirmed high security findings",
  "QG-03": "Functional and API pass rate",
  "QG-04": "P0/P1 scenario coverage",
  "QG-05": "Security scan completeness",
  "QG-06": "Performance thresholds (advisory)",
  "QG-07": "Mutation score on changed modules",
  "QG-08": "Infrastructure error ratio",
};

const VERDICT_TONE: Record<Verdict, "ok" | "warn" | "danger" | "neutral"> = {
  READY: "ok",
  READY_WITH_RISKS: "warn",
  NOT_READY: "danger",
  INCONCLUSIVE: "neutral",
};

function downloadJson(name: string, body: unknown) {
  const blob = new Blob([JSON.stringify(body, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}

export function ReportsScreen() {
  const { jobs, items, jobId, job, setJobId } = useJobSelection();
  const gates = useQualityGates(jobId || undefined);
  const report = useReport(jobId || undefined);
  const g = gates.data && Array.isArray(gates.data.gates) ? gates.data : null;
  const r = report.data ?? null;
  const partial = r ? isPartialReport(r) : false;
  const full: ReportContent | null = r && !partial ? (r.content as ReportContent) : null;
  const partialContent: PartialReportContent | null =
    r && partial ? (r.content as PartialReportContent) : null;
  const verdict = g?.verdict ?? null;
  const checksSummary = (full?.summary?.checks ?? partialContent?.summary?.checks) as
    | Record<string, number>
    | undefined;
  const reportChecks: ReportCheck[] = full?.checks ?? partialContent?.checks ?? [];
  const [reportError, setReportError] = useState<string | null>(null);

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Governance" }, { label: screen.navLabel }]}
        title={screen.name}
        subtitle="Quality gates QG-01 to QG-08 as the QA Reporting Agent evaluated them from persisted results. A gate that could not be measured is inconclusive, never passed. The platform recommends; a QA Lead decides (HA-10)."
        badge={
          verdict ? (
            <Badge tone={VERDICT_TONE[verdict]}>{verdict.replace(/_/g, " ")}</Badge>
          ) : g ? (
            <Badge tone="neutral">No verdict yet</Badge>
          ) : null
        }
        actions={
          r && jobId ? (
            <>
              <a
                href={reportHtmlUrl(jobId)}
                target="_blank"
                rel="noreferrer"
                className={buttonClass("secondary")}
                onClick={(e) => {
                  e.preventDefault();
                  setReportError(null);
                  void openHtmlReport(jobId).catch((err: unknown) =>
                    setReportError(err instanceof Error ? err.message : String(err)),
                  );
                }}
              >
                <ExternalLink className="h-4 w-4" aria-hidden="true" /> Open HTML report
              </a>
              <Button onClick={() => downloadJson(`${job?.display_id ?? jobId}-report.json`, r)}>
                <Download className="h-4 w-4" aria-hidden="true" /> Download JSON
              </Button>
            </>
          ) : undefined
        }
      />

      {reportError ? (
        <p role="alert" className="mb-4 text-sm text-danger">
          The HTML report could not be opened: {reportError}
        </p>
      ) : null}

      <div className="card mb-5 p-4">
        <JobSelect items={items} value={jobId} onChange={setJobId} loading={jobs.isLoading} />
      </div>

      {!jobId && !jobs.isLoading ? (
        <EmptyState
          title="No jobs yet"
          description="Gates are evaluated when a job produces its report. Create a job with inputs first."
        />
      ) : gates.isLoading || jobs.isLoading ? (
        <SkeletonRows label="Loading gates" />
      ) : gates.isError ? (
        <ErrorState error={gates.error} onRetry={() => gates.refetch()} />
      ) : !g ? (
        <EmptyState title="No gate data" description="The API returned no gate evaluation." />
      ) : (
        <div className="grid gap-5 lg:grid-cols-3">
          <div className="space-y-5 lg:col-span-2">
            {partial ? (
              <section
                role="status"
                className="card border-l-4 border-l-warn p-4"
                aria-labelledby="partial-heading"
              >
                <h2 id="partial-heading" className="text-sm font-semibold text-text">
                  Partial report — job did not complete
                </h2>
                <p className="mt-1 text-sm text-muted">
                  The job ended before the QA Reporting Agent ran, so no gates were evaluated and
                  there is no verdict. Checks and tests recorded up to that point are listed below.
                </p>
                {partialContent?.limitations?.length ? (
                  <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-muted">
                    {partialContent.limitations.map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                ) : null}
              </section>
            ) : null}
            <section
              className={`card border-l-4 p-4 ${
                verdict === "READY"
                  ? "border-l-ok"
                  : verdict === "NOT_READY"
                    ? "border-l-danger"
                    : verdict === "READY_WITH_RISKS"
                      ? "border-l-warn"
                      : "border-l-line-strong"
              }`}
              aria-labelledby="verdict-heading"
            >
              <h2 id="verdict-heading" className="text-sm font-semibold text-text">
                Verdict:{" "}
                <span className="font-semibold">
                  {verdict ? verdict.replace(/_/g, " ") : "not evaluated"}
                </span>
              </h2>
              <p className="mt-1 text-sm text-muted">{g.verdict_reason}</p>
              {g.evaluated_at ? (
                <p className="mt-1 text-xs text-muted">Evaluated {formatTime(g.evaluated_at)}</p>
              ) : null}
            </section>

            <section className="card" aria-labelledby="gates-heading">
              <div className="border-b border-line px-3.5 py-2.5">
                <h2 id="gates-heading" className="text-sm font-semibold text-text">
                  Quality gates
                </h2>
              </div>
              <DataTable<QualityGate>
                caption="Quality gates"
                rows={g.gates}
                rowKey={(x) => x.gate_id}
                columns={[
                  {
                    key: "gate",
                    header: "Gate",
                    render: (x) => (
                      <div>
                        <span className="mono text-muted">{x.gate_id}</span>{" "}
                        <span className="text-text">{GATE_NAME[x.gate_id] ?? ""}</span>
                      </div>
                    ),
                  },
                  {
                    key: "result",
                    header: "Result",
                    render: (x) => <StatusBadge state={x.result} />,
                  },
                  {
                    key: "blocking",
                    header: "Blocking",
                    render: (x) => (
                      <span className="text-muted">{x.blocking ? "yes" : "advisory"}</span>
                    ),
                  },
                  {
                    key: "measured",
                    header: "Measured",
                    render: (x) =>
                      x.measured && Object.keys(x.measured).length ? (
                        <span className="mono text-xs">
                          {Object.entries(x.measured)
                            .map(([k, v]) => `${k}=${String(v)}`)
                            .join(" ")}
                        </span>
                      ) : (
                        <span className="text-xs text-muted">not measured</span>
                      ),
                  },
                  {
                    key: "note",
                    header: "Note",
                    render: (x) => <span className="text-xs text-muted">{x.note ?? "—"}</span>,
                  },
                ]}
              />
            </section>

            {reportChecks.length ? (
              <section className="card" aria-labelledby="report-checks-heading">
                <div className="flex flex-wrap items-center gap-2 border-b border-line px-3.5 py-2.5">
                  <h2 id="report-checks-heading" className="text-sm font-semibold text-text">
                    Repository checks
                  </h2>
                  {checksSummary ? (
                    <span className="text-xs text-muted">
                      {Object.entries(checksSummary)
                        .map(([k, v]) => `${k} ${v}`)
                        .join(" · ")}
                    </span>
                  ) : null}
                </div>
                <DataTable<ReportCheck>
                  caption="Repository checks in the report"
                  rows={reportChecks}
                  rowKey={(x) => x.id ?? `${x.engine}:${x.name}`}
                  columns={[
                    {
                      key: "engine",
                      header: "Check",
                      render: (x) => (
                        <span>
                          <span className="mono text-muted">{x.engine}</span>{" "}
                          <span className="text-text">{x.name}</span>
                        </span>
                      ),
                    },
                    {
                      key: "outcome",
                      header: "Outcome",
                      render: (x) => <StatusBadge state={x.outcome} />,
                    },
                    {
                      key: "message",
                      header: "Message",
                      render: (x) => (
                        <span className="text-xs text-muted">{x.failure_message ?? "—"}</span>
                      ),
                    },
                  ]}
                />
              </section>
            ) : null}

            {full ? (
              <section className="card" aria-labelledby="priority-heading">
                <div className="flex flex-wrap items-center gap-2 border-b border-line px-3.5 py-2.5">
                  <h2 id="priority-heading" className="text-sm font-semibold text-text">
                    Findings by priority
                  </h2>
                  {full.finding_summary ? (
                    <span className="text-xs text-muted">
                      {full.finding_summary.open ?? 0} open · {full.finding_summary.excluded ?? 0}{" "}
                      excluded from gates
                    </span>
                  ) : null}
                </div>
                {full.findings_by_priority?.length ? (
                  <DataTable<FindingByPriority>
                    caption="Findings by priority"
                    rows={full.findings_by_priority}
                    rowKey={(x) => x.id}
                    columns={[
                      {
                        key: "id",
                        header: "Finding",
                        render: (x) => (
                          <Link to={`/defects?job=${jobId}&finding=${x.id}`} className="link">
                            <span className="mono text-muted">{x.display_id}</span> {x.title}
                          </Link>
                        ),
                      },
                      {
                        key: "severity",
                        header: "Severity",
                        render: (x) => <SeverityChip severity={x.severity} />,
                      },
                      {
                        key: "confidence",
                        header: "Confidence",
                        render: (x) => <StatusBadge state={x.confidence} />,
                      },
                      {
                        key: "status",
                        header: "Status",
                        render: (x) => <StatusBadge state={x.status} />,
                      },
                      {
                        key: "dcs",
                        header: "DCS",
                        render: (x) => <span className="tabular-nums">{x.dcs}</span>,
                      },
                      {
                        key: "priority",
                        header: "Priority",
                        render: (x) => (
                          <span className="tabular-nums font-medium">{x.risk_priority}</span>
                        ),
                      },
                    ]}
                  />
                ) : (
                  <p className="px-3.5 py-3 text-sm text-muted">
                    No finding was recorded for this job.
                  </p>
                )}
              </section>
            ) : null}

            {full ? (
              <section className="card p-4" aria-labelledby="narrative-heading">
                <h2 id="narrative-heading" className="text-sm font-semibold text-text">
                  Narrative
                  <Badge tone="info" className="ml-2">
                    {full.narrative_source}
                  </Badge>
                </h2>
                <p className="mt-2 text-sm text-text">{full.narrative}</p>
                <h3 className="mt-4 text-xs font-semibold uppercase tracking-wide text-muted">
                  Residual risk
                </h3>
                {full.residual_risk.length ? (
                  <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-muted">
                    {full.residual_risk.map((x) => (
                      <li key={x}>{x}</li>
                    ))}
                  </ul>
                ) : (
                  <p className="mt-1 text-sm text-muted">None recorded.</p>
                )}
              </section>
            ) : null}
          </div>

          <aside className="space-y-5">
            <section className="card p-4" aria-labelledby="summary-heading">
              <h2 id="summary-heading" className="mb-2 text-sm font-semibold text-text">
                Test summary
              </h2>
              {full ? (
                <KeyValue
                  items={Object.entries(full.test_summary).map(([k, v]) => ({
                    label: k.replace(/_/g, " "),
                    value: v,
                  }))}
                />
              ) : partialContent ? (
                <KeyValue
                  items={Object.entries(partialContent.summary?.tests ?? {}).map(([k, v]) => ({
                    label: k.replace(/_/g, " "),
                    value: v,
                  }))}
                />
              ) : (
                <p className="text-sm text-muted">
                  {report.isLoading
                    ? "Loading report."
                    : "No report has been generated for this job yet."}
                </p>
              )}
            </section>
            <section className="card p-4" aria-labelledby="report-heading">
              <h2 id="report-heading" className="mb-2 text-sm font-semibold text-text">
                Report record
              </h2>
              {r ? (
                <KeyValue
                  items={[
                    { label: "Id", value: r.id, mono: true },
                    { label: "Generator", value: r.generator },
                    { label: "Partial", value: partial ? "yes" : "no" },
                    { label: "Digest", value: r.digest.slice(0, 16) + "…", mono: true },
                    { label: "Created", value: formatTime(r.created_at) },
                  ]}
                />
              ) : (
                <p className="text-sm text-muted">No report record.</p>
              )}
            </section>
            <section className="card p-4" aria-labelledby="decision-heading">
              <h2 id="decision-heading" className="mb-1 text-sm font-semibold text-text">
                Release decision
              </h2>
              <p className="text-sm text-muted">
                Not available (slice 2d). Recording the human release decision (HA-10) needs the
                release-decision endpoint, which this build does not have. The verdict above is a
                recommendation only.
              </p>
              {g.accepted_risks.length ? null : (
                <p className="mt-2 text-xs text-muted">No accepted risks recorded.</p>
              )}
            </section>
          </aside>
        </div>
      )}
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
