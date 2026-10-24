import { Ban, ExternalLink, GitCompare, Radio } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { reportHtmlUrl } from "../api/client.phase2";
import { useCancelJob, useJob, useJobEvents, useJobs } from "../api/hooks";
import { useJobChecks, useJobEvidence, useJobTasks } from "../api/hooks.phase2";
import { TERMINAL_JOB_STATES } from "../api/types";
import type { EvidenceItem, StageProgress, Task } from "../api/types.phase2";
import {
  ChecksTable,
  DataTable,
  Dialog,
  EvidenceDrawer,
  LoadingState,
  PageHeader,
  ProblemAlert,
  StatusBadge,
} from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { formatDuration } from "../lib/compare";
import { formatTime, profilesSummary } from "../lib/format";
import { screenById } from "./registry";

const screen = screenById("SCR-04");

export const STAGES = [
  "Intake & Pinning",
  "Planning",
  "Environment Preparation",
  "Baseline Run",
  "Functional & API Testing",
  "Security Testing",
  "Performance Testing",
  "Mutation Testing",
  "Evidence Correlation & Triage",
  "Patch Proposal",
  "Independent Verification",
  "Quality Gates & Reporting",
  "Cleanup & Retention",
];

const STAGE_TONE: Record<string, string> = {
  succeeded: "border-emerald-200 bg-emerald-50",
  running: "border-sky-300 bg-sky-50",
  failed: "border-red-200 bg-red-50",
  held: "border-amber-300 bg-amber-50",
  cancelled: "border-slate-300 bg-slate-100",
  skipped: "border-slate-200 bg-slate-50",
  not_run: "border-slate-200 bg-white",
  pending: "border-slate-200 bg-white",
};

