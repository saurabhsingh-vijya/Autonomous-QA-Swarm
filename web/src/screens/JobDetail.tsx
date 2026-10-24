import { useQuery } from "@tanstack/react-query";
import { Ban, Check, Copy, ExternalLink, Pause, Play, Radio, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, reportHtmlUrl } from "../api/client";
import {
  useApprovePlan,
  useCancelJob,
  useExecutions,
  useFindings,
  useJob,
  useJobEvents,
  usePlan,
  useTasks,
} from "../api/hooks";
import { problemSummary } from "../api/problem";
import type { JobEvent, Plan, TaskRecord } from "../api/types";
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
  LinkButton,
  PageHeader,
  ProblemAlert,
  SeverityChip,
  SkeletonRows,
  StatusBadge,
  Tooltip,
  stateLabel,
  useToast,
} from "../components";
import { PlanDag } from "../components/PlanDag";
import { buttonClass } from "../components/ui/Button";
import { ScreenFooter } from "../layout/AppShell";
import { formatTime, profilesSummary, repoShortName } from "../lib/format";
import { STAGE_STATUS_LABEL, stageViews, type StageView } from "../lib/stages";
import { screenById } from "./registry";

const screen = screenById("SCR-04");

const NODE_CLASS: Record<StageView["status"], string> = {
  held: "border-warn bg-warn/20 ring-4 ring-warn/20",
  awaiting_approval: "border-warn bg-warn/20 ring-4 ring-warn/20",
  not_run: "border-line-strong bg-canvas",
  not_planned: "border-dashed border-line-strong bg-canvas",
  running: "border-info bg-info/20",
  succeeded: "border-ok bg-ok",
  failed: "border-danger bg-danger",
  cancelled: "border-line-strong bg-neutral/40",
  pending: "border-line-strong bg-surface",
};

