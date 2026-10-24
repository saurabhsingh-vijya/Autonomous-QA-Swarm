import { useQuery } from "@tanstack/react-query";
import { Ban, Copy, Pause, Play, Radio } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client";
import { useCancelJob, useJob, useJobEvents } from "../api/hooks";
import { problemSummary } from "../api/problem";
import type { JobEvent } from "../api/types";
import { TERMINAL_JOB_STATES } from "../api/types";
import {
  Badge,
  Button,
  DataTable,
  Dialog,
  EmptyState,
  ErrorState,
  Input,
  KeyValue,
  PageHeader,
  ProblemAlert,
  SkeletonRows,
  StatusBadge,
  Tooltip,
  useToast,
} from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime, profilesSummary, repoShortName } from "../lib/format";
import { STAGE_STATUS_LABEL, stageViews, type StageView } from "../lib/stages";
import { screenById } from "./registry";

const screen = screenById("SCR-04");

/** The one memorable element: a 13-stage rail with honest node states. */
export function StageRail({ stages }: { stages: StageView[] }) {
  return (
    <ol
      className="relative flex min-w-[900px] items-start justify-between"
      aria-label="Pipeline stages"
    >
      <span aria-hidden="true" className="absolute left-3 right-3 top-[9px] h-px bg-line-strong" />
      {stages.map((s, i) => {
        const node =
          s.status === "held"
            ? "border-warn bg-warn/20 ring-4 ring-warn/20"
            : s.status === "not_run"
              ? "border-line-strong bg-canvas"
              : s.status === "running"
                ? "border-info bg-info/20"
                : s.status === "succeeded"
                  ? "border-ok bg-ok"
                  : s.status === "failed"
                    ? "border-danger bg-danger"
                    : "border-line-strong bg-surface";
        return (
          <li
            key={s.key}
            data-stage={s.key}
            data-status={s.status}
            className={`relative flex w-[7.5%] flex-col items-center text-center ${
              s.status === "not_run" ? "opacity-60" : ""
            }`}
          >
            <span
              className={`relative z-10 flex h-[18px] w-[18px] items-center justify-center rounded-full border-2 ${node}`}
              aria-hidden="true"
            >
              {s.status === "pending" || s.status === "not_run" ? null : (
                <span className="h-1.5 w-1.5 rounded-full bg-current" />
              )}
            </span>
            <span className="mt-2 text-2xs text-muted">{i + 1}</span>
            <span
              className={`mt-0.5 text-xs leading-tight ${
                s.status === "held" ? "font-medium text-text" : "text-muted"
              } ${s.status === "not_run" ? "line-through" : ""}`}
            >
              {s.name}
            </span>
            <span
              className={`mt-1 text-2xs ${
                s.status === "held"
                  ? "text-warn"
                  : s.status === "failed"
                    ? "text-danger"
                    : "text-muted"
              }`}
            >
              {STAGE_STATUS_LABEL[s.status]}
            </span>
            {s.note ? <span className="sr-only">{s.note}</span> : null}
          </li>
        );
      })}
    </ol>
  );
}

