import { FolderGit2, Pencil, Plus, Trash2 } from "lucide-react";
import { useState, type FormEvent } from "react";
import {
  useCreateProject,
  useCreateRepository,
  useDeleteProject,
  useProjects,
  useRepositories,
  useUpdateProject,
} from "../api/hooks";
import type { Project, Repository, RepositoryProvider } from "../api/types";
import {
  DataTable,
  Dialog,
  EmptyState,
  LoadingState,
  PageHeader,
  ProblemAlert,
  StatusBadge,
  toProblem,
} from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime } from "../lib/format";
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
  const [name, setName] = useState(project?.name ?? "");
  const [description, setDescription] = useState(project?.description ?? "");
  const pending = create.isPending || update.isPending;
  const error = create.error ?? update.error;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const body = { name: name.trim(), description: description.trim() || null };
    if (project) await update.mutateAsync({ id: project.id, body }).then(onClose, () => undefined);
    else await create.mutateAsync(body).then(onClose, () => undefined);
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={project ? "Edit project" : "New project"}
      description={project ? `PATCH /api/v1/projects/${project.id}` : "POST /api/v1/projects"}
    >
      <form onSubmit={submit} className="space-y-4">
        {error ? <ProblemAlert error={error} /> : null}
        <div>
          <label htmlFor="project-name" className="label">
            Name
          </label>
          <input
            id="project-name"
            className="input"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            minLength={1}
            maxLength={120}
          />
        </div>
        <div>
          <label htmlFor="project-description" className="label">
            Description <span className="text-slate-400">(optional)</span>
          </label>
          <textarea
            id="project-description"
            className="input"
            rows={3}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={1000}
          />
        </div>
        <div className="flex justify-end gap-2">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Cancel
          </button>
          <button type="submit" className="btn-primary" disabled={pending || !name.trim()}>
            {project ? "Save" : "Create project"}
          </button>
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
      /* shown via ProblemAlert */
    }
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Add repository"
      description="POST /api/v1/repositories · syntactic checks now; SSRF/DNS checks and commit pinning run with the first job. Nothing is cloned on the control plane."
    >
      <form onSubmit={submit} className="space-y-4" noValidate>
        {create.error ? <ProblemAlert error={create.error} /> : null}
        <div>
          <label htmlFor="repo-project" className="label">
            Project
          </label>
          <select
            id="repo-project"
            className="input"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            required
          >
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
        </div>
        <fieldset>
          <legend className="label">Provider</legend>
          <div className="flex gap-2">
            {(["github", "gitlab", "other"] as RepositoryProvider[]).map((p) => (
              <label
                key={p}
                className={`cursor-pointer rounded-lg border px-3 py-1.5 text-sm ${
                  provider === p
                    ? "border-primary bg-primary-light text-primary"
                    : "border-slate-300"
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
        <div>
          <label htmlFor="repo-url" className="label">
            Repository URL
          </label>
          <input
            id="repo-url"
            className={`input ${urlError ? "border-red-400" : ""}`}
            placeholder="https://github.com/owner/repo"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            aria-invalid={Boolean(urlError)}
            aria-describedby={urlError ? "repo-url-error" : "repo-url-help"}
            required
          />
          {urlError ? (
            <p id="repo-url-error" className="mt-1 text-sm text-red-700">
              {urlError}
            </p>
          ) : (
            <p id="repo-url-help" className="mt-1 text-xs text-slate-500">
              Only HTTPS URLs on allow-listed hosts; no credentials in the URL.
            </p>
          )}
        </div>
        <div>
          <label htmlFor="repo-branch" className="label">
            Default branch{" "}
            <span className="text-slate-400">(optional, pinned by the first job)</span>
          </label>
          <input
            id="repo-branch"
            className="input"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
            placeholder="main"
          />
        </div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-slate-500">Nothing is cloned until validation passes.</span>
          <div className="flex gap-2">
            <button type="button" className="btn-secondary" onClick={onClose}>
              Cancel
            </button>
            <button
              type="submit"
              className="btn-primary"
              disabled={create.isPending || !url.trim() || !projectId}
            >
              Validate &amp; add
            </button>
          </div>
        </div>
      </form>
    </Dialog>
  );
}

export function RepositoriesScreen() {
  const projects = useProjects();
  const [selected, setSelected] = useState<string | undefined>(undefined);
  const repos = useRepositories(selected);
  const deleteProject = useDeleteProject();
  const [projectDialog, setProjectDialog] = useState<{ open: boolean; project?: Project | null }>({
    open: false,
  });
  const [repoDialog, setRepoDialog] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState<Project | null>(null);
  const [justAdded, setJustAdded] = useState<Repository | null>(null);

  const items = projects.data?.items ?? [];
  const sample = items.some((p) => p.org_name?.includes("(sample org)"));
  const orgName = items[0]?.org_name;

  return (
    <div>
      <PageHeader
        crumbs={[{ label: orgName ?? "Organisation" }, { label: "Repositories & Projects" }]}
        title="Repositories & Projects"
        subtitle="Register repositories by HTTPS URL. Syntactic validation runs now; the first job pins the ref to a commit after SSRF-safe DNS checks. Credentials are references only."
        actions={
          <>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setProjectDialog({ open: true, project: null })}
            >
              <Plus className="h-4 w-4" aria-hidden="true" /> New project
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={() => setRepoDialog(true)}
              disabled={items.length === 0}
              title={items.length === 0 ? "Create a project first" : undefined}
            >
              <Plus className="h-4 w-4" aria-hidden="true" /> Add repository
            </button>
          </>
        }
      />

      <section className="card mb-6">
        <div className="border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">
            Projects{" "}
            <span className="font-normal text-slate-500">
              {projects.data ? `${items.length} in ${orgName ?? "organisation"}` : ""}
            </span>
          </h2>
        </div>
        {projects.isLoading ? <LoadingState rows={2} label="Loading projects" /> : null}
        {projects.isError ? (
          <div className="p-4">
            <ProblemAlert error={projects.error} />
          </div>
        ) : null}
        {deleteProject.isError ? (
          <div className="p-4">
            <ProblemAlert error={deleteProject.error} />
          </div>
        ) : null}
        {projects.data && items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              title="No projects yet"
              description="Create a project to group repositories, defaults and gate thresholds."
              action={
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => setProjectDialog({ open: true, project: null })}
                >
                  New project
                </button>
              }
            />
          </div>
        ) : null}
        {items.length > 0 ? (
          <ul className="grid grid-cols-1 gap-3 p-4 md:grid-cols-2">
            <li>
              <button
                type="button"
                onClick={() => setSelected(undefined)}
                className={`w-full rounded-xl border p-3 text-left text-sm ${
                  selected === undefined ? "border-primary bg-primary-light" : "border-slate-200"
                }`}
              >
                <span className="font-medium">All projects</span>
                <span className="ml-2 text-slate-500">show every repository</span>
              </button>
            </li>
            {items.map((p) => (
              <li
                key={p.id}
                className={`rounded-xl border p-3 ${
                  selected === p.id ? "border-primary bg-primary-light" : "border-slate-200"
                }`}
              >
                <div className="flex items-start justify-between gap-2">
                  <button
                    type="button"
                    onClick={() => setSelected(p.id)}
                    className="min-w-0 flex-1 text-left"
                    aria-pressed={selected === p.id}
                  >
                    <div className="truncate text-sm font-semibold text-slate-900">{p.name}</div>
                    <div className="mt-0.5 text-xs text-slate-500">
                      {p.repository_count ?? 0} repositories · created {formatTime(p.created_at)}
                    </div>
                    {p.description ? (
                      <div className="mt-1 line-clamp-2 text-xs text-slate-600">
                        {p.description}
                      </div>
                    ) : null}
                  </button>
                  <div className="flex shrink-0 gap-1">
                    <button
                      type="button"
                      className="rounded-md p-1.5 text-slate-500 hover:bg-white"
                      aria-label={`Edit project ${p.name}`}
                      onClick={() => setProjectDialog({ open: true, project: p })}
                    >
                      <Pencil className="h-4 w-4" aria-hidden="true" />
                    </button>
                    <button
                      type="button"
                      className="rounded-md p-1.5 text-red-600 hover:bg-white"
                      aria-label={`Delete project ${p.name}`}
                      onClick={() => setConfirmDelete(p)}
                    >
                      <Trash2 className="h-4 w-4" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </section>

      {justAdded ? (
        <div className="mb-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
          Registered <span className="font-mono">{justAdded.url}</span> ·{" "}
          <StatusBadge state={justAdded.validation_status} />{" "}
          {justAdded.validation_note ? (
            <span className="ml-2">{justAdded.validation_note}</span>
          ) : null}
        </div>
      ) : null}

      <section className="card">
        <div className="border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">
            Repositories{" "}
            <span className="font-normal text-slate-500">
              {selected ? items.find((p) => p.id === selected)?.name : "all projects"}
              {repos.data ? ` · ${repos.data.items.length}` : ""}
            </span>
          </h2>
        </div>
        {repos.isLoading ? <LoadingState label="Loading repositories" /> : null}
        {repos.isError ? (
          <div className="p-4">
            <ProblemAlert error={repos.error} />
          </div>
        ) : null}
        {repos.data && repos.data.items.length === 0 ? (
          <div className="p-4">
            <EmptyState
              icon={FolderGit2}
              title="No repositories registered"
              description="Add a repository by HTTPS URL. Only syntactic validation runs in this slice."
              action={
                <button
                  type="button"
                  className="btn-primary"
                  onClick={() => setRepoDialog(true)}
                  disabled={items.length === 0}
                >
                  Add repository
                </button>
              }
            />
          </div>
        ) : null}
        {repos.data && repos.data.items.length > 0 ? (
          <DataTable<Repository>
            caption="Repositories"
            rows={repos.data.items}
            rowKey={(r) => r.id}
            columns={[
              {
                key: "repo",
                header: "Repository",
                render: (r) => (
                  <div>
                    <div className="font-medium text-slate-900">
                      {r.url.replace(/^https:\/\//, "")}
                    </div>
                    <div className="text-xs text-slate-500">
                      {items.find((p) => p.id === r.project_id)?.name ?? r.project_id} ·{" "}
                      {r.provider}
                    </div>
                  </div>
                ),
              },
              {
                key: "branch",
                header: "Branch · SHA",
                render: (r) => (
                  <span className="font-mono text-xs">
                    {r.default_branch ?? "—"} · {r.last_pinned_sha ?? "not pinned"}
                  </span>
                ),
              },
              {
                key: "lang",
                header: "Language support",
                render: (r) => r.language_support ?? "unknown",
              },
              {
                key: "validation",
                header: "Validation",
                render: (r) => (
                  <div>
                    <StatusBadge state={r.validation_status} />
                    {r.validation_note ? (
                      <div className="mt-1 max-w-xs text-xs text-slate-500">
                        {r.validation_note}
                      </div>
                    ) : null}
                  </div>
                ),
              },
              { key: "created", header: "Registered", render: (r) => formatTime(r.created_at) },
            ]}
          />
        ) : null}
      </section>

      {sample ? (
        <p className="mt-3 text-xs text-amber-800">Sample data — no repository code executed</p>
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
          onCreated={setJustAdded}
        />
      ) : null}
      <Dialog
        open={Boolean(confirmDelete)}
        onClose={() => setConfirmDelete(null)}
        title="Delete project?"
        description="The project is archived (soft delete) and hidden from lists; historical jobs keep their references."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setConfirmDelete(null)}>
              Cancel
            </button>
            <button
              type="button"
              className="btn-danger"
              disabled={deleteProject.isPending}
              onClick={() => {
                if (!confirmDelete) return;
                deleteProject.mutate(confirmDelete.id, {
                  onSettled: () => {
                    if (selected === confirmDelete.id) setSelected(undefined);
                    setConfirmDelete(null);
                  },
                });
              }}
            >
              Delete {confirmDelete?.name}
            </button>
          </>
        }
      >
        <p className="text-sm text-slate-700">
          This removes <strong>{confirmDelete?.name}</strong> from the project list.
        </p>
      </Dialog>
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
