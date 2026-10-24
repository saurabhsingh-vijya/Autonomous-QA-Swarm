import { Link, useParams } from "react-router-dom";
import { useCompare } from "../api/hooks";
import type { CompareCheck, CompareTest, Delta } from "../api/types";
import { Badge, DataTable, ErrorState, PageHeader, SkeletonRows, StatusBadge } from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { DELTA_LABEL, DELTA_TONE, summarizeDeltas } from "../lib/compare";
import { formatTime } from "../lib/format";

function DeltaChip({ delta }: { delta: Delta }) {
  return (
    <span data-delta={delta}>
      <Badge tone={DELTA_TONE[delta]}>{DELTA_LABEL[delta]}</Badge>
    </span>
  );
}

/**
 * Two runs of the same repository side by side. Deltas are computed by the API from persisted
 * check runs and test executions and describe the base job relative to the other one.
 */
export function CompareRunsScreen() {
  const { jobId = "", otherId = "" } = useParams();
  const cmp = useCompare(jobId, otherId);
  if (cmp.isLoading) return <SkeletonRows rows={6} label="Comparing runs" />;
  if (cmp.isError || !cmp.data)
    return (
      <div>
        <PageHeader crumbs={[{ label: "Jobs", to: "/jobs" }]} title="Compare runs" />
        <ErrorState
          error={cmp.error ?? new Error("Comparison unavailable")}
          onRetry={() => cmp.refetch()}
        />
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
      <div className="mb-5 grid grid-cols-1 gap-4 md:grid-cols-2">
        {[c.base, c.other].map((j, i) => (
          <section key={j.id} className="card p-4 text-sm" aria-label={i === 0 ? "Base" : "Other"}>
            <div className="text-2xs font-medium text-muted">{i === 0 ? "Base" : "Other"}</div>
            <div className="mt-1 flex items-center gap-2">
              <Link to={`/jobs/${j.id}`} className="mono link text-base font-semibold">
                {j.display_id}
              </Link>
              <StatusBadge state={j.state} />
            </div>
            <div className="mt-1 text-muted">
              <span className="mono">{j.ref}</span> →{" "}
              <span className="mono">{j.commit_sha?.slice(0, 12) ?? "not pinned"}</span>
              {j.created_at ? ` · ${formatTime(j.created_at)}` : ""}
            </div>
            <div className="mt-1 text-xs text-muted">
              tests: {counts(i === 0 ? c.test_counts.base : c.test_counts.other)}
            </div>
          </section>
        ))}
      </div>
      <section className="card mb-5" aria-labelledby="cmp-checks-heading">
        <h2
          id="cmp-checks-heading"
          className="border-b border-line px-3.5 py-2.5 text-sm font-semibold text-text"
        >
          Checks
        </h2>
        {c.checks.length === 0 ? (
          <p className="p-4 text-sm text-muted">Neither run recorded a check.</p>
        ) : (
          <DataTable<CompareCheck>
            caption="Check comparison"
            rows={c.checks}
            rowKey={(r) => `${r.engine}:${r.name}`}
            columns={[
              {
                key: "check",
                header: "Check",
                render: (r) => (
                  <span>
                    <span className="mono text-muted">{r.engine}</span>{" "}
                    <span className="text-text">{r.name}</span>
                  </span>
                ),
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
              { key: "delta", header: "Delta", render: (r) => <DeltaChip delta={r.delta} /> },
            ]}
          />
        )}
      </section>
      <section className="card" aria-labelledby="cmp-tests-heading">
        <h2
          id="cmp-tests-heading"
          className="border-b border-line px-3.5 py-2.5 text-sm font-semibold text-text"
        >
          Tests that changed <span className="font-normal text-muted">{c.tests.length} shown</span>
        </h2>
        {c.tests.length === 0 ? (
          <p className="p-4 text-sm text-muted">No test changed status between the two runs.</p>
        ) : (
          <DataTable<CompareTest>
            caption="Test comparison"
            rows={c.tests}
            rowKey={(r) => r.node_id}
            columns={[
              {
                key: "test",
                header: "Test",
                render: (r) => <span className="mono text-xs">{r.node_id}</span>,
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
              { key: "delta", header: "Delta", render: (r) => <DeltaChip delta={r.delta} /> },
            ]}
          />
        )}
      </section>
      <ScreenFooter id="SCR-04" name="Live Job Execution · run comparison" />
    </div>
  );
}
