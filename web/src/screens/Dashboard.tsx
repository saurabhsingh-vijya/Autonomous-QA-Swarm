import { AlertCircle, ArrowRight, Plus } from "lucide-react";
import { Link } from "react-router-dom";
import { useCapabilities, useJobs, useRepositories } from "../api/hooks";
import type { Job, JobState } from "../api/types";
import { TERMINAL_JOB_STATES } from "../api/types";
import { useProjectContext } from "../app/ProjectContext";
import { STATE_TONES } from "../components/status";
import {
  DataTable,
  EmptyState,
  ErrorState,
  LinkButton,
  PageHeader,
  Skeleton,
  SkeletonRows,
  StatusBadge,
  stateLabel,
} from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime, profilesSummary, repoShortName } from "../lib/format";
import { screenById } from "./registry";

const screen = screenById("SCR-01");

const BAR_COLORS: Record<string, string> = {
  grey: "bg-neutral",
  slate: "bg-neutral/60",
  blue: "bg-info",
  indigo: "bg-accent",
  green: "bg-ok",
  amber: "bg-warn",
  red: "bg-danger",
  violet: "bg-violet",
  orange: "bg-orange",
};

function Tile({
  label,
  value,
  note,
  loading,
  to,
}: {
  label: string;
  value: number | string;
  note?: string;
  loading?: boolean;
  to?: string;
}) {
  const body = (
    <>
      <div className="text-xs text-muted">{label}</div>
      {loading ? (
        <Skeleton className="mt-1.5 h-7 w-12" />
      ) : (
        <div className="mt-1 text-xl font-semibold tabular-nums text-text">{value}</div>
      )}
      {note ? <div className="mt-1 text-2xs text-muted">{note}</div> : null}
    </>
  );
  return to ? (
    <Link to={to} className="card block p-3.5 rao-transition hover:border-line-strong">
      {body}
    </Link>
  ) : (
    <div className="card p-3.5">{body}</div>
  );
}

function NotYet({ label, slice, detail }: { label: string; slice: string; detail: string }) {
  return (
    <div className="card p-3.5">
      <div className="text-xs text-muted">{label}</div>
      <div className="mt-1 text-sm font-medium text-text">No data yet</div>
      <div className="mt-1 text-2xs text-muted">
        {detail} Arrives in slice {slice}.
      </div>
    </div>
  );
}

