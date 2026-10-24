import { ArrowLeft, ArrowRight, Play } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useCreateJob, useProjects, useRepositories } from "../api/hooks";
import { problemSummary } from "../api/problem";
import type { JobProfiles } from "../api/types";
import { useProjectContext } from "../app/ProjectContext";
import {
  Badge,
  Button,
  EmptyState,
  Input,
  KeyValue,
  LinkButton,
  PageHeader,
  ProblemAlert,
  Select,
  toProblem,
  useToast,
} from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { profilesSummary, repoShortName } from "../lib/format";
import { screenById } from "./registry";

const screen = screenById("SCR-03");

const STEPS = ["Source", "Profiles", "Review"] as const;

export function NewJobScreen() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const projects = useProjects();
  const { projectId: contextProject } = useProjectContext();
  const allRepos = useRepositories();
  const create = useCreateJob();
  const { toast } = useToast();
  const [step, setStep] = useState(0);
  const [projectId, setProjectId] = useState(contextProject ?? "");
  const [repositoryId, setRepositoryId] = useState(params.get("repository") ?? "");
  const [ref, setRef] = useState("main");
  const [profiles, setProfiles] = useState<JobProfiles>({
    functional: "standard",
    security: "quick",
    performance: "none",
  });
  const [forceNew, setForceNew] = useState(false);

  const projectItems = projects.data?.items ?? [];
  const repoItems = (allRepos.data?.items ?? []).filter(
    (r) => !projectId || r.project_id === projectId,
  );
  const selectedRepo = (allRepos.data?.items ?? []).find((r) => r.id === repositoryId);

  // A repository deep link selects its project too.
  useEffect(() => {
    if (selectedRepo && !projectId) setProjectId(selectedRepo.project_id);
  }, [selectedRepo, projectId]);
  useEffect(() => {
    if (selectedRepo && selectedRepo.default_branch) setRef(selectedRepo.default_branch);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedRepo?.id]);

  const problem = create.error ? toProblem(create.error) : null;
  const sourceValid = Boolean(repositoryId) && ref.trim().length > 0;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const job = await create.mutateAsync({
        repository_id: repositoryId,
        ref: ref.trim(),
        profiles,
        force_new: forceNew,
      });
      toast({
        kind: "success",
        title: "Job created",
        description: `${job.display_id} is held at Intake & Pinning.`,
      });
      navigate(`/jobs/${job.id}`);
    } catch (err) {
      toast({ kind: "error", title: "Job not created", description: problemSummary(err) });
    }
  };

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Jobs", to: "/jobs" }, { label: "New QA job" }]}
        title="New QA job"
        badge={<Badge tone="neutral">Draft</Badge>}
        subtitle="Choose a repository and ref, pick profiles, then review exactly what will happen. In this build the job is created and held; nothing executes."
      />
      {projects.data && projectItems.length === 0 ? (
        <EmptyState
          title="No projects or repositories"
          description="Create a project and register a repository before creating a job."
          action={
            <LinkButton to="/repositories" variant="primary">
              Go to Repositories &amp; Projects
            </LinkButton>
          }
        />
      ) : (
        <form onSubmit={submit} className="grid grid-cols-1 gap-5 lg:grid-cols-3">
          <div className="card lg:col-span-2">
            <ol className="flex border-b border-line" aria-label="Steps">
              {STEPS.map((label, i) => {
                const enabled = i === 0 || sourceValid;
                return (
                  <li key={label} className="flex-1">
                    <button
                      type="button"
                      onClick={() => enabled && setStep(i)}
                      disabled={!enabled}
                      aria-current={step === i ? "step" : undefined}
                      className={`flex h-10 w-full items-center justify-center gap-2 border-b-2 text-sm rao-transition disabled:cursor-not-allowed disabled:opacity-50 ${
                        step === i
                          ? "border-accent text-text"
                          : "border-transparent text-muted hover:text-text"
                      }`}
                    >
                      <span
                        className={`flex h-5 w-5 items-center justify-center rounded-full text-2xs ${
                          i < step ? "bg-ok text-white" : "border border-line-strong"
                        }`}
                        aria-hidden="true"
                      >
                        {i + 1}
                      </span>
                      {label}
                    </button>
                  </li>
                );
              })}
            </ol>

            <div className="space-y-4 p-5">
              {problem ? (
                <ProblemAlert error={create.error}>
                  {problem.error_code === "job_duplicate_active" && problem.existing_job ? (
                    <p className="mt-2 text-text">
                      Existing job{" "}
                      <Link to={`/jobs/${problem.existing_job.id}`} className="mono link">
                        {problem.existing_job.display_id}
                      </Link>{" "}
                      ({problem.existing_job.state.replace(/_/g, " ")}). {problem.hint}
                    </p>
                  ) : null}
                </ProblemAlert>
              ) : null}

              {step === 0 ? (
                <>
                  <Select
                    id="job-project"
                    label="Project"
                    value={projectId}
                    onChange={(e) => {
                      setProjectId(e.target.value);
                      setRepositoryId("");
                    }}
                    required
                  >
                    <option value="">Select a project</option>
                    {projectItems.map((p) => (
                      <option key={p.id} value={p.id}>
                        {p.name}
                      </option>
                    ))}
                  </Select>
                  <Select
                    id="job-repository"
                    label="Repository"
                    value={repositoryId}
                    onChange={(e) => setRepositoryId(e.target.value)}
                    required
                    disabled={!projectId || allRepos.isLoading}
                    hint={
                      !projectId
                        ? "Select a project first."
                        : repoItems.length === 0 && !allRepos.isLoading
                          ? "This project has no repositories yet."
                          : undefined
                    }
                  >
                    <option value="">
                      {allRepos.isLoading ? "Loading" : "Select a repository"}
                    </option>
                    {repoItems.map((r) => (
                      <option key={r.id} value={r.id}>
                        {repoShortName(r.url)} ({r.validation_status.replace(/_/g, " ")})
                      </option>
                    ))}
                  </Select>
                  {allRepos.isError ? <ProblemAlert error={allRepos.error} /> : null}
                  <Input
                    id="job-ref"
                    label="Ref (branch, tag or PR ref)"
                    className="font-mono"
                    value={ref}
                    onChange={(e) => setRef(e.target.value)}
                    required
                    maxLength={255}
                    hint="Resolved to an immutable commit SHA during validating, from slice 1b."
                  />
                </>
              ) : null}

              {step === 1 ? (
                <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
                  <Select
                    id="prof-functional"
                    label="Functional"
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
                  </Select>
                  <Select
                    id="prof-security"
                    label="Security"
                    value={profiles.security}
                    onChange={(e) =>
                      setProfiles({
                        ...profiles,
                        security: e.target.value as JobProfiles["security"],
                      })
                    }
                    hint="Deep (DAST) is a Phase 4 profile and is not offered."
                  >
                    <option value="none">None</option>
                    <option value="quick">Quick</option>
                    <option value="standard">Standard</option>
                  </Select>
                  <Select
                    id="prof-performance"
                    label="Performance"
                    value={profiles.performance}
                    onChange={(e) =>
                      setProfiles({
                        ...profiles,
                        performance: e.target.value as JobProfiles["performance"],
                      })
                    }
                    hint="Baseline needs HA-03 once approvals exist. Load, stress, spike and soak are Phase 4."
                  >
                    <option value="none">None</option>
                    <option value="smoke">Smoke</option>
                    <option value="baseline">Baseline</option>
                  </Select>
                  <label className="flex items-center gap-2 text-sm text-text md:col-span-3">
                    <input
                      type="checkbox"
                      checked={forceNew}
                      onChange={(e) => setForceNew(e.target.checked)}
                      className="h-4 w-4 rounded border-line-strong bg-canvas accent-[rgb(var(--c-accent))]"
                    />
                    Force a new job even if an equivalent one is active (QA Lead only)
                  </label>
                </div>
              ) : null}

              {step === 2 ? (
                <div className="space-y-4">
                  <KeyValue
                    columns={2}
                    items={[
                      {
                        label: "Project",
                        value: projectItems.find((p) => p.id === projectId)?.name ?? "—",
                      },
                      {
                        label: "Repository",
                        value: selectedRepo ? repoShortName(selectedRepo.url) : "—",
                        mono: true,
                      },
                      { label: "Ref", value: ref, mono: true },
                      { label: "Profiles", value: profilesSummary(profiles) },
                      { label: "Force new", value: forceNew ? "Yes" : "No" },
                    ]}
                  />
                  <div className="rounded-md border border-line bg-canvas p-3 text-sm text-text">
                    <p className="font-medium">What will happen</p>
                    <ol className="mt-1.5 list-decimal space-y-1 pl-5 text-muted">
                      <li>
                        The request is sent once with a generated Idempotency-Key; a repeat returns
                        the same job.
                      </li>
                      <li>
                        If an equivalent job is active for this repository, ref and profiles, you
                        get a link to it instead (409).
                      </li>
                      <li>
                        The job is created, moved to validating and held at Intake & Pinning: intake
                        arrives in slice 1b.
                      </li>
                      <li>No code is fetched, built or run. No approval is requested.</li>
                    </ol>
                  </div>
                </div>
              ) : null}

              <div className="flex items-center justify-between border-t border-line pt-4">
                <Button
                  onClick={() => setStep((s) => Math.max(0, s - 1))}
                  disabled={step === 0}
                  variant="ghost"
                >
                  <ArrowLeft className="h-4 w-4" aria-hidden="true" /> Back
                </Button>
                {step < 2 ? (
                  <Button
                    variant="primary"
                    onClick={() => setStep((s) => s + 1)}
                    disabled={!sourceValid}
                  >
                    Continue <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    variant="primary"
                    loading={create.isPending}
                    disabled={!sourceValid}
                  >
                    <Play className="h-4 w-4" aria-hidden="true" /> Create job
                  </Button>
                )}
              </div>
            </div>
          </div>

          <aside className="space-y-4">
            <div className="card p-4 text-sm">
              <h2 className="font-semibold text-text">Policy summary</h2>
              <p className="mt-1.5 text-muted">
                Policy Engine evaluation arrives in slice 2c. Until then no approval is requested
                and no sandbox starts; the job record and audit trail are real.
              </p>
            </div>
            <div className="card p-4 text-sm text-muted">
              <h2 className="font-semibold text-text">Local by default</h2>
              <p className="mt-1.5">
                The request goes to the local API only. Nothing is sent to an external service.
              </p>
            </div>
          </aside>
        </form>
      )}
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
