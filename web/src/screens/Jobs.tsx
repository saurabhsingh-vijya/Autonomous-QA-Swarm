import { Plus, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useJobs, useRepositories } from "../api/hooks";
import type { Job, JobState } from "../api/types";
import { JOB_STATES, TERMINAL_JOB_STATES } from "../api/types";
import { useProjectContext } from "../app/ProjectContext";
import {
  DataTable,
  EmptyState,
  ErrorState,
  LinkButton,
  PageHeader,
  Pagination,
  SkeletonRows,
  StatusBadge,
  useCursorPager,
} from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime, profilesSummary, repoShortName } from "../lib/format";
import { screenById } from "./registry";

const screen = screenById("SCR-04");

type Filter = "all" | "active" | "terminal" | JobState;

const CHIPS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "active", label: "Active" },
  { id: "terminal", label: "Finished" },
  { id: "validating", label: "Held at intake" },
  { id: "cancelled", label: "Cancelled" },
];

export function JobsScreen() {
  const [params, setParams] = useSearchParams();
  const initial = params.get("state") as Filter | null;
  const [filter, setFilter] = useState<Filter>(initial ?? "all");
  const [query, setQuery] = useState("");
  const pager = useCursorPager();
  const { projectId, project } = useProjectContext();

  useEffect(() => {
    pager.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filter, projectId]);

  const stateParam: JobState[] | undefined =
    filter === "all"
      ? undefined
      : filter === "active"
        ? JOB_STATES.filter((s) => !TERMINAL_JOB_STATES.includes(s))
        : filter === "terminal"
          ? TERMINAL_JOB_STATES
          : [filter];
  const jobs = useJobs({
    state: stateParam,
    limit: 50,
    cursor: pager.cursor,
    project_id: projectId,
  });
  const repos = useRepositories();
  const repoById = new Map((repos.data?.items ?? []).map((r) => [r.id, r]));

  const q = query.trim().toLowerCase();
  const rows = (jobs.data?.items ?? []).filter(
    (j) =>
      !q ||
      j.display_id.toLowerCase().includes(q) ||
      j.ref.toLowerCase().includes(q) ||
      (repoById.get(j.repository_id)?.url.toLowerCase().includes(q) ?? false),
  );

  const choose = (f: Filter) => {
    setFilter(f);
    if (f === "all") params.delete("state");
    else params.set("state", f);
    setParams(params, { replace: true });
  };

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Jobs" }]}
        title="Live Job Execution"
        subtitle={`Jobs for ${project ? project.name : "all projects"}, newest first. Open a job for its stage rail, held reason and live event stream.`}
        actions={
          <LinkButton to="/jobs/new" variant="primary">
            <Plus className="h-4 w-4" aria-hidden="true" /> New QA job
          </LinkButton>
        }
      />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div role="group" aria-label="Filter by state" className="flex flex-wrap gap-1.5">
          {CHIPS.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => choose(c.id)}
              aria-pressed={filter === c.id}
              className={`h-7 rounded-md border px-2.5 text-xs rao-transition ${
                filter === c.id
                  ? "border-accent bg-accent/15 text-text"
                  : "border-line text-muted hover:border-line-strong hover:text-text"
              }`}
            >
              {c.label}
            </button>
          ))}
        </div>
        <label className="relative ml-auto">
          <span className="sr-only">Search jobs</span>
          <Search
            className="pointer-events-none absolute left-2 top-1.5 h-3.5 w-3.5 text-muted"
            aria-hidden="true"
          />
          <input
            type="search"
            className="input h-7 w-56 pl-7"
            placeholder="Job id, ref or repository"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
        </label>
      </div>
      <section className="card" aria-label="Jobs">
        {jobs.isLoading ? <SkeletonRows label="Loading jobs" /> : null}
        {jobs.isError ? <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} /> : null}
        {jobs.data && jobs.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title={filter === "all" ? "No jobs yet" : "No jobs match this filter"}
              description="Create a QA job from a registered repository. It is created and held at Intake & Pinning."
              action={
                <LinkButton to="/jobs/new" variant="primary">
                  New QA job
                </LinkButton>
              }
            />
          </div>
        ) : null}
        {jobs.data && jobs.data.items.length > 0 ? (
          <>
            <DataTable<Job>
              caption="Jobs"
              rows={rows}
              rowKey={(j) => j.id}
              emptyLabel="No jobs match your search on this page."
              columns={[
                {
                  key: "job",
                  header: "Job",
                  sortValue: (j) => j.display_id,
                  render: (j) => (
                    <Link to={`/jobs/${j.id}`} className="mono font-medium text-accent">
                      {j.display_id}
                    </Link>
                  ),
                },
                {
                  key: "repo",
                  header: "Repository",
                  sortValue: (j) => repoById.get(j.repository_id)?.url ?? j.repository_id,
                  render: (j) => {
                    const r = repoById.get(j.repository_id);
                    return (
                      <span className="mono">{r ? repoShortName(r.url) : j.repository_id}</span>
                    );
                  },
                },
                {
                  key: "ref",
                  header: "Ref",
                  sortValue: (j) => j.ref,
                  render: (j) => (
                    <span className="mono">
                      {j.ref}
                      {j.commit_sha ? (
                        <span className="text-muted" title={j.commit_sha}>
                          {" "}
                          @ {j.commit_sha.slice(0, 8)}
                        </span>
                      ) : null}
                    </span>
                  ),
                },
                {
                  key: "profiles",
                  header: "Profiles",
                  render: (j) => profilesSummary(j.profiles),
                },
                {
                  key: "state",
                  header: "State",
                  sortValue: (j) => j.state,
                  render: (j) => <StatusBadge state={j.state} />,
                },
                {
                  key: "held",
                  header: "Note",
                  render: (j) => <span className="text-muted">{j.held_reason ?? ""}</span>,
                },
                {
                  key: "created",
                  header: "Created",
                  sortValue: (j) => j.created_at,
                  render: (j) => <span className="tabular-nums">{formatTime(j.created_at)}</span>,
                },
              ]}
            />
            <Pagination
              page={pager.page}
              canPrev={pager.canPrev}
              nextCursor={jobs.data.next_cursor}
              onNext={pager.next}
              onPrev={pager.prev}
              shown={rows.length}
            />
          </>
        ) : null}
      </section>
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