function EventStream({ events, status }: { events: JobEvent[]; status: string }) {
  const [follow, setFollow] = useState(true);
  const box = useRef<HTMLDivElement>(null);
  const { toast } = useToast();

  useEffect(() => {
    if (follow && box.current) box.current.scrollTop = box.current.scrollHeight;
  }, [events, follow]);

  const onScroll = () => {
    const el = box.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 8;
    if (!atBottom && follow) setFollow(false);
    if (atBottom && !follow) setFollow(true);
  };

  const copy = async (e: JobEvent) => {
    try {
      await navigator.clipboard.writeText(JSON.stringify(e, null, 2));
      toast({ kind: "success", title: "Event copied" });
    } catch {
      toast({ kind: "error", title: "Event not copied", description: "Clipboard unavailable." });
    }
  };

  return (
    <section className="card" aria-labelledby="events-heading">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3.5 py-2">
        <h2 id="events-heading" className="text-sm font-semibold text-text">
          Event stream
        </h2>
        <span
          className={`inline-flex items-center gap-1.5 rounded border px-1.5 text-2xs ${
            status === "live"
              ? "border-ok/40 text-ok"
              : status === "connecting"
                ? "border-line text-muted"
                : "border-line-strong text-muted"
          }`}
          aria-live="polite"
        >
          <Radio className="h-3 w-3" aria-hidden="true" />
          {status === "live"
            ? "SSE live"
            : status === "connecting"
              ? "Connecting"
              : status === "closed"
                ? "Stream ended"
                : "Disconnected"}
        </span>
        <span className="text-2xs text-muted">{events.length} received</span>
        <Button
          size="sm"
          variant="ghost"
          className="ml-auto"
          onClick={() => setFollow((f) => !f)}
          aria-pressed={follow}
        >
          {follow ? (
            <>
              <Pause className="h-3.5 w-3.5" aria-hidden="true" /> Pause autoscroll
            </>
          ) : (
            <>
              <Play className="h-3.5 w-3.5" aria-hidden="true" /> Follow
            </>
          )}
        </Button>
      </div>
      <div
        ref={box}
        onScroll={onScroll}
        className="max-h-80 overflow-auto bg-canvas font-mono text-xs"
        tabIndex={0}
        aria-label="Event log"
      >
        {events.length === 0 ? (
          <p className="p-3 text-muted">
            No events on this connection yet. Earlier events replay when the stream connects.
          </p>
        ) : (
          <ol className="divide-y divide-line/60">
            {events.map((e, i) => (
              <li key={`${e.id}-${i}`} className="group flex items-start gap-3 px-3 py-1.5">
                <span className="w-16 shrink-0 tabular-nums text-muted">
                  {e.receivedAt ? e.receivedAt.slice(11, 19) : "—"}
                </span>
                <span className="w-8 shrink-0 text-right tabular-nums text-muted">
                  {e.id || "—"}
                </span>
                <span className="w-40 shrink-0 text-accent">{e.type}</span>
                <span className="min-w-0 flex-1 break-all text-text">
                  {typeof e.data === "string" ? e.data : JSON.stringify(e.data)}
                </span>
                <button
                  type="button"
                  onClick={() => copy(e)}
                  className="shrink-0 rounded p-0.5 text-muted opacity-0 hover:text-text focus:opacity-100 group-hover:opacity-100"
                  aria-label={`Copy event ${e.id}`}
                >
                  <Copy className="h-3 w-3" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ol>
        )}
      </div>
    </section>
  );
}

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
  const { toast } = useToast();
  const [confirm, setConfirm] = useState(false);
  const [reason, setReason] = useState("");

  if (job.isLoading) return <SkeletonRows rows={6} label="Loading job" />;
  if (job.isError || !job.data)
    return (
      <div>
        <PageHeader crumbs={[{ label: "Jobs", to: "/jobs" }]} title="Job" />
        <ErrorState error={job.error ?? new Error("Job not found")} onRetry={() => job.refetch()} />
      </div>
    );
  const j = job.data;
  const terminal = TERMINAL_JOB_STATES.includes(j.state);
  const held = Boolean(j.held_reason) && !terminal;
  const stages = stageViews(j);
  const tasks = Object.entries(j.task_summary ?? {});

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Jobs", to: "/jobs" }, { label: j.display_id }]}
        title={j.display_id}
        badge={<StatusBadge state={j.state} />}
        subtitle={
          <span className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <span className="mono text-text">
              {repo.data ? repoShortName(repo.data.url) : j.repository_id}
            </span>
            <span className="mono">
              {j.ref}
              {j.commit_sha ? ` ${j.commit_sha.slice(0, 10)}` : ""}
            </span>
            {!j.commit_sha ? <Badge tone="neutral">commit not pinned</Badge> : null}
            <span>{profilesSummary(j.profiles)}</span>
            <span>created {formatTime(j.created_at)}</span>
          </span>
        }
        actions={
          !terminal ? (
            <Button variant="danger" onClick={() => setConfirm(true)}>
              <Ban className="h-4 w-4" aria-hidden="true" /> Cancel job
            </Button>
          ) : undefined
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
          className="mb-4 rounded-md border border-warn/50 bg-warn/10 px-3.5 py-2.5 text-sm text-text"
        >
          <span className="font-medium text-warn">Held at Intake & Pinning.</span> {j.held_reason}.
          No task has been leased and no sandbox has started.
        </div>
      ) : null}

      <section className="card mb-5 p-4" aria-labelledby="rail-heading">
        <div className="mb-4 flex items-center justify-between">
          <h2 id="rail-heading" className="text-sm font-semibold text-text">
            Pipeline
            <span className="ml-2 text-xs font-normal text-muted">
              13 stages, derived from job state
            </span>
          </h2>
          {j.current_stage ? (
            <span className="text-xs text-muted">
              current stage <span className="mono text-text">{j.current_stage}</span>
            </span>
          ) : null}
        </div>
        <div className="overflow-x-auto pb-1">
          <StageRail stages={stages} />
        </div>
      </section>

      <div className="grid grid-cols-1 gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <EventStream events={events} status={status} />
          <section className="card" aria-labelledby="tasks-heading">
            <div className="border-b border-line px-3.5 py-2.5">
              <h2 id="tasks-heading" className="text-sm font-semibold text-text">
                Tasks
              </h2>
            </div>
            {tasks.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  compact
                  title="No tasks yet"
                  description="Tasks are enqueued when a plan is accepted (slice 2c). Nothing has been leased for this job."
                />
              </div>
            ) : (
              <DataTable
                caption="Tasks by state"
                rows={tasks.map(([state, count]) => ({ state, count }))}
                rowKey={(r) => r.state}
                columns={[
                  { key: "state", header: "State", render: (r) => <StatusBadge state={r.state} /> },
                  {
                    key: "count",
                    header: "Tasks",
                    align: "right",
                    sortValue: (r) => r.count,
                    render: (r) => r.count,
                  },
                ]}
              />
            )}
          </section>
        </div>
        <aside className="card p-4" aria-labelledby="record-heading">
          <h2 id="record-heading" className="mb-3 text-sm font-semibold text-text">
            Job record
          </h2>
          <KeyValue
            items={[
              { label: "Id", value: j.id, mono: true },
              { label: "Project", value: j.project_id, mono: true },
              { label: "Created by", value: j.created_by ?? "—" },
              { label: "Deadline", value: formatTime(j.deadline_at) },
              { label: "Updated", value: formatTime(j.updated_at) },
              { label: "Ended", value: formatTime(j.ended_at ?? null) },
              { label: "Version", value: j.version },
              ...(j.cancel_reason ? [{ label: "Cancel reason", value: j.cancel_reason }] : []),
            ]}
          />
          <p className="mt-3 text-xs text-muted">
            Resource usage, logs and retry controls arrive with the Execution Service (slice 1c).
            Retry is not offered because the backend has no retry endpoint yet.
          </p>
          <div className="mt-3 flex gap-2">
            <Link to="/jobs" className="link text-xs">
              Back to jobs
            </Link>
            <Tooltip content="Tasks, agent handoffs and the plan DAG are shown once planning exists (slice 2c).">
              <Link to="/agent-graph" className="link text-xs">
                Agent registry
              </Link>
            </Tooltip>
          </div>
        </aside>
      </div>

      <Dialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={`Cancel ${j.display_id}?`}
        description="The job moves through cancelling to cancelled via the state machine. Any workers would be destroyed; in this build there are none."
        footer={
          <>
            <Button onClick={() => setConfirm(false)}>Keep job</Button>
            <Button
              variant="danger"
              loading={cancel.isPending}
              onClick={() =>
                cancel.mutate(reason.trim() || undefined, {
                  onSuccess: (res) =>
                    toast({
                      kind: "success",
                      title: "Job cancelled",
                      description: `${j.display_id} is now ${res.state.replace(/_/g, " ")}.`,
                    }),
                  onError: (err) =>
                    toast({
                      kind: "error",
                      title: "Job not cancelled",
                      description: problemSummary(err),
                    }),
                  onSettled: () => setConfirm(false),
                })
              }
            >
              Cancel job
            </Button>
          </>
        }
      >
        <Input
          id="cancel-reason"
          label="Reason"
          optional
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          maxLength={1000}
        />
      </Dialog>
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
