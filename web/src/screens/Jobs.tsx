import { Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { useJobs, useRepositories } from "../api/hooks";
import type { Job, JobState } from "../api/types";
import { JOB_STATES, TERMINAL_JOB_STATES } from "../api/types";
import {
  DataTable,
  EmptyState,
  LoadingState,
  PageHeader,
  ProblemAlert,
  StatusBadge,
} from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime, profilesSummary } from "../lib/format";
import { screenById } from "./registry";

const screen = screenById("SCR-04");

type Filter = "all" | "active" | "terminal" | JobState;

export function JobsScreen() {
  const [filter, setFilter] = useState<Filter>("all");
  const stateParam: JobState[] | undefined =
    filter === "all"
      ? undefined
      : filter === "active"
        ? JOB_STATES.filter((s) => !TERMINAL_JOB_STATES.includes(s))
        : filter === "terminal"
          ? TERMINAL_JOB_STATES
          : [filter];
  const jobs = useJobs({ state: stateParam, limit: 100 });
  const repos = useRepositories();
  const repoById = new Map((repos.data?.items ?? []).map((r) => [r.id, r]));

  const chips: { id: Filter; label: string }[] = [
    { id: "all", label: "All" },
    { id: "active", label: "Active" },
    { id: "terminal", label: "Terminal" },
    { id: "validating", label: "Validating" },
    { id: "cancelled", label: "Cancelled" },
  ];

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Jobs" }]}
        title="Live Job Execution"
        subtitle="Jobs for this organisation, newest first. Open a job for its state, held reason and live event stream."
        actions={
          <Link to="/jobs/new" className="btn-primary">
            <Plus className="h-4 w-4" aria-hidden="true" /> New QA job
          </Link>
        }
      />
      <div className="mb-4 flex flex-wrap gap-2" role="group" aria-label="Filter by state">
        {chips.map((c) => (
          <button
            key={c.id}
            type="button"
            onClick={() => setFilter(c.id)}
            aria-pressed={filter === c.id}
            className={`rounded-full border px-3 py-1 text-sm ${
              filter === c.id
                ? "border-primary bg-primary-light text-primary"
                : "border-slate-300 bg-white text-slate-700"
            }`}
          >
            {c.label}
          </button>
        ))}
      </div>
      <section className="card">
        {jobs.isLoading ? <LoadingState label="Loading jobs" /> : null}
        {jobs.isError ? (
          <div className="p-4">
            <ProblemAlert error={jobs.error} />
          </div>
        ) : null}
        {jobs.data && jobs.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No jobs match this filter"
              description="Create a QA job from a registered repository."
              action={
                <Link to="/jobs/new" className="btn-primary">
                  New QA job
                </Link>
              }
            />
          </div>
        ) : null}
        {jobs.data && jobs.data.items.length > 0 ? (
          <DataTable<Job>
            caption="Jobs"
            rows={jobs.data.items}
            rowKey={(j) => j.id}
            columns={[
              {
                key: "job",
                header: "Job",
                render: (j) => (
                  <Link to={`/jobs/${j.id}`} className="font-mono text-sm font-medium text-primary">
                    {j.display_id}
                  </Link>
                ),
              },
              {
                key: "repo",
                header: "Repository",
                render: (j) =>
                  repoById.get(j.repository_id)?.url.replace(/^https:\/\//, "") ?? j.repository_id,
              },
              {
                key: "ref",
                header: "Ref",
                render: (j) => (
                  <span className="font-mono text-xs">
                    {j.ref}
                    {j.commit_sha ? (
                      <span className="text-slate-400"> @ {j.commit_sha.slice(0, 8)}</span>
                    ) : null}
                  </span>
                ),
              },
              { key: "profiles", header: "Profiles", render: (j) => profilesSummary(j.profiles) },
              { key: "state", header: "State", render: (j) => <StatusBadge state={j.state} /> },
              {
                key: "created",
                header: "Created (local)",
                render: (j) => formatTime(j.created_at),
              },
            ]}
          />
        ) : null}
      </section>
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
