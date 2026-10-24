import { Play } from "lucide-react";
import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useCreateJob, useProjects, useRepositories } from "../api/hooks";
import type { JobProfiles } from "../api/types";
import { EmptyState, PageHeader, ProblemAlert, toProblem } from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { screenById } from "./registry";

const screen = screenById("SCR-03");

export function NewJobScreen() {
  const navigate = useNavigate();
  const projects = useProjects();
  const [projectId, setProjectId] = useState("");
  const repos = useRepositories(projectId || undefined);
  const create = useCreateJob();
  const [repositoryId, setRepositoryId] = useState("");
  const [ref, setRef] = useState("main");
  const [profiles, setProfiles] = useState<JobProfiles>({
    functional: "standard",
    security: "quick",
    performance: "none",
  });
  const [forceNew, setForceNew] = useState(false);

  const projectItems = projects.data?.items ?? [];
  const repoItems = (repos.data?.items ?? []).filter(
    (r) => !projectId || r.project_id === projectId,
  );
  const problem = create.error ? toProblem(create.error) : null;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const job = await create.mutateAsync({
        repository_id: repositoryId,
        ref: ref.trim(),
        profiles,
        force_new: forceNew,
      });
      navigate(`/jobs/${job.id}`);
    } catch {
      /* shown via ProblemAlert */
    }
  };

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Jobs", to: "/jobs" }, { label: "New QA job" }]}
        title="New QA job"
        badge={
          <span className="rounded border border-slate-300 px-2 py-0.5 text-xs font-medium text-slate-600">
            Draft
          </span>
        }
        subtitle="The job is created in validating; the scheduler pins the ref to a commit, plans the checks and the Execution Service runs them. Repository code (pytest) runs only where the exec host explicitly allows it."
      />
      {projects.data && projectItems.length === 0 ? (
        <EmptyState
          title="No projects or repositories"
          description="Create a project and register a repository before launching a job."
          action={
            <Link to="/repositories" className="btn-primary">
              Go to Repositories &amp; Projects
            </Link>
          }
        />
      ) : (
        <form onSubmit={submit} className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <div className="card space-y-4 p-5 lg:col-span-2">
            {problem ? (
              <ProblemAlert error={create.error}>
                {problem.error_code === "job_duplicate_active" && problem.existing_job ? (
                  <p className="mt-2">
                    Existing job:{" "}
                    <Link
                      to={`/jobs/${problem.existing_job.id}`}
                      className="font-mono font-medium underline"
                    >
                      {problem.existing_job.display_id}
                    </Link>{" "}
                    ({problem.existing_job.state}). {problem.hint}
                  </p>
                ) : null}
              </ProblemAlert>
            ) : null}
            <h2 className="text-sm font-semibold text-slate-900">1 · Source</h2>
            <div>
              <label htmlFor="job-project" className="label">
                Project
              </label>
              <select
                id="job-project"
                className="input"
                value={projectId}
                onChange={(e) => {
                  setProjectId(e.target.value);
                  setRepositoryId("");
                }}
                required
              >
                <option value="">Select a project…</option>
                {projectItems.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <label htmlFor="job-repository" className="label">
                Repository
              </label>
              <select
                id="job-repository"
                className="input"
                value={repositoryId}
                onChange={(e) => setRepositoryId(e.target.value)}
                required
                disabled={!projectId || repos.isLoading}
              >
                <option value="">
                  {!projectId
                    ? "Select a project first"
                    : repos.isLoading
                      ? "Loading…"
                      : repoItems.length
                        ? "Select a repository…"
                        : "No repositories in this project"}
                </option>
                {repoItems.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.url.replace(/^https:\/\//, "")} ({r.validation_status})
                  </option>
                ))}
              </select>
              {repos.isError ? (
                <div className="mt-2">
                  <ProblemAlert error={repos.error} />
                </div>
              ) : null}
            </div>
            <div>
              <label htmlFor="job-ref" className="label">
                Ref (branch, tag or PR ref)
              </label>
              <input
                id="job-ref"
                className="input font-mono"
                value={ref}
                onChange={(e) => setRef(e.target.value)}
                required
                maxLength={255}
              />
              <p className="mt-1 text-xs text-slate-500">
                Resolved to an immutable commit SHA during validating (git ls-remote).
              </p>
            </div>

            <h2 className="pt-2 text-sm font-semibold text-slate-900">3 · Profiles</h2>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <div>
                <label htmlFor="prof-functional" className="label">
                  Functional
                </label>
                <select
                  id="prof-functional"
                  className="input"
                  value={profiles.functional}
                  onChange={(e) =>
                    setProfiles({
                      ...profiles,
                      functional: e.target.value as JobProfiles["functional"],
                    })
                  }
                >
                  <option value="none">None</option>
                  <option value="standard">Standard</option>
                </select>
              </div>
              <div>
                <label htmlFor="prof-security" className="label">
                  Security
                </label>
                <select
                  id="prof-security"
                  className="input"
                  value={profiles.security}
                  onChange={(e) =>
                    setProfiles({
                      ...profiles,
                      security: e.target.value as JobProfiles["security"],
                    })
                  }
                >
                  <option value="none">None</option>
                  <option value="quick">Quick</option>
                  <option value="standard">Standard</option>
                </select>
                <p className="mt-1 text-xs text-slate-500">Deep (DAST) is Future — Phase 4.</p>
              </div>
              <div>
                <label htmlFor="prof-performance" className="label">
                  Performance
                </label>
                <select
                  id="prof-performance"
                  className="input"
                  value={profiles.performance}
                  onChange={(e) =>
                    setProfiles({
                      ...profiles,
                      performance: e.target.value as JobProfiles["performance"],
                    })
                  }
                >
                  <option value="none">None</option>
                  <option value="smoke">Smoke</option>
                  <option value="baseline">Baseline (HA-03)</option>
                </select>
                <p className="mt-1 text-xs text-slate-500">
                  Load / Stress / Spike / Soak are Future.
                </p>
              </div>
            </div>
            <label className="flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={forceNew}
                onChange={(e) => setForceNew(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300"
              />
              Force new job (QA Lead only)
            </label>
          </div>

          <aside className="space-y-4">
            <div className="card p-5">
              <h2 className="text-sm font-semibold text-slate-900">Policy summary</h2>
              <p className="mt-2 text-sm text-slate-600">
                Policy Engine evaluation arrives in slice 2c. In slice 1a the job is created, moved
                to <span className="font-mono">validating</span> and held with reason &ldquo;intake
                arrives in slice 1b&rdquo;. No approval is requested and no sandbox starts.
              </p>
            </div>
            <div className="card p-5 text-sm text-slate-600">
              <strong className="text-slate-900">Idempotent launch.</strong> Sent with a generated{" "}
              <span className="font-mono">Idempotency-Key</span>. An active job for the same
              repository, ref and profile hash returns 409 with a link to it.
            </div>
            <div className="card flex items-center justify-between p-5">
              <Link to="/jobs" className="btn-secondary">
                Back
              </Link>
              <button
                type="submit"
                className="btn-primary"
                disabled={create.isPending || !repositoryId || !ref.trim()}
              >
                <Play className="h-4 w-4" aria-hidden="true" /> Launch job
              </button>
            </div>
          </aside>
        </form>
      )}
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