export function DashboardScreen() {
  const { projectId, project, projects, isLoading: projectsLoading } = useProjectContext();
  const repos = useRepositories(projectId);
  const jobs = useJobs({ limit: 200, project_id: projectId });
  const caps = useCapabilities();
  const repoById = new Map((repos.data?.items ?? []).map((r) => [r.id, r]));
  const jobItems = jobs.data?.items ?? [];
  const active = jobItems.filter((j) => !TERMINAL_JOB_STATES.includes(j.state));
  const held = jobItems.filter((j) => j.state === "validating" && j.held_reason);
  const sample = projects.some((p) => p.org_name?.includes("(sample org)"));
  const scope = project ? project.name : "all projects";

  const byState = jobItems.reduce<Record<string, number>>((acc, j) => {
    acc[j.state] = (acc[j.state] ?? 0) + 1;
    return acc;
  }, {});
  const stateEntries = Object.entries(byState).sort((a, b) => b[1] - a[1]) as [JobState, number][];

  const firstRun = !repos.isLoading && !projectsLoading && (repos.data?.items.length ?? 0) === 0;
  const dbDown = Boolean(caps.data && caps.data.database && !caps.data.database.available);

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Home" }, { label: "Dashboard" }]}
        title="QA Health Overview"
        subtitle={`Counts for ${scope}. Everything here is read from the local database; the platform recommends and a QA Lead decides (HA-10).`}
        actions={
          <LinkButton to="/jobs/new" variant="primary">
            <Plus className="h-4 w-4" aria-hidden="true" /> New QA job
          </LinkButton>
        }
      />

      {firstRun ? (
        <section className="card mb-5 p-5" aria-labelledby="first-run">
          <h2 id="first-run" className="text-md font-semibold text-text">
            Get started in three steps
          </h2>
          <p className="mt-1 text-sm text-muted">
            RaOne runs entirely on this machine. Nothing is fetched or executed until later slices;
            today you can set up projects, register repositories and create held jobs.
          </p>
          <ol className="mt-4 grid gap-3 md:grid-cols-3">
            {[
              {
                n: 1,
                title: "Create a project",
                text: "Projects group repositories and, later, gate thresholds.",
                to: "/repositories?new=project",
                cta: "Create project",
                done: projects.length > 0,
              },
              {
                n: 2,
                title: "Add a repository",
                text: "An HTTPS URL on an allow-listed host. Checked syntactically only.",
                to: "/repositories?new=repository",
                cta: "Add repository",
                done: false,
              },
              {
                n: 3,
                title: "Create a QA job",
                text: "The job is created and held at Intake & Pinning until slice 1b.",
                to: "/jobs/new",
                cta: "New QA job",
                done: false,
              },
            ].map((s) => (
              <li key={s.n} className="rounded-md border border-line bg-canvas p-3.5">
                <div className="flex items-center gap-2 text-sm font-medium text-text">
                  <span
                    className={`flex h-5 w-5 items-center justify-center rounded-full text-2xs ${
                      s.done ? "bg-ok text-white" : "border border-line-strong text-muted"
                    }`}
                  >
                    {s.n}
                  </span>
                  {s.title}
                </div>
                <p className="mt-1.5 text-xs text-muted">{s.text}</p>
                <div className="mt-3">
                  <LinkButton to={s.to} size="sm" variant={s.done ? "secondary" : "primary"}>
                    {s.done ? "Done, add another" : s.cta}
                    <ArrowRight className="h-3.5 w-3.5" aria-hidden="true" />
                  </LinkButton>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : null}

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Tile
          label="Projects"
          value={projects.length}
          loading={projectsLoading}
          to="/repositories"
        />
        <Tile
          label="Repositories"
          value={repos.data?.items.length ?? 0}
          loading={repos.isLoading}
          note="Syntactic validation only in this slice"
          to="/repositories"
        />
        <Tile label="Jobs" value={jobItems.length} loading={jobs.isLoading} to="/jobs" />
        <Tile
          label="Active jobs"
          value={active.length}
          loading={jobs.isLoading}
          note="Non-terminal states"
          to="/jobs"
        />
      </div>

      <div className="mb-5 grid gap-3 lg:grid-cols-3">
        <section className="card p-3.5 lg:col-span-2" aria-labelledby="states-heading">
          <h2 id="states-heading" className="text-xs text-muted">
            Jobs by state
          </h2>
          {jobs.isLoading ? (
            <Skeleton className="mt-2 h-2.5" />
          ) : jobItems.length === 0 ? (
            <p className="mt-1.5 text-sm text-muted">No jobs yet for {scope}.</p>
          ) : (
            <>
              <div
                className="mt-2 flex h-2.5 w-full overflow-hidden rounded bg-raised"
                role="img"
                aria-label={stateEntries.map(([s, n]) => `${stateLabel(s)} ${n}`).join(", ")}
              >
                {stateEntries.map(([s, n]) => (
                  <span
                    key={s}
                    className={BAR_COLORS[STATE_TONES[s] ?? "grey"]}
                    style={{ width: `${(n / jobItems.length) * 100}%` }}
                  />
                ))}
              </div>
              <ul className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs">
                {stateEntries.map(([s, n]) => (
                  <li key={s} className="flex items-center gap-1.5">
                    <span
                      className={`h-2 w-2 rounded-sm ${BAR_COLORS[STATE_TONES[s] ?? "grey"]}`}
                      aria-hidden="true"
                    />
                    <Link to={`/jobs?state=${s}`} className="text-muted hover:text-text">
                      {stateLabel(s)}
                    </Link>
                    <span className="tabular-nums text-text">{n}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
        </section>
        <section className="card p-3.5" aria-labelledby="attention-heading">
          <h2 id="attention-heading" className="text-xs text-muted">
            Needs attention
          </h2>
          <ul className="mt-2 space-y-1.5 text-sm">
            {dbDown || caps.isError ? (
              <li className="flex items-start gap-2 text-danger">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                <span>
                  {caps.isError ? "The API is unreachable." : "The database is unreachable."}{" "}
                  <Link to="/settings" className="link">
                    System health
                  </Link>
                </span>
              </li>
            ) : null}
            {held.slice(0, 5).map((j) => (
              <li key={j.id} className="flex items-start gap-2">
                <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-warn" aria-hidden="true" />
                <span className="min-w-0">
                  <Link to={`/jobs/${j.id}`} className="mono link">
                    {j.display_id}
                  </Link>{" "}
                  <span className="text-muted">held: {j.held_reason}</span>
                </span>
              </li>
            ))}
            {held.length > 5 ? (
              <li className="text-xs text-muted">
                <Link to="/jobs?state=validating" className="link">
                  {held.length - 5} more held jobs
                </Link>
              </li>
            ) : null}
            {!dbDown && !caps.isError && held.length === 0 ? (
              <li className="text-muted">Nothing needs attention.</li>
            ) : null}
          </ul>
        </section>
      </div>

      <div className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-3">
        <NotYet
          label="Test results"
          slice="1d"
          detail="No test has run: this build executes nothing."
        />
        <NotYet
          label="Open defects"
          slice="2b"
          detail="Findings need reproduced evidence; none exist."
        />
        <NotYet
          label="Quality gates"
          slice="2d"
          detail="QG-01 to QG-08 are evaluated at reporting."
        />
      </div>

      <section className="card" aria-labelledby="recent-heading">
        <div className="flex items-center justify-between border-b border-line px-3.5 py-2.5">
          <h2 id="recent-heading" className="text-sm font-semibold text-text">
            Recent jobs
            {jobs.data ? (
              <span className="ml-2 text-xs font-normal text-muted">
                {Math.min(jobItems.length, 10)} of {jobItems.length}, newest first
              </span>
            ) : null}
          </h2>
          <Link to="/jobs" className="link text-xs">
            View all jobs
          </Link>
        </div>
        {jobs.isLoading ? <SkeletonRows label="Loading jobs" /> : null}
        {jobs.isError ? <ErrorState error={jobs.error} onRetry={() => jobs.refetch()} /> : null}
        {jobs.data && jobItems.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No jobs yet"
              description="Register a repository, then create a QA job. The job is held at Intake & Pinning; nothing runs on the control plane."
              action={
                <>
                  <LinkButton to="/repositories" variant="primary">
                    Add a repository
                  </LinkButton>
                  <LinkButton to="/jobs/new">New QA job</LinkButton>
                </>
              }
            />
          </div>
        ) : null}
        {jobs.data && jobItems.length > 0 ? (
          <DataTable<Job>
            caption="Recent jobs"
            rows={jobItems.slice(0, 10)}
            rowKey={(j) => j.id}
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
                render: (j) => {
                  const r = repoById.get(j.repository_id);
                  return <span className="mono">{r ? repoShortName(r.url) : j.repository_id}</span>;
                },
              },
              {
                key: "ref",
                header: "Ref",
                render: (j) => (
                  <span className="mono">
                    {j.ref}
                    {j.commit_sha ? ` ${j.commit_sha.slice(0, 10)}` : ""}
                  </span>
                ),
              },
              { key: "profiles", header: "Profiles", render: (j) => profilesSummary(j.profiles) },
              {
                key: "state",
                header: "State",
                sortValue: (j) => j.state,
                render: (j) => <StatusBadge state={j.state} />,
              },
              {
                key: "created",
                header: "Created",
                sortValue: (j) => j.created_at,
                render: (j) => <span className="tabular-nums">{formatTime(j.created_at)}</span>,
              },
            ]}
          />
        ) : null}
      </section>
      {sample ? (
        <p className="mt-3 text-xs text-warn">Sample data — no repository code executed</p>
      ) : null}
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
