import { FolderGit2, Pencil, Play, Plus, Search, Trash2 } from "lucide-react";
import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import {
  useCreateProject,
  useCreateRepository,
  useDeleteProject,
  useProjects,
  useRepositories,
  useUpdateProject,
} from "../api/hooks";
import { problemSummary } from "../api/problem";
import type { Project, Repository, RepositoryProvider } from "../api/types";
import { useProjectContext } from "../app/ProjectContext";
import {
  Button,
  DataTable,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  PageHeader,
  ProblemAlert,
  Select,
  SkeletonRows,
  StatusBadge,
  Textarea,
  toProblem,
  useToast,
} from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime, repoShortName } from "../lib/format";
import { screenById } from "./registry";

const screen = screenById("SCR-02");

function ProjectDialog({
  open,
  onClose,
  project,
}: {
  open: boolean;
  onClose: () => void;
  project?: Project | null;
}) {
  const create = useCreateProject();
  const update = useUpdateProject();
  const { toast } = useToast();
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  const pending = create.isPending || update.isPending;
  const error = create.error ?? update.error;
  const nameError = error
    ? toProblem(error).errors?.find((e) => e.pointer === "/name")?.message
    : undefined;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = { name: name.trim(), description: description.trim() || null };
    try {
      if (project) {
        await update.mutateAsync({ id: project.id, body });
        toast({ kind: "success", title: "Project saved", description: body.name });
      } else {
        await create.mutateAsync(body);
        toast({ kind: "success", title: "Project created", description: body.name });
      }
      onClose();
    } catch (err) {
      toast({
        kind: "error",
        title: project ? "Project not saved" : "Project not created",
        description: problemSummary(err),
      });
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={project ? "Edit project" : "New project"}
      description="Projects group repositories and, later, gate thresholds and default profiles."
    >
      <form onSubmit={submit} className="space-y-4">
        {error && !nameError ? <ProblemAlert error={error} /> : null}
        <Input
          id="project-name"
          label="Name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
          minLength={1}
          maxLength={200}
          error={nameError}
          autoComplete="off"
        />
        <Textarea
          id="project-description"
          label="Description"
          optional
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          maxLength={2000}
        />
        <div className="flex justify-end gap-2">
          <Button onClick={onClose}>Cancel</Button>
          <Button type="submit" variant="primary" loading={pending} disabled={!name.trim()}>
            {project ? "Save changes" : "Create project"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

export function AddRepositoryDialog({
  open,
  onClose,
  projects,
  defaultProjectId,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  projects: Project[];
  defaultProjectId?: string;
  onCreated?: (r: Repository) => void;
}) {
  const create = useCreateRepository();
  const [projectId, setProjectId] = useState(defaultProjectId ?? projects[0]?.id ?? "");
  const [provider, setProvider] = useState<RepositoryProvider>("github");
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("");
  const problem = create.error ? toProblem(create.error) : null;
  const urlError = problem?.errors?.find((e) => e.pointer === "/url")?.message;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    try {
      const r = await create.mutateAsync({
        project_id: projectId,
        provider,
        url: url.trim(),
        default_branch: branch.trim() || null,
      });
      onCreated?.(r);
      onClose();
    } catch {
      /* shown inline */
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add repository"
      description="Only the URL shape is checked in this slice: https, allow-listed host, owner/repo, no credentials. DNS and reachability checks arrive in slice 1b. Nothing is cloned."
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        {create.error ? <ProblemAlert error={create.error} /> : null}
        <Select
          id="repo-project"
          label="Project"
          value={projectId}
          onChange={(e) => setProjectId(e.target.value)}
          required
        >
          {projects.map((p) => (
            <option key={p.id} value={p.id}>
              {p.name}
            </option>
          ))}
        </Select>
        <fieldset>
          <legend className="label">Provider</legend>
          <div className="flex flex-wrap gap-2">
            {(["github", "gitlab", "other"] as RepositoryProvider[]).map((p) => (
              <label
                key={p}
                className={`cursor-pointer rounded-md border px-2.5 py-1 text-sm rao-transition ${
                  provider === p
                    ? "border-accent bg-accent/15 text-text"
                    : "border-line text-muted hover:border-line-strong"
                }`}
              >
                <input
                  type="radio"
                  name="provider"
                  value={p}
                  checked={provider === p}
                  onChange={() => setProvider(p)}
                  className="sr-only"
                />
                {p === "github" ? "GitHub" : p === "gitlab" ? "GitLab" : "Other (allow-listed)"}
              </label>
            ))}
          </div>
        </fieldset>
        <Input
          id="repo-url"
          label="Repository URL"
          className="font-mono"
          placeholder="https://github.com/owner/repo"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          error={urlError}
          hint="HTTPS only, on an allow-listed host, without credentials in the URL."
          required
          autoComplete="off"
        />
        <Input
          id="repo-branch"
          label="Default branch"
          optional
          className="font-mono"
          value={branch}
          onChange={(e) => setBranch(e.target.value)}
          placeholder="main"
          hint="Resolved from the provider in slice 1b if left empty."
        />
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted">Nothing is cloned until validation passes.</span>
          <div className="flex gap-2">
            <Button onClick={onClose}>Cancel</Button>
            <Button
              type="submit"
              variant="primary"
              loading={create.isPending}
              disabled={!url.trim() || !projectId}
            >
              Validate &amp; add
            </Button>
          </div>
        </div>
      </form>
    </Dialog>
  );
}

type StatusFilter = "all" | Repository["validation_status"];

export function RepositoriesScreen() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const projects = useProjects();
  const { projectId: selected, setProjectId: setSelected } = useProjectContext();
  const repos = useRepositories(selected);
  const deleteProject = useDeleteProject();
  const { toast } = useToast();
  const [projectDialog, setProjectDialog] = useState<{ open: boolean; project?: Project | null }>({
    open: false,
  });
  const [repoDialog, setRepoDialog] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Project | null>(null);
  const [justAdded, setJustAdded] = useState<Repository | null>(null);
  const [projectQuery, setProjectQuery] = useState("");
  const [repoQuery, setRepoQuery] = useState("");
  const [providerFilter, setProviderFilter] = useState<"all" | RepositoryProvider>("all");
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");

  const items = useMemo(() => projects.data?.items ?? [], [projects.data]);
  const sample = items.some((p) => p.org_name?.includes("(sample org)"));
  const orgName = items[0]?.org_name;

  // Deep links from the command palette and the first-run guide: ?new=project | ?new=repository
  useEffect(() => {
    const open = params.get("new");
    if (!open) return;
    if (open === "project") setProjectDialog({ open: true, project: null });
    if (open === "repository" && items.length > 0) setRepoDialog(true);
    if (open !== "repository" || items.length > 0) {
      params.delete("new");
      setParams(params, { replace: true });
    }
  }, [params, setParams, items.length]);

  const visibleProjects = items.filter((p) =>
    p.name.toLowerCase().includes(projectQuery.trim().toLowerCase()),
  );
  const visibleRepos = (repos.data?.items ?? []).filter((r) => {
    const q = repoQuery.trim().toLowerCase();
    return (
      (!q || r.url.toLowerCase().includes(q)) &&
      (providerFilter === "all" || r.provider === providerFilter) &&
      (statusFilter === "all" || r.validation_status === statusFilter)
    );
  });

  return (
    <div>
      <PageHeader
        crumbs={[{ label: orgName ?? "Organisation" }, { label: "Repositories & Projects" }]}
        title="Repositories & Projects"
        subtitle="Register repositories by HTTPS URL. This slice checks only the URL shape; SSRF-safe validation and commit pinning arrive in slice 1b. Credentials are references only."
        actions={
          <>
            <Button onClick={() => setProjectDialog({ open: true, project: null })}>
              <Plus className="h-4 w-4" aria-hidden="true" /> New project
            </Button>
            <Button
              variant="primary"
              onClick={() => setRepoDialog(true)}
              disabled={items.length === 0}
              title={items.length === 0 ? "Create a project first" : undefined}
            >
              <Plus className="h-4 w-4" aria-hidden="true" /> Add repository
            </Button>
          </>
        }
      />

      <section className="card mb-5" aria-labelledby="projects-heading">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line px-3.5 py-2.5">
          <h2 id="projects-heading" className="text-sm font-semibold text-text">
            Projects
            {projects.data ? (
              <span className="ml-2 text-xs font-normal text-muted">
                {items.length} in {orgName ?? "this organisation"}
              </span>
            ) : null}
          </h2>
          {items.length > 3 ? (
            <label className="relative">
              <span className="sr-only">Filter projects</span>
              <Search
                className="pointer-events-none absolute left-2 top-1.5 h-3.5 w-3.5 text-muted"
                aria-hidden="true"
              />
              <input
                type="search"
                className="input h-7 w-56 pl-7"
                placeholder="Filter projects"
                value={projectQuery}
                onChange={(e) => setProjectQuery(e.target.value)}
              />
            </label>
          ) : null}
        </div>
        {projects.isLoading ? <SkeletonRows rows={2} label="Loading projects" /> : null}
        {projects.isError ? (
          <ErrorState error={projects.error} onRetry={() => projects.refetch()} />
        ) : null}
        {projects.data && items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No projects yet"
              description="Create a project to group repositories, defaults and gate thresholds."
              action={
                <Button
                  variant="primary"
                  onClick={() => setProjectDialog({ open: true, project: null })}
                >
                  Create project
                </Button>
              }
            />
          </div>
        ) : null}
        {items.length > 0 ? (
          <ul className="grid grid-cols-1 gap-2 p-3 md:grid-cols-2 xl:grid-cols-3">
            <li>
              <button
                type="button"
                onClick={() => setSelected(undefined)}
                aria-pressed={selected === undefined}
                className={`h-full w-full rounded-md border p-3 text-left text-sm rao-transition ${
                  selected === undefined
                    ? "border-accent bg-accent/10"
                    : "border-line hover:border-line-strong"
                }`}
              >
                <span className="font-medium text-text">All projects</span>
                <span className="mt-0.5 block text-xs text-muted">Show every repository</span>
              </button>
            </li>
            {visibleProjects.map((p) => (
              <li
                key={p.id}
                className={`rounded-md border p-3 rao-transition ${
                  selected === p.id ? "border-accent bg-accent/10" : "border-line"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => setSelected(p.id)}
                    className="min-w-0 flex-1 text-left"
                    aria-pressed={selected === p.id}
                  >
                    <div className="truncate text-sm font-medium text-text">{p.name}</div>
                    <div className="mt-0.5 text-xs text-muted">
                      {p.repository_count ?? 0}{" "}
                      {(p.repository_count ?? 0) === 1 ? "repository" : "repositories"}, created{" "}
                      {formatTime(p.created_at)}
                    </div>
                    {p.description ? (
                      <div className="mt-1 line-clamp-2 text-xs text-muted">{p.description}</div>
                    ) : null}
                  </button>
                  <div className="flex shrink-0 gap-0.5">
                    <Button
                      size="sm"
                      variant="ghost"
                      aria-label={`Edit project ${p.name}`}
                      onClick={() => setProjectDialog({ open: true, project: p })}
                    >
                      <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="hover:text-danger"
                      aria-label={`Delete project ${p.name}`}
                      onClick={() => setConfirmDelete(p)}
                    >
                      <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
                    </Button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      {justAdded ? (
        <div
          role="status"
          className="mb-4 flex flex-wrap items-center gap-2 rounded-md border border-warn/40 bg-warn/10 px-3 py-2 text-sm text-text"
        >
          <span>
            Registered <span className="mono">{repoShortName(justAdded.url)}</span>
          </span>
          <StatusBadge state={justAdded.validation_status} />
          {justAdded.validation_note ? (
            <span className="text-xs text-muted">{justAdded.validation_note}</span>
          ) : null}
        </div>
      ) : null}

      <section className="card" aria-labelledby="repos-heading">
        <div className="flex flex-wrap items-center gap-2 border-b border-line px-3.5 py-2.5">
          <h2 id="repos-heading" className="text-sm font-semibold text-text">
            Repositories
            <span className="ml-2 text-xs font-normal text-muted">
              {selected ? items.find((p) => p.id === selected)?.name : "all projects"}
              {repos.data ? `, ${visibleRepos.length} shown` : ""}
            </span>
          </h2>
          <div className="ml-auto flex flex-wrap items-center gap-2">
            <label className="relative">
              <span className="sr-only">Search repositories</span>
              <Search
                className="pointer-events-none absolute left-2 top-1.5 h-3.5 w-3.5 text-muted"
                aria-hidden="true"
              />
              <input
                type="search"
                className="input h-7 w-52 pl-7"
                placeholder="Search by URL"
                value={repoQuery}
                onChange={(e) => setRepoQuery(e.target.value)}
              />
            </label>
            <select
              aria-label="Provider"
              className="input h-7 w-auto py-0"
              value={providerFilter}
              onChange={(e) => setProviderFilter(e.target.value as typeof providerFilter)}
            >
              <option value="all">All providers</option>
              <option value="github">GitHub</option>
              <option value="gitlab">GitLab</option>
              <option value="other">Other</option>
            </select>
            <select
              aria-label="Validation status"
              className="input h-7 w-auto py-0"
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as StatusFilter)}
            >
              <option value="all">Any status</option>
              <option value="pending_validation">Pending validation</option>
              <option value="validating">Validating</option>
              <option value="valid">Valid</option>
              <option value="validation_failed">Validation failed</option>
            </select>
          </div>
        </div>
        {repos.isLoading ? <SkeletonRows label="Loading repositories" /> : null}
        {repos.isError ? <ErrorState error={repos.error} onRetry={() => repos.refetch()} /> : null}
        {repos.data && repos.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={FolderGit2}
              title="No repositories registered"
              description="Add a repository by HTTPS URL. Only the URL shape is checked in this slice."
              action={
                <Button
                  variant="primary"
                  onClick={() => setRepoDialog(true)}
                  disabled={items.length === 0}
                >
                  Add repository
                </Button>
              }
            />
          </div>
        ) : null}
        {repos.data && repos.data.items.length > 0 ? (
          <DataTable<Repository>
            caption="Repositories"
            rows={visibleRepos}
            rowKey={(r) => r.id}
            emptyLabel="No repositories match these filters."
            defaultSort={{ key: "created", dir: "desc" }}
            columns={[
              {
                key: "repo",
                header: "Repository",
                sortValue: (r) => r.url,
                render: (r) => (
                  <div>
                    <div className="mono font-medium text-text">{repoShortName(r.url)}</div>
                    <div className="text-2xs text-muted">
                      {items.find((p) => p.id === r.project_id)?.name ?? r.project_id}
                    </div>
                  </div>
                ),
              },
              {
                key: "provider",
                header: "Provider",
                sortValue: (r) => r.provider,
                render: (r) => r.provider,
              },
              {
                key: "branch",
                header: "Branch",
                render: (r) => (
                  <span className="mono">
                    {r.default_branch ?? "—"}
                    {r.last_pinned_sha ? ` ${r.last_pinned_sha.slice(0, 10)}` : ""}
                  </span>
                ),
              },
              {
                key: "validation",
                header: "Validation",
                sortValue: (r) => r.validation_status,
                render: (r) => <StatusBadge state={r.validation_status} />,
              },
              {
                key: "created",
                header: "Registered",
                sortValue: (r) => r.created_at,
                render: (r) => <span className="tabular-nums">{formatTime(r.created_at)}</span>,
              },
              {
                key: "actions",
                header: "",
                align: "right",
                render: (r) => (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => navigate(`/jobs/new?repository=${encodeURIComponent(r.id)}`)}
                    aria-label={`New job from ${repoShortName(r.url)}`}
                  >
                    <Play className="h-3.5 w-3.5" aria-hidden="true" /> New job
                  </Button>
                ),
              },
            ]}
            renderExpanded={(r) => (
              <dl className="grid gap-2 text-xs sm:grid-cols-2">
                <div>
                  <dt className="text-muted">Full URL</dt>
                  <dd className="mono break-all text-text">{r.url}</dd>
                </div>
                <div>
                  <dt className="text-muted">Language support</dt>
                  <dd className="text-text">{r.language_support ?? "unknown"} (detected in 1b)</dd>
                </div>
                <div className="sm:col-span-2">
                  <dt className="text-muted">Validation note</dt>
                  <dd className="text-text">{r.validation_note ?? "—"}</dd>
                </div>
              </dl>
            )}
          />
        ) : null}
      </section>

      {sample ? (
        <p className="mt-3 text-xs text-warn">Sample data — no repository code executed</p>
      ) : null}

      {projectDialog.open ? (
        <ProjectDialog
          key={projectDialog.project?.id ?? "new"}
          open
          project={projectDialog.project}
          onClose={() => setProjectDialog({ open: false })}
        />
      ) : null}
      {repoDialog ? (
        <AddRepositoryDialog
          open
          onClose={() => setRepoDialog(false)}
          projects={items}
          defaultProjectId={selected}
          onCreated={(r) => {
            setJustAdded(r);
            toast({
              kind: "success",
              title: "Repository registered",
              description: `${repoShortName(r.url)} is pending validation.`,
            });
          }}
        />
      ) : null}
      <Dialog
        open={Boolean(confirmDelete)}
        onClose={() => setConfirmDelete(null)}
        title="Delete project?"
        description="The project is archived and hidden from lists. Historical jobs keep their references."
        footer={
          <>
            <Button onClick={() => setConfirmDelete(null)}>Cancel</Button>
            <Button
              variant="danger"
              loading={deleteProject.isPending}
              onClick={() => {
                if (!confirmDelete) return;
                const target = confirmDelete;
                deleteProject.mutate(target.id, {
                  onSuccess: () => {
                    if (selected === target.id) setSelected(undefined);
                    toast({ kind: "success", title: "Project deleted", description: target.name });
                  },
                  onError: (err) =>
                    toast({
                      kind: "error",
                      title: "Project not deleted",
                      description: problemSummary(err),
                    }),
                  onSettled: () => setConfirmDelete(null),
                });
              }}
            >
              Delete project
            </Button>
          </>
        }
      >
        <p className="text-sm text-text">
          This removes <strong>{confirmDelete?.name}</strong> and its repositories from the lists.
        </p>
      </Dialog>
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
