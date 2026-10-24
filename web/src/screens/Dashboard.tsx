import { Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { useJobs, useProjects, useRepositories } from "../api/hooks";
import type { Job } from "../api/types";
import { TERMINAL_JOB_STATES } from "../api/types";
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

const screen = screenById("SCR-01");

function Tile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="card p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className="mt-1 text-2xl font-semibold text-slate-900">{value}</div>
      {note ? <div className="mt-1 text-xs text-slate-500">{note}</div> : null}
    </div>
  );
}

export function DashboardScreen() {
  const projects = useProjects();
  const repos = useRepositories();
  const jobs = useJobs({ limit: 20 });
  const repoById = new Map((repos.data?.items ?? []).map((r) => [r.id, r]));
  const active = (jobs.data?.items ?? []).filter((j) => !TERMINAL_JOB_STATES.includes(j.state));
  const sample = projects.data?.items.some((p) => p.org_name?.includes("(sample org)"));

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Home" }, { label: "Dashboard" }]}
        title="QA Health Overview"
        subtitle="Release readiness, open findings and pipeline health for the latest jobs · the platform recommends, the QA Lead decides (HA-10)."
        actions={
          <Link to="/jobs/new" className="btn-primary">
            <Plus className="h-4 w-4" aria-hidden="true" /> New QA job
          </Link>
        }
      />
      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-4">
        <Tile
          label="Projects"
          value={projects.isLoading ? "…" : String(projects.data?.items.length ?? 0)}
        />
        <Tile
          label="Repositories"
          value={repos.isLoading ? "…" : String(repos.data?.items.length ?? 0)}
          note="validated when a job pins them"
        />
        <Tile
          label="Active jobs"
          value={jobs.isLoading ? "…" : String(active.length)}
          note="non-terminal states"
        />
        <Tile
          label="Agent pool / Quality gates"
          value="—"
          note="Not implemented in this phase (slice 1c / 2d)"
        />
      </div>

      <section className="card">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">
            Recent jobs{" "}
            <span className="font-normal text-slate-500">
              {jobs.data ? `${jobs.data.items.length} shown · newest first` : ""}
            </span>
          </h2>
          <Link to="/jobs" className="text-sm text-primary hover:underline">
            View all
          </Link>
        </div>
        {jobs.isLoading ? <LoadingState label="Loading jobs" /> : null}
        {jobs.isError ? (
          <div className="p-4">
            <ProblemAlert error={jobs.error} />
          </div>
        ) : null}
        {jobs.data && jobs.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No jobs yet"
              description="Add a repository, then create a QA job. The scheduler pins the commit and the Execution Service runs the checks."
              action={
                <Link to="/repositories" className="btn-primary">
                  Add a repository
                </Link>
              }
            />
          </div>
        ) : null}
        {jobs.data && jobs.data.items.length > 0 ? (
          <DataTable<Job>
            caption="Recent jobs"
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
                header: "Ref → commit",
                render: (j) => `${j.ref} → ${j.commit_sha ?? "not pinned"}`,
              },
              { key: "profiles", header: "Profiles", render: (j) => profilesSummary(j.profiles) },
              { key: "state", header: "State", render: (j) => <StatusBadge state={j.state} /> },
              { key: "reason", header: "Reason", render: (j) => j.held_reason ?? "—" },
              {
                key: "created",
                header: "Created (local)",
                render: (j) => formatTime(j.created_at),
              },
            ]}
          />
        ) : null}
      </section>
      {sample ? (
        <p className="mt-3 text-xs text-amber-800">Sample data — no repository code executed</p>
      ) : null}
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
