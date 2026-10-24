import { FileSearch } from "lucide-react";
import { useState } from "react";
import { useChecks, useExecutions, useJobEvidence } from "../api/hooks";
import type { EvidenceItem, TestExecution } from "../api/types";
import { ChecksTable } from "../components/ChecksTable";
import {
  Badge,
  Button,
  DataTable,
  EmptyState,
  ErrorState,
  PageHeader,
  SkeletonRows,
  StatusBadge,
} from "../components";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { JobSelect } from "../components/JobSelect";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime } from "../lib/format";
import { useJobSelection } from "../lib/useJobSelection";
import type { ScreenDef } from "./registry";

/**
 * SCR-06 (functional) and SCR-07 (API) share one table: persisted test executions for one job,
 * each row linking to the evidence item the agent stored. A status is never derived client-side.
 */
export function ExecutionResultsScreen({
  screen,
  testType,
}: {
  screen: ScreenDef;
  testType: "functional" | "api";
}) {
  const { jobs, items, jobId, job, setJobId } = useJobSelection();
  const executions = useExecutions(jobId || undefined);
  const evidence = useJobEvidence(jobId || undefined);
  const checks = useChecks(testType === "functional" && jobId ? jobId : undefined);
  const [open, setOpen] = useState<EvidenceItem | null>(null);

  const rows: TestExecution[] = (
    Array.isArray(executions.data?.items) ? executions.data.items : []
  ).filter((e) => (testType === "api" ? e.test_type === "api" : e.test_type !== "api"));
  const evidenceRows = Array.isArray(evidence.data?.items) ? evidence.data.items : [];
  const evidenceById = new Map(evidenceRows.map((e) => [e.id, e]));
  const checkRows = Array.isArray(checks.data) ? checks.data : [];
  const counts = rows.reduce<Record<string, number>>((acc, e) => {
    acc[e.status] = (acc[e.status] ?? 0) + 1;
    return acc;
  }, {});
  const executed = (counts.passed ?? 0) + (counts.failed ?? 0);
  /** Per-status counts the API reports for the whole job (header `X-Test-Counts`). */
  const apiCounts = executions.data?.counts ?? {};
  const isPytest = (e: TestExecution) => Boolean(e.node_id);

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Results" }, { label: screen.navLabel }]}
        title={screen.name}
        subtitle={
          testType === "api"
            ? "Read-only HTTP checks the API Testing Agent ran against a local target, with the recorded request and response as evidence. Blocked rows were refused by the local policy and never sent."
            : "Repository tests run by the Execution Service's pytest engine (one row per test, with its JUnit message), plus functional scenarios derived from supplied requirements, which are recorded as skipped because no scenario engine exists. A pass is only ever a persisted pytest result."
        }
        badge={
          rows.length ? (
            <Badge tone={executed ? "info" : "neutral"}>
              {executed} executed of {rows.length}
            </Badge>
          ) : null
        }
      />

      <div className="card mb-5 p-4">
        <JobSelect items={items} value={jobId} onChange={setJobId} loading={jobs.isLoading} />
        {rows.length ? (
          <ul className="mt-3 flex flex-wrap gap-2" aria-label="Executions by status">
            {Object.entries(counts).map(([s, n]) => (
              <li key={s} className="flex items-center gap-1">
                <StatusBadge state={s} />
                <span className="text-xs tabular-nums text-text">{n}</span>
              </li>
            ))}
          </ul>
        ) : null}
        {Object.keys(apiCounts).length ? (
          <p className="mt-2 text-xs text-muted" aria-label="Job-wide test counts">
            Job-wide (all test types):{" "}
            {Object.entries(apiCounts)
              .map(([k, v]) => `${k} ${v}`)
              .join(" · ")}
          </p>
        ) : null}
      </div>

      {testType === "functional" ? (
        <section className="card mb-5" aria-labelledby="checks-heading">
          <div className="border-b border-line px-3.5 py-2.5">
            <h2 id="checks-heading" className="text-sm font-semibold text-text">
              Repository checks{job ? ` for ${job.display_id}` : ""}
            </h2>
          </div>
          {checks.isLoading ? (
            <SkeletonRows label="Loading checks" />
          ) : checks.isError ? (
            <ErrorState error={checks.error} onRetry={() => checks.refetch()} />
          ) : checkRows.length === 0 ? (
            <p className="px-3.5 py-3 text-sm text-muted">
              No check run recorded: the job was not pinned to a commit, or no Execution Service is
              configured.
            </p>
          ) : (
            <ChecksTable checks={checkRows} evidence={evidenceRows} onOpenEvidence={setOpen} />
          )}
        </section>
      ) : null}

      <section className="card" aria-labelledby="exec-table-heading">
        <div className="border-b border-line px-3.5 py-2.5">
          <h2 id="exec-table-heading" className="text-sm font-semibold text-text">
            Executions{job ? ` for ${job.display_id}` : ""}
          </h2>
        </div>
        {!jobId && !jobs.isLoading ? (
          <div className="p-4">
            <EmptyState
              title="No jobs yet"
              description="Create a job with API checks or requirements; its executions appear here."
            />
          </div>
        ) : executions.isLoading || jobs.isLoading ? (
          <SkeletonRows label="Loading executions" />
        ) : executions.isError ? (
          <ErrorState error={executions.error} onRetry={() => executions.refetch()} />
        ) : rows.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title={`No ${testType} executions recorded`}
              description={
                testType === "api"
                  ? "This job had no API checks, or its API Testing task has not run yet."
                  : "This job had no functional profile or requirements, or its Functional Testing task has not run yet."
              }
            />
          </div>
        ) : (
          <DataTable<TestExecution>
            caption={`${testType} executions`}
            rows={rows}
            rowKey={(e) => e.id}
            columns={[
              {
                key: "name",
                header: "Check",
                sortValue: (e) => e.name,
                render: (e) => (
                  <div>
                    <div className="font-medium text-text">{e.name}</div>
                    <div className="mono text-2xs text-muted">
                      {isPytest(e) ? e.node_id : (e.scenario_id ?? "—")}
                    </div>
                  </div>
                ),
              },
              {
                key: "status",
                header: "Status",
                sortValue: (e) => e.status,
                render: (e) => <StatusBadge state={e.status} />,
              },
              ...(testType === "api"
                ? [
                    {
                      key: "http",
                      header: "Expected / observed",
                      render: (e: TestExecution) => (
                        <span className="mono text-xs">
                          {e.meta.expected_status ?? "—"} /{" "}
                          {e.meta.observed_status == null ? "—" : e.meta.observed_status}
                        </span>
                      ),
                    },
                  ]
                : []),
              ...(testType === "functional"
                ? [
                    {
                      key: "file",
                      header: "File",
                      render: (e: TestExecution) => (
                        <span className="mono text-xs text-muted">
                          {e.file ?? (isPytest(e) ? "—" : "requirement scenario")}
                        </span>
                      ),
                    },
                  ]
                : []),
              {
                key: "duration",
                header: "Duration",
                align: "right" as const,
                sortValue: (e) => e.duration_ms,
                render: (e) => <span className="tabular-nums">{e.duration_ms} ms</span>,
              },
              {
                key: "message",
                header: "Message",
                render: (e) => <span className="text-muted">{e.message ?? "—"}</span>,
              },
              {
                key: "evidence",
                header: "Evidence",
                render: (e) =>
                  e.evidence_id ? (
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setOpen(evidenceById.get(e.evidence_id!) ?? null)}
                      disabled={!evidenceById.has(e.evidence_id)}
                      aria-label={`View evidence for ${e.name}`}
                    >
                      <FileSearch className="h-3.5 w-3.5" aria-hidden="true" /> View
                    </Button>
                  ) : (
                    <span className="text-xs text-muted">none</span>
                  ),
              },
            ]}
            renderExpanded={(e) => (
              <dl className="grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-muted">Tool</dt>
                  <dd className="mono">
                    {e.tool} {e.tool_version}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted">Provenance / purpose</dt>
                  <dd>
                    {e.provenance} · {e.purpose}
                  </dd>
                </div>
                <div>
                  <dt className="text-muted">Recorded</dt>
                  <dd>{formatTime(e.created_at)}</dd>
                </div>
                <div>
                  <dt className="text-muted">Meta</dt>
                  <dd className="mono break-all">{JSON.stringify(e.meta)}</dd>
                </div>
                {e.commit_sha ? (
                  <div>
                    <dt className="text-muted">Commit</dt>
                    <dd className="mono">{e.commit_sha}</dd>
                  </div>
                ) : null}
                {e.check_run_id ? (
                  <div>
                    <dt className="text-muted">Check run</dt>
                    <dd className="mono">{e.check_run_id}</dd>
                  </div>
                ) : null}
              </dl>
            )}
          />
        )}
      </section>
      <EvidenceDrawer evidence={open} onClose={() => setOpen(null)} />
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
