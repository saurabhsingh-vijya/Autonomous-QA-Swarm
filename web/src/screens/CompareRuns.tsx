import { Link, useParams } from "react-router-dom";
import { useCompare } from "../api/hooks.phase2";
import type { CompareCheck, CompareTest } from "../api/types.phase2";
import { DataTable, LoadingState, PageHeader, ProblemAlert, StatusBadge } from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { DELTA_LABEL, DELTA_TONE, summarizeDeltas } from "../lib/compare";
import { formatTime } from "../lib/format";

function DeltaChip({ delta }: { delta: CompareCheck["delta"] }) {
  return (
    <span
      className={`inline-flex rounded-full border px-2 py-0.5 text-xs font-medium ${DELTA_TONE[delta]}`}
    >
      {DELTA_LABEL[delta]}
    </span>
  );
}

export function CompareRunsScreen() {
  const { jobId = "", otherId = "" } = useParams();
  const cmp = useCompare(jobId, otherId);
  if (cmp.isLoading) return <LoadingState rows={6} label="Comparing runs" />;
  if (cmp.isError || !cmp.data)
    return (
      <div>
        <PageHeader crumbs={[{ label: "Jobs", to: "/jobs" }]} title="Compare runs" />
        <ProblemAlert error={cmp.error ?? new Error("Comparison unavailable")} />
      </div>
    );
  const c = cmp.data;
  const counts = (m: Record<string, number>) =>
    Object.entries(m)
      .map(([k, v]) => `${k} ${v}`)
      .join(" · ") || "no tests";
  return (
    <div>
      <PageHeader
        crumbs={[
          { label: "Jobs", to: "/jobs" },
          { label: c.base.display_id, to: `/jobs/${c.base.id}` },
          { label: "Compare" },
        ]}
        title={`${c.base.display_id} vs ${c.other.display_id}`}
        subtitle={
          <>
            Checks: {summarizeDeltas(c.check_deltas)} · Tests: {summarizeDeltas(c.test_deltas)}.{" "}
            {c.same_repository ? "Same repository" : "Different repositories"} ·{" "}
            {c.same_commit ? "same commit" : "different commits"}.
          </>
        }
      />
      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-2">
        {[c.base, c.other].map((j, i) => (
          <div key={j.id} className="card p-4 text-sm">
            <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
              {i === 0 ? "Base" : "Other"}
            </div>
            <div className="mt-1 flex items-center gap-2">
              <Link to={`/jobs/${j.id}`} className="font-mono text-base font-semibold text-primary">
                {j.display_id}
              </Link>
              <StatusBadge state={j.state} />
            </div>
            <div className="mt-1 text-slate-600">
              {j.ref} →{" "}
              <span className="font-mono">{j.commit_sha?.slice(0, 12) ?? "not pinned"}</span> ·{" "}
              {formatTime(j.created_at)}
            </div>
            <div className="mt-1 text-xs text-slate-500">
              tests: {counts(i === 0 ? c.test_counts.base : c.test_counts.other)}
            </div>
          </div>
        ))}
      </div>
      <section className="card mb-6">
        <h2 className="border-b border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900">
          Checks
        </h2>
        <DataTable<CompareCheck>
          caption="Check comparison"
          rows={c.checks}
          rowKey={(r) => `${r.engine}:${r.name}`}
          columns={[
            {
              key: "check",
              header: "Check",
              render: (r) => <span className="font-mono text-xs">{r.engine}</span>,
            },
            {
              key: "base",
              header: c.base.display_id,
              render: (r) => (r.base ? <StatusBadge state={r.base} /> : "—"),
            },
            {
              key: "other",
              header: c.other.display_id,
              render: (r) => (r.other ? <StatusBadge state={r.other} /> : "—"),
            },
            { key: "delta", header: "Δ", render: (r) => <DeltaChip delta={r.delta} /> },
          ]}
        />
      </section>
      <section className="card">
        <h2 className="border-b border-slate-200 px-4 py-3 text-sm font-semibold text-slate-900">
          Tests that changed{" "}
          <span className="font-normal text-slate-500">{c.tests.length} shown</span>
        </h2>
        {c.tests.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">No test changed status between the two runs.</p>
        ) : (
          <DataTable<CompareTest>
            caption="Test comparison"
            rows={c.tests}
            rowKey={(r) => r.node_id}
            columns={[
              {
                key: "test",
                header: "Test",
                render: (r) => <span className="font-mono text-xs">{r.node_id}</span>,
              },
              {
                key: "base",
                header: c.base.display_id,
                render: (r) => (r.base ? <StatusBadge state={r.base} /> : "—"),
              },
              {
                key: "other",
                header: c.other.display_id,
                render: (r) => (r.other ? <StatusBadge state={r.other} /> : "—"),
              },
              { key: "delta", header: "Δ", render: (r) => <DeltaChip delta={r.delta} /> },
            ]}
          />
        )}
      </section>
      <ScreenFooter id="SCR-04" name="Live Job Execution · run comparison" />
    </div>
  );
}
