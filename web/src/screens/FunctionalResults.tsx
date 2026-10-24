import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useJob, useJobs } from "../api/hooks";
import { useJobChecks, useJobEvidence, useJobTests } from "../api/hooks.phase2";
import type { TestStatus } from "../api/types";
import type { EvidenceItem, TestExecution } from "../api/types.phase2";
import {
  DataTable,
  EmptyState,
  EvidenceDrawer,
  LoadingState,
  PageHeader,
  ProblemAlert,
  StatusBadge,
} from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { formatDuration } from "../lib/compare";
import { screenById } from "./registry";

const screen = screenById("SCR-06");
const STATUSES: TestStatus[] = [
  "passed",
  "failed",
  "skipped",
  "blocked",
  "timed_out",
  "infrastructure_error",
];

export function FunctionalResultsScreen() {
  const [params, setParams] = useSearchParams();
  const jobs = useJobs({ limit: 50 });
  const jobId = params.get("job") ?? jobs.data?.items[0]?.id ?? "";
  const job = useJob(jobId);
  const [filter, setFilter] = useState<"all" | "non_passing" | TestStatus>("non_passing");
  const statusFilter =
    filter === "all"
      ? undefined
      : filter === "non_passing"
        ? STATUSES.filter((s) => s !== "passed")
        : [filter];
  const tests = useJobTests(jobId, statusFilter);
  const checks = useJobChecks(jobId, job.data?.state);
  const evidence = useJobEvidence(jobId);
  const [open, setOpen] = useState<EvidenceItem | null>(null);
  const pytest = checks.data?.find((c) => c.engine_id === "pytest");
  const counts = tests.data?.counts ?? {};
  const executed = Object.values(counts).reduce((a, b) => a + b, 0);

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Results" }, { label: "Functional Tests" }]}
        title="Functional Test Results"
        subtitle="Existing pytest suites run by the Execution Service; each result is normalised to the six design statuses. Flaky reruns are not implemented yet."
        actions={
          <label className="text-sm">
            <span className="sr-only">Job</span>
            <select
              className="input"
              value={jobId}
              onChange={(e) => setParams({ job: e.target.value })}
              aria-label="Select job"
            >
              {(jobs.data?.items ?? []).map((j) => (
                <option key={j.id} value={j.id}>
                  {j.display_id} · {j.ref} · {j.state}
                </option>
              ))}
            </select>
          </label>
        }
      />
      {!jobId && jobs.data ? (
        <EmptyState
          title="No jobs yet"
          description="Run a QA job to see test results here."
          action={
            <Link to="/jobs/new" className="btn-primary">
              New QA job
            </Link>
          }
        />
      ) : null}
      {jobId ? (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 md:grid-cols-7">
            <div className="card p-3">
              <div className="text-xs text-slate-500">Executed</div>
              <div className="text-2xl font-semibold text-slate-900">{executed}</div>
            </div>
            {STATUSES.map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setFilter(s)}
                aria-pressed={filter === s}
                className={`card p-3 text-left ${filter === s ? "ring-2 ring-primary" : ""}`}
              >
                <div className="text-xs text-slate-500">{s.replace(/_/g, " ")}</div>
                <div className="text-2xl font-semibold text-slate-900">{counts[s] ?? 0}</div>
              </button>
            ))}
          </div>
          {pytest ? (
            <div className="mb-4 rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm">
              <span className="font-medium text-slate-900">pytest check:</span>{" "}
              <StatusBadge state={pytest.outcome} />{" "}
              <span className="text-slate-600">
                {pytest.failure_message ??
                  `${pytest.tool_version} · ${formatDuration(pytest.duration_ms)}`}
              </span>
              {pytest.log_evidence_id ? (
                <button
                  type="button"
                  className="ml-2 text-primary underline"
                  onClick={() => {
                    const item = evidence.data?.find((e) => e.id === pytest.log_evidence_id);
                    if (item) setOpen(item);
                  }}
                >
                  view log
                </button>
              ) : null}
              <Link to={`/jobs/${jobId}`} className="ml-2 text-primary underline">
                job detail
              </Link>
            </div>
          ) : (
            <p className="mb-4 text-sm text-slate-500">
              No pytest check for this job yet (functional profile off, or still running).
            </p>
          )}
          <div className="mb-3 flex gap-2" role="group" aria-label="Filter tests">
            {(["non_passing", "all"] as const).map((f) => (
              <button
                key={f}
                type="button"
                aria-pressed={filter === f}
                onClick={() => setFilter(f)}
                className={`rounded-full border px-3 py-1 text-sm ${filter === f ? "border-primary bg-primary-light text-primary" : "border-slate-300 bg-white text-slate-700"}`}
              >
                {f === "all" ? "All" : "Non-passing"}
              </button>
            ))}
          </div>
          <section className="card">
            {tests.isLoading ? <LoadingState label="Loading tests" /> : null}
            {tests.isError ? (
              <div className="p-4">
                <ProblemAlert error={tests.error} />
              </div>
            ) : null}
            {tests.data && tests.data.items.length === 0 ? (
              <p className="p-4 text-sm text-slate-500">No tests match this filter.</p>
            ) : null}
            {tests.data && tests.data.items.length > 0 ? (
              <DataTable<TestExecution>
                caption="Test executions"
                rows={tests.data.items}
                rowKey={(t) => t.id}
                columns={[
                  {
                    key: "test",
                    header: "Test",
                    render: (t) => (
                      <div>
                        <div className="font-mono text-xs text-slate-900">{t.name}</div>
                        <div className="font-mono text-[11px] text-slate-500">{t.node_id}</div>
                      </div>
                    ),
                  },
                  {
                    key: "prov",
                    header: "Provenance",
                    render: (t) => <span className="text-xs">{t.provenance}</span>,
                  },
                  { key: "dur", header: "Duration", render: (t) => formatDuration(t.duration_ms) },
                  {
                    key: "status",
                    header: "Status",
                    render: (t) => <StatusBadge state={t.status} />,
                  },
                  {
                    key: "msg",
                    header: "Failure message",
                    render: (t) => (
                      <pre className="max-w-xl whitespace-pre-wrap break-words font-mono text-[11px] text-slate-700">
                        {t.message ?? "—"}
                      </pre>
                    ),
                  },
                ]}
              />
            ) : null}
          </section>
        </>
      ) : null}
      <EvidenceDrawer item={open} onClose={() => setOpen(null)} />
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