/** The one memorable element: a 13-stage rail with honest node states. */
export function StageRail({ stages }: { stages: StageView[] }) {
  return (
    <ol
      className="relative flex min-w-[900px] items-start justify-between"
      aria-label="Pipeline stages"
    >
      <span aria-hidden="true" className="absolute left-3 right-3 top-[9px] h-px bg-line-strong" />
      {stages.map((s, i) => {
        const dim = s.status === "not_run" || s.status === "not_planned";
        const emphasised = s.status === "held" || s.status === "awaiting_approval";
        return (
          <li
            key={s.key}
            data-stage={s.key}
            data-status={s.status}
            className={`relative flex w-[7.5%] flex-col items-center text-center ${
              dim ? "opacity-60" : ""
            }`}
            title={s.note ?? undefined}
          >
            <span
              className={`relative z-10 flex h-[18px] w-[18px] items-center justify-center rounded-full border-2 ${NODE_CLASS[s.status]}`}
              aria-hidden="true"
            >
              {s.status === "pending" || dim ? null : (
                <span
                  className={`h-1.5 w-1.5 rounded-full bg-current ${
                    s.status === "running" ? "rao-pulse" : ""
                  }`}
                />
              )}
            </span>
            <span className="mt-2 text-2xs text-muted">{i + 1}</span>
            <span
              className={`mt-0.5 text-xs leading-tight ${
                emphasised ? "font-medium text-text" : "text-muted"
              } ${s.status === "not_run" ? "line-through" : ""}`}
            >
              {s.name}
            </span>
            <span
              className={`mt-1 text-2xs ${
                emphasised
                  ? "text-warn"
                  : s.status === "failed"
                    ? "text-danger"
                    : s.status === "succeeded"
                      ? "text-ok"
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

function KindBadge({
  kind,
  adapter,
  modelRef,
}: {
  kind: string;
  adapter: string;
  modelRef: string | null;
}) {
  const tone = kind === "deterministic" ? "info" : modelRef ? "violet" : "neutral";
  return (
    <Badge tone={tone} title={modelRef ? `model ${modelRef}` : "no model called"}>
      {adapter}
      {modelRef ? ` · ${modelRef}` : ""}
    </Badge>
  );
}

function TaskDetails({ task }: { task: TaskRecord }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div>
        <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">
          Attempts
        </h3>
        {task.attempts.length === 0 ? (
          <p className="text-sm text-muted">No attempt has been leased.</p>
        ) : (
          <ol className="space-y-1 text-sm">
            {task.attempts.map((a) => (
              <li key={a.id} className="flex flex-wrap items-center gap-2">
                <span className="tabular-nums text-muted">#{a.attempt_no}</span>
                <StatusBadge state={a.outcome} />
                <span className="mono text-xs text-muted">{a.lease_owner}</span>
                <span className="text-xs text-muted">
                  {formatTime(a.started_at)} → {formatTime(a.ended_at)}
                </span>
                {a.error_code ? (
                  <span className="mono text-xs text-danger">
                    {a.error_code} ({a.error_class})
                  </span>
                ) : null}
              </li>
            ))}
          </ol>
        )}
        <h3 className="mb-1.5 mt-3 text-xs font-semibold uppercase tracking-wide text-muted">
          Dependencies
        </h3>
        <p className="mono text-xs text-muted">
          hard: {task.depends_on.tasks?.length ? task.depends_on.tasks.join(", ") : "none"} · soft:{" "}
          {task.depends_on.soft?.length ? task.depends_on.soft.join(", ") : "none"}
        </p>
      </div>
      <div>
        <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-muted">Outputs</h3>
        {task.outputs.length === 0 ? (
          <p className="text-sm text-muted">No output recorded for this task.</p>
        ) : (
          <ul className="space-y-2">
            {task.outputs.map((o) => (
              <li key={o.id} className="rounded-md border border-line bg-canvas p-2.5 text-xs">
                <div className="flex flex-wrap items-center gap-1.5">
                  <span className="tabular-nums text-muted">attempt {o.attempt_no}</span>
                  <Badge tone={o.validation_status === "valid" ? "ok" : "danger"}>
                    {o.validation_status}
                  </Badge>
                  <KindBadge kind={o.agent_kind} adapter={o.adapter} modelRef={o.model_ref} />
                  <span className="mono text-muted">
                    {o.schema_name} v{o.schema_version}
                  </span>
                  <span className="text-muted">
                    {o.duration_ms} ms · {o.tokens_in}/{o.tokens_out} tokens
                  </span>
                </div>
                <p className="mono mt-1 truncate text-muted" title={o.output_sha256}>
                  sha256 {o.output_sha256.slice(0, 16)}…
                </p>
                <details className="mt-1">
                  <summary className="cursor-pointer text-muted hover:text-text">Payload</summary>
                  <pre className="mt-1 max-h-64 overflow-auto rounded border border-line bg-surface p-2 font-mono text-2xs text-text">
                    {JSON.stringify(o.payload, null, 2)}
                  </pre>
                </details>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function PlanPanel({
  plan,
  tasks,
  canDecide,
  jobId,
}: {
  plan: Plan;
  tasks: TaskRecord[];
  canDecide: boolean;
  jobId: string;
}) {
  const approve = useApprovePlan(jobId);
  const { toast } = useToast();
  const [reject, setReject] = useState(false);
  const [reason, setReason] = useState("");

  const decide = (decision: "approve" | "reject") =>
    approve.mutate(
      { decision, reason: reason.trim() || undefined },
      {
        onSuccess: (res) =>
          toast({
            kind: "success",
            title: decision === "approve" ? "Plan approved" : "Plan rejected",
            description: `Job is now ${res.state.replace(/_/g, " ")}.`,
          }),
        onError: (err) =>
          toast({
            kind: "error",
            title: "Decision not recorded",
            description: problemSummary(err),
          }),
        onSettled: () => setReject(false),
      },
    );

  return (
    <section className="card" aria-labelledby="plan-heading">
      <div className="flex flex-wrap items-center gap-2 border-b border-line px-3.5 py-2.5">
        <h2 id="plan-heading" className="text-sm font-semibold text-text">
          Plan
          <span className="ml-2 text-xs font-normal text-muted">
            revision {plan.revision} · {plan.planner}
          </span>
        </h2>
        <Badge tone={plan.approval_required ? (plan.approved_at ? "ok" : "warn") : "neutral"}>
          {plan.approval_required
            ? plan.approved_at
              ? `approved ${formatTime(plan.approved_at)}`
              : "approval required (HA-05)"
            : "no approval required"}
        </Badge>
        <span className="mono ml-auto text-2xs text-muted" title={plan.plan_hash}>
          hash {plan.plan_hash.slice(0, 12)}…
        </span>
      </div>
      <div className="p-3.5">
        <PlanDag nodes={plan.nodes} tasks={tasks} />
        {canDecide ? (
          <div
            role="status"
            className="mt-3 rounded-md border border-warn/50 bg-warn/10 p-3 text-sm text-text"
          >
            <p className="font-medium text-warn">Human approval required (HA-05).</p>
            <p className="mt-1 text-muted">
              No task is enqueued until a QA Lead approves this plan. Rejecting cancels the job.
            </p>
            {approve.isError ? (
              <div className="mt-2">
                <ProblemAlert error={approve.error} />
              </div>
            ) : null}
            {reject ? (
              <div className="mt-2 space-y-2">
                <Input
                  id="reject-reason"
                  label="Reason (required to reject)"
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  maxLength={1000}
                />
                <div className="flex gap-2">
                  <Button
                    variant="danger"
                    loading={approve.isPending}
                    disabled={!reason.trim()}
                    onClick={() => decide("reject")}
                  >
                    <X className="h-4 w-4" aria-hidden="true" /> Reject plan
                  </Button>
                  <Button variant="ghost" onClick={() => setReject(false)}>
                    Back
                  </Button>
                </div>
              </div>
            ) : (
              <div className="mt-2 flex gap-2">
                <Button
                  variant="primary"
                  loading={approve.isPending}
                  onClick={() => decide("approve")}
                >
                  <Check className="h-4 w-4" aria-hidden="true" /> Approve plan
                </Button>
                <Button variant="danger" onClick={() => setReject(true)}>
                  <X className="h-4 w-4" aria-hidden="true" /> Reject
                </Button>
              </div>
            )}
          </div>
        ) : null}
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
  const planAvailable = Boolean(job.data?.plan_available);
  const plan = usePlan(jobId, planAvailable);
  const tasks = useTasks(jobId);
  const executions = useExecutions(jobId);
  const findings = useFindings(jobId);

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
  const held = j.state === "validating" && Boolean(j.held_reason);
  const awaiting = j.state === "awaiting_approval";
  const stages = stageViews(j);
  const taskRows: TaskRecord[] = Array.isArray(tasks.data?.items) ? tasks.data.items : [];
  const execRows = Array.isArray(executions.data?.items) ? executions.data.items : [];
  const findingRows = Array.isArray(findings.data?.items) ? findings.data.items : [];
  const warnings = j.warnings?.messages ?? [];
  const execByStatus = execRows.reduce<Record<string, number>>((acc, e) => {
    acc[e.status] = (acc[e.status] ?? 0) + 1;
    return acc;
  }, {});
  const inputs = j.inputs;

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
          <>
            {j.report_available ? (
              <>
                <a
                  href={reportHtmlUrl(j.id)}
                  target="_blank"
                  rel="noreferrer"
                  className={buttonClass("secondary")}
                >
                  <ExternalLink className="h-4 w-4" aria-hidden="true" /> Open HTML report
                </a>
                <LinkButton to={`/reports?job=${j.id}`} variant="primary">
                  Gates &amp; report
                </LinkButton>
              </>
            ) : null}
            {!terminal ? (
              <Button variant="danger" onClick={() => setConfirm(true)}>
                <Ban className="h-4 w-4" aria-hidden="true" /> Cancel job
              </Button>
            ) : null}
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
          className="mb-4 rounded-md border border-warn/50 bg-warn/10 px-3.5 py-2.5 text-sm text-text"
        >
          <span className="font-medium text-warn">Held at Intake & Pinning.</span> {j.held_reason}.
          No task has been enqueued and no agent has run.
        </div>
      ) : null}
      {awaiting ? (
        <div
          role="status"
          className="mb-4 rounded-md border border-warn/50 bg-warn/10 px-3.5 py-2.5 text-sm text-text"
        >
          <span className="font-medium text-warn">Awaiting plan approval.</span> {j.held_reason}
        </div>
      ) : null}
      {warnings.length ? (
        <div
          role="note"
          aria-label="Job warnings"
          className="mb-4 rounded-md border border-line bg-surface px-3.5 py-2.5 text-sm"
        >
          <p className="font-medium text-text">Warnings recorded by agents</p>
          <ul className="mt-1 list-disc space-y-0.5 pl-5 text-muted">
            {warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <section className="card mb-5 p-4" aria-labelledby="rail-heading">
        <div className="mb-4 flex items-center justify-between">
          <h2 id="rail-heading" className="text-sm font-semibold text-text">
            Pipeline
            <span className="ml-2 text-xs font-normal text-muted">
              13 stages, derived from persisted task states
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
          {plan.data ? (
            <PlanPanel plan={plan.data} tasks={taskRows} canDecide={awaiting} jobId={j.id} />
          ) : null}

          <section className="card" aria-labelledby="tasks-heading">
            <div className="flex items-center gap-2 border-b border-line px-3.5 py-2.5">
              <h2 id="tasks-heading" className="text-sm font-semibold text-text">
                Tasks
              </h2>
              {taskRows.length ? (
                <span className="text-xs text-muted">
                  {taskRows.filter((t) => t.state === "succeeded").length} of {taskRows.length}{" "}
                  succeeded
                </span>
              ) : null}
            </div>
            {tasks.isError ? (
              <div className="p-4">
                <ProblemAlert error={tasks.error} />
              </div>
            ) : taskRows.length === 0 ? (
              <div className="p-4">
                <EmptyState
                  compact
                  title="No tasks yet"
                  description={
                    awaiting
                      ? "Tasks are enqueued once the plan is approved."
                      : held
                        ? "This job has no inputs for agents to work from, so nothing was planned."
                        : "No task has been enqueued for this job."
                  }
                />
              </div>
            ) : (
              <DataTable<TaskRecord>
                caption="Tasks"
                rows={taskRows}
                rowKey={(t) => t.id}
                columns={[
                  {
                    key: "agent",
                    header: "Agent",
                    sortValue: (t) => t.agent_id ?? "",
                    render: (t) => (
                      <span>
                        <span className="mono text-muted">{t.agent_id ?? "—"}</span>{" "}
                        <span className="mono text-text">{t.task_type}</span>
                      </span>
                    ),
                  },
                  {
                    key: "stage",
                    header: "Stage",
                    render: (t) => <span className="text-muted">{t.stage.replace(/_/g, " ")}</span>,
                  },
                  {
                    key: "state",
                    header: "State",
                    sortValue: (t) => t.state,
                    render: (t) => <StatusBadge state={t.state} />,
                  },
                  {
                    key: "attempts",
                    header: "Attempts",
                    align: "right",
                    sortValue: (t) => t.attempt_count,
                    render: (t) => t.attempt_count,
                  },
                  {
                    key: "adapter",
                    header: "Adapter",
                    render: (t) => {
                      const last = t.outputs[t.outputs.length - 1];
                      return last ? (
                        <KindBadge
                          kind={last.agent_kind}
                          adapter={last.adapter}
                          modelRef={last.model_ref}
                        />
                      ) : (
                        <span className="text-muted">—</span>
                      );
                    },
                  },
                  {
                    key: "error",
                    header: "Last error",
                    render: (t) =>
                      t.last_error_code ? (
                        <span className="mono text-xs text-danger">{t.last_error_code}</span>
                      ) : (
                        <span className="text-muted">—</span>
                      ),
                  },
                ]}
                renderExpanded={(t) => <TaskDetails task={t} />}
              />
            )}
          </section>

          <div className="grid gap-5 md:grid-cols-2">
            <section className="card p-4" aria-labelledby="exec-heading">
              <h2 id="exec-heading" className="text-sm font-semibold text-text">
                Test executions
              </h2>
              {execRows.length === 0 ? (
                <p className="mt-1.5 text-sm text-muted">No test execution has been recorded.</p>
              ) : (
                <>
                  <ul className="mt-2 flex flex-wrap gap-1.5">
                    {Object.entries(execByStatus).map(([s, n]) => (
                      <li key={s}>
                        <StatusBadge state={s} />
                        <span className="ml-1 text-xs tabular-nums text-text">{n}</span>
                      </li>
                    ))}
                  </ul>
                  <div className="mt-3 flex gap-3 text-xs">
                    <Link to={`/results/api?job=${j.id}`} className="link">
                      API results
                    </Link>
                    <Link to={`/results/functional?job=${j.id}`} className="link">
                      Functional results
                    </Link>
                  </div>
                </>
              )}
            </section>
            <section className="card p-4" aria-labelledby="findings-heading">
              <h2 id="findings-heading" className="text-sm font-semibold text-text">
                Findings
              </h2>
              {findingRows.length === 0 ? (
                <p className="mt-1.5 text-sm text-muted">
                  No finding has been recorded for this job.
                </p>
              ) : (
                <ul className="mt-2 space-y-1.5 text-sm">
                  {findingRows.slice(0, 5).map((f) => (
                    <li key={f.id} className="flex items-center gap-2">
                      <SeverityChip severity={f.severity} />
                      <Link to={`/defects?job=${j.id}&finding=${f.id}`} className="mono link">
                        {f.display_id}
                      </Link>
                      <span className="min-w-0 truncate text-muted">{f.title}</span>
                      <span className="ml-auto text-xs tabular-nums text-muted">DCS {f.dcs}</span>
                    </li>
                  ))}
                  {findingRows.length > 5 ? (
                    <li>
                      <Link to={`/defects?job=${j.id}`} className="link text-xs">
                        All {findingRows.length} findings
                      </Link>
                    </li>
                  ) : null}
                </ul>
              )}
            </section>
          </div>

          <EventStream events={events} status={status} />
        </div>
        <aside className="space-y-5">
          <section className="card p-4" aria-labelledby="record-heading">
            <h2 id="record-heading" className="mb-3 text-sm font-semibold text-text">
              Job record
            </h2>
            <KeyValue
              items={[
                { label: "Id", value: j.id, mono: true },
                { label: "Project", value: j.project_id, mono: true },
                { label: "Created by", value: j.created_by ?? "—" },
                { label: "Deadline", value: formatTime(j.deadline_at) },
                { label: "Started", value: formatTime(j.started_at ?? null) },
                { label: "Ended", value: formatTime(j.ended_at ?? null) },
                { label: "Updated", value: formatTime(j.updated_at) },
                { label: "Version", value: j.version },
                {
                  label: "Plan approval",
                  value: j.require_plan_approval ? "Required (HA-05)" : "Not required",
                },
                ...(j.cancel_reason ? [{ label: "Cancel reason", value: j.cancel_reason }] : []),
              ]}
            />
            <div className="mt-3 flex gap-2">
              <Link to="/jobs" className="link text-xs">
                Back to jobs
              </Link>
              <Tooltip content="Agent registry and this job's plan graph.">
                <Link to={`/agent-graph?job=${j.id}`} className="link text-xs">
                  Agent graph
                </Link>
              </Tooltip>
            </div>
          </section>
          <section className="card p-4" aria-labelledby="inputs-heading">
            <h2 id="inputs-heading" className="mb-2 text-sm font-semibold text-text">
              Inputs
            </h2>
            {!inputs || (inputs.requirements.length === 0 && inputs.api_checks.length === 0) ? (
              <p className="text-sm text-muted">No inputs were supplied with this job.</p>
            ) : (
              <>
                <h3 className="text-xs text-muted">Requirements ({inputs.requirements.length})</h3>
                {inputs.requirements.length ? (
                  <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-text">
                    {inputs.requirements.map((r, i) => (
                      <li key={i}>{r}</li>
                    ))}
                  </ul>
                ) : null}
                <h3 className="mt-3 text-xs text-muted">API checks ({inputs.api_checks.length})</h3>
                {inputs.api_checks.length ? (
                  <ul className="mt-1 space-y-0.5 font-mono text-xs text-text">
                    {inputs.api_checks.map((c, i) => (
                      <li key={i}>
                        {c.method} {c.url} → {c.expected_status}{" "}
                        <span className="text-muted">{c.priority}</span>
                      </li>
                    ))}
                  </ul>
                ) : null}
              </>
            )}
          </section>
          {taskRows.length ? (
            <section className="card p-4" aria-labelledby="summary-heading">
              <h2 id="summary-heading" className="mb-2 text-sm font-semibold text-text">
                Task states
              </h2>
              <ul className="flex flex-wrap gap-1.5">
                {Object.entries(j.task_summary ?? {}).map(([s, n]) => (
                  <li key={s} className="flex items-center gap-1">
                    <StatusBadge state={s} />
                    <span className="text-xs tabular-nums text-text">{n}</span>
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs text-muted">
                {stateLabel(j.state)}; derived from {taskRows.length} persisted task records.
              </p>
            </section>
          ) : null}
        </aside>
      </div>

      <Dialog
        open={confirm}
        onClose={() => setConfirm(false)}
        title={`Cancel ${j.display_id}?`}
        description="The job moves to cancelled via the state machine. Pending tasks are marked cancelled; a task already running finishes its attempt and its output is kept."
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
