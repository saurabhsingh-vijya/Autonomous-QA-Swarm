import { ArrowLeft, ArrowRight, Play, Plus, Trash2 } from "lucide-react";
import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useCreateJob, useProjects, useRepositories } from "../api/hooks";
import { problemSummary } from "../api/problem";
import type { ApiCheck, ApiCheckMethod, JobProfiles } from "../api/types";
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
  Textarea,
  toProblem,
  useToast,
} from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { profilesSummary, repoShortName } from "../lib/format";
import { QUICK_CHECK, checkWarning, parseRequirements } from "../lib/jobInputs";
import { screenById } from "./registry";

const screen = screenById("SCR-03");

const STEPS = ["Source", "Profiles", "Inputs", "Review"] as const;
const METHODS: ApiCheckMethod[] = ["GET", "HEAD", "OPTIONS"];

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
    security: "none",
    performance: "none",
  });
  const [forceNew, setForceNew] = useState(false);
  const [requirementsText, setRequirementsText] = useState("");
  const [checks, setChecks] = useState<ApiCheck[]>([]);
  const [requireApproval, setRequireApproval] = useState(false);

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
  const requirements = parseRequirements(requirementsText);
  const checksValid = checks.every((c) => c.url.trim().length >= 8);
  const hasInputs = requirements.length > 0 || checks.length > 0;
  const blockedChecks = checks.filter((c) => checkWarning(c)).length;

  const updateCheck = (i: number, patch: Partial<ApiCheck>) =>
    setChecks((prev) => prev.map((c, j) => (j === i ? { ...c, ...patch } : c)));

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const job = await create.mutateAsync({
        repository_id: repositoryId,
        ref: ref.trim(),
        profiles,
        inputs: {
          requirements,
          api_checks: checks.map((c) => ({ ...c, url: c.url.trim() })),
        },
        require_plan_approval: requireApproval,
        force_new: forceNew,
      });
      toast({
        kind: "success",
        title: "Job created",
        description:
          job.state === "awaiting_approval"
            ? `${job.display_id} is waiting for plan approval (HA-05).`
            : job.state === "running" || job.state === "queued"
              ? `${job.display_id} was admitted; tasks are running.`
              : job.state === "validating"
                ? `${job.display_id} is queued for intake and planning.`
                : `${job.display_id} is ${job.state.replace(/_/g, " ")}${
                    job.held_reason ? `: ${job.held_reason}` : ""
                  }.`,
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
        subtitle="Choose a repository and ref, pick profiles, supply the inputs agents work from, then review exactly what will happen. No repository code is fetched or executed."
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
                    hint="Resolved to an immutable commit SHA by the scheduler during Intake & Pinning (git ls-remote)."
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
                    hint="Standard plans the Functional Testing Agent; without an execution engine its scenarios are recorded as skipped, never passed."
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
                    hint="No security engine exists yet (slice 2a); the stage is marked not planned."
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
                    hint="No performance engine exists yet (slice 3b); the stage is marked not planned."
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
                <div className="space-y-5">
                  <Textarea
                    id="job-requirements"
                    label="Requirements"
                    optional
                    rows={5}
                    value={requirementsText}
                    onChange={(e) => setRequirementsText(e.target.value)}
                    placeholder={
                      "One requirement per line, e.g.\nThe service must answer health checks"
                    }
                    hint={`${requirements.length} requirement${requirements.length === 1 ? "" : "s"}. The Requirements Analysis Agent turns each line into a traceable scenario (deterministic; no model is called unless a local provider is configured).`}
                  />

                  <fieldset>
                    <legend className="label">API checks</legend>
                    <p className="mb-2 text-xs text-muted">
                      Read-only HTTP checks the API Testing Agent runs against a local target. Only
                      GET, HEAD and OPTIONS to localhost or 127.0.0.1 are allowed; anything else is
                      recorded as blocked.
                    </p>
                    {checks.length === 0 ? (
                      <p className="mb-2 text-sm text-muted">No API checks yet.</p>
                    ) : (
                      <ol className="space-y-2" aria-label="API checks">
                        {checks.map((c, i) => {
                          const warn = checkWarning(c);
                          return (
                            <li
                              key={i}
                              className="grid grid-cols-1 gap-2 rounded-md border border-line bg-canvas p-2.5 md:grid-cols-[110px_1fr_110px_90px_auto]"
                            >
                              <Select
                                id={`check-method-${i}`}
                                label="Method"
                                value={c.method}
                                onChange={(e) =>
                                  updateCheck(i, { method: e.target.value as ApiCheckMethod })
                                }
                              >
                                {METHODS.map((m) => (
                                  <option key={m} value={m}>
                                    {m}
                                  </option>
                                ))}
                              </Select>
                              <Input
                                id={`check-url-${i}`}
                                label="URL"
                                className="font-mono"
                                value={c.url}
                                onChange={(e) => updateCheck(i, { url: e.target.value })}
                                required
                                maxLength={2048}
                                error={warn}
                              />
                              <Input
                                id={`check-status-${i}`}
                                label="Expect"
                                type="number"
                                min={100}
                                max={599}
                                value={c.expected_status}
                                onChange={(e) =>
                                  updateCheck(i, {
                                    expected_status: Number(e.target.value) || 200,
                                  })
                                }
                              />
                              <Select
                                id={`check-priority-${i}`}
                                label="Priority"
                                value={c.priority}
                                onChange={(e) =>
                                  updateCheck(i, {
                                    priority: e.target.value as ApiCheck["priority"],
                                  })
                                }
                              >
                                <option value="P0">P0</option>
                                <option value="P1">P1</option>
                                <option value="P2">P2</option>
                              </Select>
                              <div className="flex items-end">
                                <Button
                                  variant="ghost"
                                  size="sm"
                                  onClick={() =>
                                    setChecks((prev) => prev.filter((_, j) => j !== i))
                                  }
                                  aria-label={`Remove check ${i + 1}`}
                                >
                                  <Trash2 className="h-4 w-4" aria-hidden="true" />
                                </Button>
                              </div>
                            </li>
                          );
                        })}
                      </ol>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2">
                      <Button
                        size="sm"
                        onClick={() =>
                          setChecks((prev) => [
                            ...prev,
                            { method: "GET", url: "", expected_status: 200, priority: "P1" },
                          ])
                        }
                      >
                        <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Add check
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => setChecks((prev) => [...prev, { ...QUICK_CHECK }])}
                      >
                        Quick add: GET http://localhost:8000/healthz expect 200
                      </Button>
                    </div>
                  </fieldset>

                  <label className="flex items-start gap-2 text-sm text-text">
                    <input
                      type="checkbox"
                      checked={requireApproval}
                      onChange={(e) => setRequireApproval(e.target.checked)}
                      className="mt-0.5 h-4 w-4 rounded border-line-strong bg-canvas accent-[rgb(var(--c-accent))]"
                    />
                    <span>
                      Require plan approval before any agent runs (HA-05)
                      <span className="block text-xs text-muted">
                        The job waits in awaiting approval until a QA Lead approves or rejects the
                        plan. Nothing is enqueued before that decision.
                      </span>
                    </span>
                  </label>
                </div>
              ) : null}

              {step === 3 ? (
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
                      { label: "Requirements", value: requirements.length },
                      {
                        label: "API checks",
                        value: blockedChecks
                          ? `${checks.length} (${blockedChecks} will be blocked by policy)`
                          : checks.length,
                      },
                      {
                        label: "Plan approval",
                        value: requireApproval ? "Required (HA-05)" : "Not required",
                      },
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
                      {hasInputs ? (
                        <>
                          <li>
                            The job is created in validating and queued for the scheduler: Intake &
                            Pinning resolves the ref to a commit (git ls-remote), then the combined
                            plan is built. Nothing runs before that.
                          </li>
                          <li>
                            Repository checks (snapshot integrity, Python syntax, secret scan,
                            pytest) are planned only when the ref is pinned and an Execution Service
                            is configured; the scheduler records a warning otherwise.
                          </li>
                          <li>
                            The orchestrator builds a deterministic plan: Requirements Analysis
                            (AG-02)
                            {profiles.functional !== "none" ? ", Functional Testing (AG-03)" : ""}
                            {checks.length ? ", API Testing (AG-04)" : ""}, Evidence Analysis
                            (AG-08) and QA Reporting (AG-11).
                          </li>
                          <li>
                            {requireApproval
                              ? "The job waits for a QA Lead to approve the plan (HA-05) before any task is enqueued."
                              : "Tasks are enqueued once the plan is built; the agent runner and the exec host execute them in dependency order."}
                          </li>
                          <li>
                            API checks are read-only requests to localhost. Functional scenarios
                            from requirements are recorded as skipped (no scenario engine); the
                            repository&apos;s own pytest suite runs only where the exec host allows
                            code execution.
                          </li>
                          <li>
                            Outputs, executions, evidence, findings and the report are persisted and
                            shown on the job page.
                          </li>
                        </>
                      ) : (
                        <li>
                          No inputs were supplied. The job is queued for Intake &amp; Pinning; if
                          the ref is pinned and an Execution Service is configured, only the
                          repository checks plus the evidence and report agents run. If the
                          repository cannot be pinned the job fails at intake instead of pretending.
                        </li>
                      )}
                      <li>
                        The control plane never fetches, builds or runs repository code; only an
                        Execution Service host does, and pytest only where it explicitly allows code
                        execution.
                      </li>
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
                {step < STEPS.length - 1 ? (
                  <Button
                    variant="primary"
                    onClick={() => setStep((s) => s + 1)}
                    disabled={!sourceValid || (step === 2 && !checksValid)}
                  >
                    Continue <ArrowRight className="h-4 w-4" aria-hidden="true" />
                  </Button>
                ) : (
                  <Button
                    type="submit"
                    variant="primary"
                    loading={create.isPending}
                    disabled={!sourceValid || !checksValid}
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
              <ul className="mt-1.5 list-disc space-y-1 pl-4 text-muted">
                <li>Deny by default: only GET, HEAD and OPTIONS to localhost or 127.0.0.1.</li>
                <li>Cloud metadata addresses and credentials in URLs are refused.</li>
                <li>Plan approval (HA-05) is the only human gate in this build.</li>
              </ul>
            </div>
            <div className="card p-4 text-sm text-muted">
              <h2 className="font-semibold text-text">Local by default</h2>
              <p className="mt-1.5">
                The request goes to the local API only. Agents use deterministic adapters; a local
                model is used only when a provider is configured, and the job record says which.
              </p>
            </div>
          </aside>
        </form>
      )}
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
