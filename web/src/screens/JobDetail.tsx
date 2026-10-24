import { Ban, Radio } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useCancelJob, useJob, useJobEvents } from "../api/hooks";
import { TERMINAL_JOB_STATES } from "../api/types";
import { Dialog, LoadingState, PageHeader, ProblemAlert, StatusBadge } from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime, profilesSummary } from "../lib/format";
import { useQuery } from "@tanstack/react-query";
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

export function JobDetailScreen() {
  const { jobId = "" } = useParams();
  const job = useJob(jobId);
  const repo = useQuery({
    queryKey: ["repositories", "detail", job.data?.repository_id],
    queryFn: () => api.getRepository(job.data!.repository_id),
    enabled: Boolean(job.data?.repository_id),
  });
  const cancel = useCancelJob(jobId);
  const { events, status } = useJobEvents(jobId);
  const [confirm, setConfirm] = useState(false);
  const [reason, setReason] = useState("");

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
            · {j.ref} → {j.commit_sha ?? "not pinned"} · {profilesSummary(j.profiles)} · created{" "}
            {formatTime(j.created_at)}
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
          <strong>Held:</strong> {j.held_reason}. No task has been leased and no sandbox has
          started.
        </div>
      ) : null}

      <section className="card mb-6 p-4">
        <h2 className="mb-3 text-sm font-semibold text-slate-900">
          Pipeline stages{" "}
          <span className="font-normal text-slate-500">13 stages · derived from job state</span>
        </h2>
        <ol className="grid grid-cols-2 gap-2 md:grid-cols-4 xl:grid-cols-7">
          {STAGES.map((name, i) => {
            const isIntake = i === 0;
            const label =
              isIntake && held ? "Held — slice 1b" : isIntake && terminal ? "Not run" : "Pending";
            return (
              <li
                key={name}
                className={`rounded-lg border p-2 text-xs ${
                  isIntake && held ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white"
                }`}
              >
                <div className="text-[11px] font-semibold text-slate-500">{i + 1}</div>
                <div className="font-medium text-slate-800">{name}</div>
                <div className="mt-1 text-slate-500">{label}</div>
              </li>
            );
          })}
        </ol>
      </section>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <section className="card lg:col-span-2">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3">
            <h2 className="text-sm font-semibold text-slate-900">
              Live events{" "}
              <span className="font-normal text-slate-500">GET /jobs/{"{id}"}/events</span>
            </h2>
            <span className="text-xs text-slate-500">{events.length} received</span>
          </div>
          {events.length === 0 ? (
            <p className="p-4 text-sm text-slate-500">
              No events received yet on this connection. Earlier events are replayed when the stream
              connects with a Last-Event-ID.
            </p>
          ) : (
            <ul className="divide-y divide-slate-100 font-mono text-xs">
              {events.map((e, i) => (
                <li key={`${e.id}-${i}`} className="flex gap-3 px-4 py-2">
                  <span className="w-28 shrink-0 text-slate-400">{e.id || "—"}</span>
                  <span className="w-40 shrink-0 font-semibold text-slate-700">{e.type}</span>
                  <span className="min-w-0 break-all text-slate-600">
                    {typeof e.data === "string" ? e.data : JSON.stringify(e.data)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <aside className="card p-4 text-sm">
          <h2 className="mb-2 text-sm font-semibold text-slate-900">Job record</h2>
          <dl className="space-y-1.5 text-slate-700">
            <div className="flex justify-between gap-2">
              <dt className="text-slate-500">ID</dt>
              <dd className="truncate font-mono text-xs">{j.id}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-slate-500">Project</dt>
              <dd className="truncate font-mono text-xs">{j.project_id}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-slate-500">Deadline</dt>
              <dd>{formatTime(j.deadline_at)}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-slate-500">Version</dt>
              <dd>{j.version}</dd>
            </div>
            <div className="flex justify-between gap-2">
              <dt className="text-slate-500">Updated</dt>
              <dd>{formatTime(j.updated_at)}</dd>
            </div>
          </dl>
          <p className="mt-3 text-xs text-slate-500">
            Tasks, resource usage and the log tail arrive with the Execution Service (slices 1c–1d).{" "}
            <Link to="/jobs" className="text-primary underline">
              Back to jobs
            </Link>
          </p>
        </aside>
      </div>

      <Dialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={`Cancel ${j.display_id}?`}
        description="The job moves through cancelling to cancelled via the state machine. Any workers would be destroyed; in slice 1a there are none."
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
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