function Summary({ label, counts }: { label: string; counts: Record<string, number> }) {
  const entries = Object.entries(counts);
  return (
    <div className="card p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">{label}</div>
      {entries.length === 0 ? (
        <div className="mt-1 text-sm text-slate-500">none yet</div>
      ) : (
        <div className="mt-2 flex flex-wrap gap-2">
          {entries.map(([k, v]) => (
            <span key={k} className="inline-flex items-center gap-1.5 text-sm">
              <StatusBadge state={k} />
              <span className="font-semibold text-slate-900">{v}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}

export function JobDetailScreen() {
  const { jobId = "" } = useParams();
  const job = useJob(jobId);
  const state = job.data?.state;
  const repo = useQuery({
    queryKey: ["repositories", "detail", job.data?.repository_id],
    queryFn: () => api.getRepository(job.data!.repository_id),
    enabled: Boolean(job.data?.repository_id),
  });
  const tasks = useJobTasks(jobId, state);
  const checks = useJobChecks(jobId, state);
  const evidence = useJobEvidence(jobId);
  const siblings = useJobs({ repository_id: job.data?.repository_id, limit: 20 });
  const cancel = useCancelJob(jobId);
  const { events, status } = useJobEvents(jobId);
  const [confirm, setConfirm] = useState(false);
  const [reason, setReason] = useState("");
  const [openEvidence, setOpenEvidence] = useState<EvidenceItem | null>(null);

  if (job.isLoading) return <LoadingState rows={6} label="Loading job" />;
  if (job.isError || !job.data)
    return (
      <div>
        <PageHeader crumbs={[{ label: "Jobs", to: "/jobs" }]} title="Job" />
        <ProblemAlert error={job.error ?? new Error("Job not found")} />
      </div>
    );
  const j = job.data;
  const terminal = TERMINAL_JOB_STATES.includes(j.state);
  const held = Boolean(j.held_reason) && !terminal;
  const stages: StageProgress[] = (j.stages ?? []) as StageProgress[];
  const previous = (siblings.data?.items ?? []).filter((s) => s.id !== j.id);

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Jobs", to: "/jobs" }, { label: j.display_id }]}
        title={j.display_id}
        badge={<StatusBadge state={j.state} />}
        subtitle={
          <>
            <span className="font-mono">
              {repo.data ? repo.data.url.replace(/^https:\/\//, "") : j.repository_id}
            </span>{" "}
            · {j.ref} →{" "}
            <span className="font-mono">{j.commit_sha?.slice(0, 12) ?? "not pinned"}</span> ·{" "}
            {profilesSummary(j.profiles)} · created {formatTime(j.created_at)}
            {j.snapshot_sha256 ? (
              <>
                {" "}
                · snapshot <span className="font-mono">{j.snapshot_sha256.slice(0, 12)}</span>
              </>
            ) : null}
          </>
        }
        actions={
          <>
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${
                status === "live"
                  ? "border-sky-200 bg-sky-50 text-sky-700"
                  : "border-slate-200 bg-slate-50 text-slate-600"
              }`}
            >
              <Radio className="h-3.5 w-3.5" aria-hidden="true" />
              {status === "live"
                ? "SSE live"
                : status === "connecting"
                  ? "Connecting…"
                  : "Disconnected"}
            </span>
            {previous.length > 0 ? (
              <Link to={`/jobs/${j.id}/compare/${previous[0].id}`} className="btn-secondary">
                <GitCompare className="h-4 w-4" aria-hidden="true" /> Compare with{" "}
                {previous[0].display_id}
              </Link>
            ) : null}
            <a
              href={reportHtmlUrl(j.id)}
              target="_blank"
              rel="noreferrer"
              className="btn-secondary"
            >
              <ExternalLink className="h-4 w-4" aria-hidden="true" /> Report
            </a>
            <button
              type="button"
              className="btn-danger"
              disabled={terminal || cancel.isPending}
              onClick={() => setConfirm(true)}
              title={terminal ? "Job is in a terminal state" : undefined}
            >
              <Ban className="h-4 w-4" aria-hidden="true" /> Cancel job
            </button>
          </>
        }
      />

      {cancel.isError ? (
        <div className="mb-4">
          <ProblemAlert error={cancel.error} />
        </div>
      ) : null}
      {held ? (
        <div
          role="status"
          className="mb-4 rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          <strong>Held:</strong> {j.held_reason}. The scheduler picks the job up on its next tick.
        </div>
      ) : null}
      {j.warnings?.length ? (
        <div
          role="status"
          className="mb-4 rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          <strong>Warnings</strong>
          <ul className="mt-1 list-disc pl-5">
            {j.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <section className="card mb-6 p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-900">
          Pipeline stages{" "}
          <span className="font-normal text-slate-500">
            13 stages · derived from task and job state
          </span>
        </h2>
        <ol className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
          {STAGES.map((name, i) => {
            const st = stages[i];
            const statusKey = st?.status ?? "pending";
            return (
              <li
                key={name}
                className={`rounded-lg border p-2 text-xs ${STAGE_TONE[statusKey] ?? ""}`}
                data-stage-status={statusKey}
              >
                <div className="text-[11px] font-semibold text-slate-500">{i + 1}</div>
                <div className="font-medium text-slate-800">{name}</div>
                <div className="mt-1 flex items-center gap-1 text-slate-600">
                  <StatusBadge state={statusKey} />
                  {st?.tasks ? (
                    <span className="text-[11px] text-slate-500">{st.tasks} task(s)</span>
                  ) : null}
                </div>
                {st?.note ? <div className="mt-1 text-[11px] text-slate-500">{st.note}</div> : null}
              </li>
            );
          })}
        </ol>
      </section>

      <div className="mb-6 grid grid-cols-1 gap-4 md:grid-cols-3">
        <Summary label="Tasks" counts={j.task_summary ?? {}} />
        <Summary label="Checks" counts={j.check_summary ?? {}} />
        <Summary label="Tests" counts={j.test_summary ?? {}} />
      </div>

      <section className="card mb-6">
        <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">
            Check results{" "}
            <span className="font-normal text-slate-500">GET /jobs/{"{id}"}/checks</span>
          </h2>
          <Link
            to={`/results/functional?job=${j.id}`}
            className="text-sm text-primary hover:underline"
          >
            Functional test results
          </Link>
        </div>
        {checks.isLoading ? <LoadingState label="Loading checks" /> : null}
        {checks.isError ? (
          <div className="p-4">
            <ProblemAlert error={checks.error} />
          </div>
        ) : null}
        {checks.data && checks.data.length === 0 ? (
          <p className="p-4 text-sm text-slate-500">
            No check has reported yet. Results appear as the Execution Service completes tasks.
          </p>
        ) : null}
        {checks.data && checks.data.length > 0 ? (
          <ChecksTable
            checks={checks.data}
            evidence={evidence.data ?? []}
            onOpenEvidence={setOpenEvidence}
          />
        ) : null}
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">
              Tasks <span className="font-normal text-slate-500">GET /jobs/{"{id}"}/tasks</span>
            </h2>
            <span className="text-xs text-slate-500">{tasks.data?.length ?? 0} tasks</span>
          </div>
          {tasks.isLoading ? <LoadingState label="Loading tasks" /> : null}
          {tasks.data && tasks.data.length === 0 ? (
            <p className="p-4 text-sm text-slate-500">No tasks planned yet.</p>
          ) : null}
          {tasks.data && tasks.data.length > 0 ? (
            <DataTable<Task>
              caption="Tasks"
              rows={tasks.data}
              rowKey={(t) => t.id}
              columns={[
                {
                  key: "task",
                  header: "Task",
                  render: (t) => (
                    <div>
                      <div className="font-mono text-xs text-slate-900">
                        {t.task_type}
                        {t.engine ? `:${t.engine}` : ""}
                      </div>
                      <div className="text-xs text-slate-500">
                        {t.stage.replace(/_/g, " ")}
                        {t.agent_id ? ` · ${t.agent_id}` : ""}
                      </div>
                    </div>
                  ),
                },
                { key: "state", header: "State", render: (t) => <StatusBadge state={t.state} /> },
                {
                  key: "attempts",
                  header: "Attempts",
                  render: (t) => (
                    <span className="text-xs">
                      {t.attempt_count}
                      {t.attempts.length
                        ? ` · last ${t.attempts[t.attempts.length - 1].outcome}`
                        : ""}
                    </span>
                  ),
                },
                {
                  key: "error",
                  header: "Error",
                  render: (t) => (
                    <span className="font-mono text-xs text-red-700">
                      {t.last_error_code ?? "—"}
                    </span>
                  ),
                },
                {
                  key: "duration",
                  header: "Last attempt",
                  render: (t) => {
                    const a = t.attempts[t.attempts.length - 1];
                    if (!a?.started_at || !a.ended_at) return "—";
                    return formatDuration(
                      new Date(a.ended_at).getTime() - new Date(a.started_at).getTime(),
                    );
                  },
                },
              ]}
            />
          ) : null}
        </section>
        <aside className="card p-4 text-sm">
          <h2 className="mb-2 text-sm font-semibold text-slate-900">Live events</h2>
          <p className="mb-2 text-xs text-slate-500">{events.length} received on this connection</p>
          <ul className="max-h-80 space-y-1 overflow-auto font-mono text-[11px]">
            {events
              .slice(-40)
              .reverse()
              .map((e, i) => (
                <li key={`${e.id}-${i}`} className="truncate text-slate-600">
                  <span className="text-slate-400">{e.id} </span>
                  <span className="font-semibold text-slate-700">{e.type}</span>{" "}
                  {typeof e.data === "string" ? e.data : JSON.stringify(e.data)}
                </li>
              ))}
          </ul>
          {previous.length > 0 ? (
            <div className="mt-4 border-t border-slate-200 pt-3">
              <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-500">
                Previous runs of this repository
              </h3>
              <ul className="mt-1 space-y-1">
                {previous.slice(0, 6).map((p) => (
                  <li key={p.id} className="flex items-center justify-between gap-2 text-xs">
                    <Link to={`/jobs/${p.id}`} className="font-mono text-primary">
                      {p.display_id}
                    </Link>
                    <StatusBadge state={p.state} />
                    <Link
                      to={`/jobs/${j.id}/compare/${p.id}`}
                      className="text-primary hover:underline"
                    >
                      compare
                    </Link>
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </aside>
      </div>

      <Dialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={`Cancel ${j.display_id}?`}
        description="The job moves to cancelling; running workers are stopped and the job becomes cancelled once every worker run is reported destroyed."
        footer={
          <>
            <button type="button" className="btn-secondary" onClick={() => setConfirm(false)}>
              Keep running
            </button>
            <button
              type="button"
              className="btn-danger"
              disabled={cancel.isPending}
              onClick={() =>
                cancel.mutate(reason.trim() || undefined, { onSettled: () => setConfirm(false) })
              }
            >
              Confirm cancel
            </button>
          </>
        }
      >
        <label htmlFor="cancel-reason" className="label">
          Reason <span className="text-slate-400">(optional)</span>
        </label>
        <input
          id="cancel-reason"
          className="input"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </Dialog>
      <EvidenceDrawer item={openEvidence} onClose={() => setOpenEvidence(null)} />
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
