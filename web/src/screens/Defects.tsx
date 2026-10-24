import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { DEV_ROLE } from "../api/client";
import { useFindingEvidence, useFindingHistory, useFindings, useTriageFinding } from "../api/hooks";
import { problemSummary, toProblem } from "../api/problem";
import type {
  EvidenceItem,
  Finding,
  FindingStatus,
  PriorityBreakdown,
  TriageAction,
  TriageRequest,
} from "../api/types";
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
  SeverityChip,
  SkeletonRows,
  StatusBadge,
  Textarea,
  useToast,
} from "../components";
import { EvidenceDrawer } from "../components/EvidenceDrawer";
import { JobSelect } from "../components/JobSelect";
import { ScreenFooter } from "../layout/AppShell";
import { formatLocation } from "../lib/compare";
import { formatTime } from "../lib/format";
import { useJobSelection } from "../lib/useJobSelection";
import { screenById } from "./registry";

const screen = screenById("SCR-11");

const DCS_LABEL: Record<string, string> = {
  reproducibility: "Reproducibility (35)",
  deterministic_oracle: "Deterministic oracle (25)",
  evidence_completeness: "Evidence completeness (15)",
  independent_corroboration: "Independent corroboration (15)",
  stability_history: "Stability history (10)",
  reproduced: "Reproduced",
  evidence: "Evidence attached",
  oracle: "Oracle defined",
  occurrences: "Occurrences",
  independent: "Independent runs",
  severity: "Severity signal",
};

type StatusFilter = "all" | "open" | "rejected" | "accepted";

const STATUS_FILTERS: { key: StatusFilter; label: string; statuses?: FindingStatus[] }[] = [
  { key: "all", label: "All" },
  { key: "open", label: "Open", statuses: ["candidate", "reopened"] },
  { key: "rejected", label: "Rejected", statuses: ["false_positive", "duplicate"] },
  { key: "accepted", label: "Accepted risk", statuses: ["accepted_risk"] },
];

/** Legal triage actions per current status (mirrors backend/src/qaswarm/defects/triage.py). */
const OPEN_FOR_TRIAGE: FindingStatus[] = [
  "candidate",
  "triaging",
  "confirmed",
  "reopened",
  "fix_failed",
];
const REOPENABLE: FindingStatus[] = [
  "false_positive",
  "duplicate",
  "accepted_risk",
  "not_reproducible",
  "fix_verified",
];

// eslint-disable-next-line react-refresh/only-export-components
export function legalTriageActions(status: FindingStatus): TriageAction[] {
  if (OPEN_FOR_TRIAGE.includes(status))
    return ["mark_false_positive", "mark_duplicate", "accept_risk"];
  if (REOPENABLE.includes(status)) return ["reopen"];
  return [];
}

const ACTION_LABEL: Record<TriageAction, { button: string; done: string; title: string }> = {
  mark_false_positive: {
    button: "Mark false positive",
    done: "Marked false positive",
    title: "Mark false positive",
  },
  mark_duplicate: { button: "Mark duplicate", done: "Marked duplicate", title: "Mark duplicate" },
  accept_risk: { button: "Accept risk", done: "Risk accepted", title: "Accept risk" },
  reopen: { button: "Reopen", done: "Reopened", title: "Reopen finding" },
  request_reproduction: {
    button: "Request reproduction",
    done: "Reproduction requested",
    title: "Request reproduction",
  },
};

// eslint-disable-next-line react-refresh/only-export-components
export function priorityFormula(b: PriorityBreakdown): string {
  return `severity ${b.severity_weight} × confidence ${b.confidence_factor} × exposure ${b.exposure_factor} = ${b.value}`;
}

function hasBreakdown(b: Finding["priority_breakdown"]): b is PriorityBreakdown {
  return Boolean(b && typeof (b as PriorityBreakdown).formula === "string");
}

export function DcsBar({ value, breakdown }: { value: number; breakdown: Record<string, number> }) {
  const tone = value >= 80 ? "bg-ok" : value >= 50 ? "bg-info" : "bg-warn";
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted">Defect Confidence Score</span>
        <span className="tabular-nums font-medium text-text">{value} / 100</span>
      </div>
      <div
        className="mt-1 h-2 w-full overflow-hidden rounded bg-raised"
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={value}
        aria-label="Defect Confidence Score"
      >
        <span className={`block h-full ${tone}`} style={{ width: `${value}%` }} />
      </div>
      <ul className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5 text-2xs text-muted">
        {Object.entries(breakdown).map(([k, v]) => (
          <li key={k}>
            {DCS_LABEL[k] ?? k.replace(/_/g, " ")}{" "}
            <span className="tabular-nums text-text">{v}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function SectionTitle({ children, tone = "" }: { children: string; tone?: string }) {
  return (
    <h3 className={`text-xs font-semibold uppercase tracking-wide ${tone || "text-muted"}`}>
      {children}
    </h3>
  );
}

/* ----------------------------------------------------------------- triage dialog */

function TriageDialog({
  action,
  finding,
  duplicateOptions,
  busy,
  onClose,
  onSubmit,
}: {
  action: TriageAction | null;
  finding: Finding;
  duplicateOptions: { id: string; label: string }[];
  busy: boolean;
  onClose: () => void;
  onSubmit: (body: TriageRequest) => void;
}) {
  const [reason, setReason] = useState("");
  const [duplicateOf, setDuplicateOf] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  useEffect(() => {
    setReason("");
    setDuplicateOf(duplicateOptions[0]?.id ?? "");
    setExpiresAt("");
  }, [action, duplicateOptions]);
  if (!action) return null;
  const label = ACTION_LABEL[action];
  const needsReason = action === "mark_false_positive" || action === "accept_risk";
  const valid =
    (!needsReason || reason.trim().length > 0) &&
    (action !== "mark_duplicate" || duplicateOf.trim().length > 0) &&
    (action !== "accept_risk" || expiresAt.length > 0);
  const submit = () => {
    const body: TriageRequest = { action, reason: reason.trim() || null };
    if (action === "mark_duplicate") body.duplicate_of = duplicateOf.trim();
    if (action === "accept_risk") body.expires_at = new Date(expiresAt).toISOString();
    onSubmit(body);
  };
  return (
    <Dialog
      open
      onClose={onClose}
      title={label.title}
      description={`${finding.display_id} · ${finding.title}`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={busy}>
            Cancel
          </Button>
          <Button variant="primary" onClick={submit} disabled={!valid || busy}>
            {label.button}
          </Button>
        </>
      }
    >
      <div className="space-y-3">
        {action === "mark_duplicate" ? (
          <div>
            <label htmlFor="dup-of" className="label">
              Duplicate of
            </label>
            {duplicateOptions.length ? (
              <select
                id="dup-of"
                className="input"
                value={duplicateOptions.some((o) => o.id === duplicateOf) ? duplicateOf : "__other"}
                onChange={(e) => setDuplicateOf(e.target.value === "__other" ? "" : e.target.value)}
              >
                {duplicateOptions.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.label}
                  </option>
                ))}
                <option value="__other">Another finding id…</option>
              </select>
            ) : null}
            {!duplicateOptions.some((o) => o.id === duplicateOf) ? (
              <Input
                label="Finding id"
                placeholder="fnd_…"
                value={duplicateOf}
                onChange={(e) => setDuplicateOf(e.target.value)}
                hint="The original finding this one duplicates. Evidence of both stays accessible."
              />
            ) : null}
          </div>
        ) : null}
        {action === "accept_risk" ? (
          <Input
            label="Expires on"
            type="date"
            value={expiresAt}
            onChange={(e) => setExpiresAt(e.target.value)}
            hint="HA-08: accepted risk needs an expiry; on expiry the finding reopens."
          />
        ) : null}
        <Textarea
          label="Reason"
          optional={!needsReason}
          rows={3}
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          hint={
            needsReason
              ? "Recorded in the audit trail with your user and role."
              : "Optional; recorded in the audit trail if given."
          }
        />
      </div>
    </Dialog>
  );
}

/* ----------------------------------------------------------------- finding card */

function FindingCard({
  finding,
  jobId,
  onEvidence,
}: {
  finding: Finding;
  jobId: string | undefined;
  onEvidence: (evidenceId?: string) => void;
}) {
  const { toast } = useToast();
  const triage = useTriageFinding(jobId);
  const history = useFindingHistory(finding.id);
  const [pending, setPending] = useState<TriageAction | null>(null);

  const facts = finding.facts.items ?? [];
  const inferred = finding.inferred.items ?? [];
  const evidenceCount = finding.evidence_ids.items?.length ?? 0;
  const hypotheses = finding.root_causes?.items ?? [];
  const affected = finding.affected_tests?.items ?? [];
  const repro = finding.reproducibility ?? {};
  const prior = finding.history?.prior_occurrences ?? [];
  const timeline = finding.status_history?.items ?? [];
  const actions = legalTriageActions(finding.status);
  const breakdown = finding.priority_breakdown;

  const others = useMemo(
    () =>
      (Array.isArray(history.data?.items) ? history.data.items : []).filter(
        (h) => h.id !== finding.id,
      ),
    [history.data, finding.id],
  );
  const duplicateOptions = useMemo(
    () => others.map((h) => ({ id: h.id, label: `${h.display_id} · ${h.title}` })),
    [others],
  );

  const run = (body: TriageRequest) => {
    const label = ACTION_LABEL[body.action];
    triage.mutate(
      { finding, body },
      {
        onSuccess: () => {
          setPending(null);
          toast({ kind: "success", title: label.done, description: finding.display_id });
        },
        onError: (err) => {
          const p = toProblem(err);
          if (p.status === 412) {
            setPending(null);
            toast({
              kind: "error",
              title: "Finding changed since you read it",
              description: "The latest version has been loaded; review it and try again.",
            });
            return;
          }
          toast({
            kind: "error",
            title: `${label.title} failed`,
            description: problemSummary(err),
          });
        },
      },
    );
  };

  return (
    <article className="card p-4" aria-labelledby={`f-${finding.id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <SeverityChip severity={finding.severity} />
        <h2 id={`f-${finding.id}`} className="text-sm font-semibold text-text">
          <span className="mono text-muted">{finding.display_id}</span> {finding.title}
        </h2>
        <StatusBadge state={finding.confidence} />
        <StatusBadge state={finding.status} />
        {finding.history?.recurring ? <Badge tone="warn">Seen before</Badge> : null}
        <span className="ml-auto text-xs text-muted">{formatTime(finding.created_at)}</span>
      </div>

      {finding.description ? (
        <section className="mt-3" aria-label="Description">
          <SectionTitle>Description</SectionTitle>
          <p className="mt-1 text-sm text-text">{finding.description}</p>
        </section>
      ) : null}

      <div className="mt-4 grid gap-5 lg:grid-cols-3">
        <div className="space-y-5 lg:col-span-2">
          <div className="grid gap-4 md:grid-cols-2">
            <section aria-label="Verified facts">
              <SectionTitle tone="text-ok">Facts (observed)</SectionTitle>
              {facts.length ? (
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-text">
                  {facts.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm text-muted">No facts recorded.</p>
              )}
            </section>
            <section aria-label="Inferred notes">
              <SectionTitle tone="text-warn">Inferred (not verified)</SectionTitle>
              {inferred.length ? (
                <ul className="mt-1 list-disc space-y-0.5 pl-4 text-sm text-muted">
                  {inferred.map((f) => (
                    <li key={f}>{f}</li>
                  ))}
                </ul>
              ) : (
                <p className="mt-1 text-sm text-muted">No inference recorded.</p>
              )}
            </section>
          </div>

          <section aria-label="Likely root causes">
            <SectionTitle>Likely root causes</SectionTitle>
            {hypotheses.length ? (
              <ul className="mt-1 space-y-2">
                {hypotheses.map((h, i) => (
                  <li key={i} className="rounded-md border border-line bg-surface p-2.5 text-sm">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge tone="neutral">uncertainty</Badge>
                      <StatusBadge state={h.uncertainty} />
                      <span className="text-2xs text-muted">{h.source}</span>
                    </div>
                    <p className="mt-1 text-text">{h.hypothesis}</p>
                    <p className="mt-0.5 text-xs text-muted">Basis: {h.basis}</p>
                    {h.supporting_evidence.length ? (
                      <p className="mt-1 flex flex-wrap items-center gap-1 text-xs text-muted">
                        Evidence:
                        {h.supporting_evidence.map((id) => (
                          <button
                            key={id}
                            type="button"
                            className="mono rounded border border-line px-1 text-2xs text-accent rao-transition hover:bg-raised"
                            onClick={() => onEvidence(id)}
                          >
                            {id}
                          </button>
                        ))}
                      </p>
                    ) : null}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-1 text-sm text-muted">No hypothesis could be derived.</p>
            )}
            <p className="mt-1.5 text-xs text-muted">
              Hypotheses are rule-based and unverified; none changes the score.
            </p>
          </section>

          <section aria-label="Priority">
            <SectionTitle>Priority</SectionTitle>
            {hasBreakdown(breakdown) ? (
              <div className="mt-1 text-sm">
                <span className="tabular-nums font-semibold text-text">{breakdown.value}</span>
                <span className="ml-2 mono text-xs text-muted">{priorityFormula(breakdown)}</span>
                <p className="mt-0.5 text-xs text-muted">
                  {breakdown.severity} · {breakdown.confidence} · {breakdown.exposure}.{" "}
                  {breakdown.note}
                </p>
              </div>
            ) : (
              <p className="mt-1 text-sm text-muted">
                Priority {finding.risk_priority ?? 0} (no breakdown stored).
              </p>
            )}
          </section>

          <DcsBar value={finding.dcs} breakdown={finding.dcs_breakdown} />

          <section aria-label="Reproducibility" className="rounded-md border border-line p-3">
            <SectionTitle>Reproducibility</SectionTitle>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm">
              <span>
                Attempted:{" "}
                <span className="font-medium text-text">{repro.attempted ? "yes" : "no"}</span>
              </span>
              <span>
                Runs: <span className="tabular-nums text-text">{repro.runs ?? 0}</span>
              </span>
              <span>
                Reproduced: <span className="tabular-nums text-text">{repro.reproduced ?? 0}</span>
              </span>
            </div>
            {repro.note ? <p className="mt-1 text-xs text-muted">{repro.note}</p> : null}
          </section>

          <section aria-label="Affected tests">
            <SectionTitle>Affected tests</SectionTitle>
            {affected.length ? (
              <div className="mt-1">
                <DataTable
                  caption="Affected tests"
                  rows={affected}
                  rowKey={(t) => t.execution_id}
                  columns={[
                    { key: "name", header: "Name", render: (t) => <span>{t.name}</span> },
                    {
                      key: "status",
                      header: "Status",
                      render: (t) => <StatusBadge state={t.status} />,
                    },
                    {
                      key: "scn",
                      header: "Scenario",
                      render: (t) => (
                        <span className="mono text-xs text-muted">{t.scenario_id ?? "—"}</span>
                      ),
                    },
                  ]}
                />
              </div>
            ) : (
              <p className="mt-1 text-sm text-muted">No linked execution.</p>
            )}
          </section>

          <section aria-label="Seen before">
            <SectionTitle>Seen before</SectionTitle>
            {history.isLoading ? (
              <p className="mt-1 text-sm text-muted">Loading history.</p>
            ) : others.length || prior.length ? (
              <div className="mt-1 text-sm">
                {finding.history?.first_seen ? (
                  <p className="text-muted">
                    First seen in {finding.history.first_seen.job_display_id} as{" "}
                    <span className="mono">{finding.history.first_seen.display_id}</span> on{" "}
                    {formatTime(finding.history.first_seen.seen_at)}.
                  </p>
                ) : null}
                <ul className="mt-1 space-y-1">
                  {(others.length
                    ? others.map((h) => ({
                        key: h.id,
                        display_id: h.display_id,
                        job: prior.find((p) => p.finding_id === h.id)?.job_display_id ?? h.job_id,
                        ref: prior.find((p) => p.finding_id === h.id)?.job_ref ?? "",
                        status: h.status,
                        at: h.created_at,
                      }))
                    : prior.map((p) => ({
                        key: p.finding_id,
                        display_id: p.display_id,
                        job: p.job_display_id,
                        ref: p.job_ref,
                        status: p.status,
                        at: p.seen_at,
                      }))
                  ).map((h) => (
                    <li key={h.key} className="flex flex-wrap items-center gap-2">
                      <span className="mono text-xs">{h.display_id}</span>
                      <span className="text-muted">
                        {h.job}
                        {h.ref ? ` @ ${h.ref}` : ""}
                      </span>
                      <StatusBadge state={h.status} />
                      <span className="text-xs text-muted">{formatTime(h.at)}</span>
                    </li>
                  ))}
                </ul>
                <p className="mt-1 text-xs text-muted">
                  Recurrence is a recorded fact; it does not count as a reproduction.
                </p>
              </div>
            ) : (
              <p className="mt-1 text-sm text-muted">Not seen before on this repository.</p>
            )}
          </section>

          <section aria-label="Status history">
            <SectionTitle>Status history</SectionTitle>
            {timeline.length ? (
              <ol className="mt-1 space-y-1 border-l border-line pl-3 text-sm">
                {timeline.map((e, i) => (
                  <li key={i}>
                    <span className="text-xs text-muted">{formatTime(e.at)}</span>{" "}
                    <span className="text-text">{e.action.replace(/_/g, " ")}</span>{" "}
                    <span className="text-muted">
                      {e.from ? `${e.from} → ` : ""}
                      {e.to} · {e.actor_id} ({e.role})
                    </span>
                    {e.reason ? <span className="block text-xs text-muted">{e.reason}</span> : null}
                  </li>
                ))}
              </ol>
            ) : (
              <p className="mt-1 text-sm text-muted">No status change recorded.</p>
            )}
          </section>
        </div>

        <aside className="space-y-4">
          <KeyValue
            items={[
              { label: "Category", value: finding.category, mono: true },
              { label: "Location", value: formatLocation(finding.location), mono: true },
              { label: "Occurrences", value: finding.occurrences },
              { label: "Evidence items", value: evidenceCount },
              { label: "Executions", value: finding.test_execution_ids.items?.length ?? 0 },
              { label: "Fingerprint", value: finding.fingerprint.slice(0, 16) + "…", mono: true },
              { label: "Version", value: `v${finding.version}`, mono: true },
            ]}
          />
          <Button size="sm" onClick={() => onEvidence()} disabled={evidenceCount === 0}>
            View evidence ({evidenceCount})
          </Button>

          <section aria-label="Triage" className="rounded-md border border-line p-3">
            <SectionTitle>Triage</SectionTitle>
            <p className="mt-1 text-xs text-muted">
              Acting as <span className="text-text">{DEV_ROLE}</span>. False positive and accepted
              risk need a QA Lead; duplicate and reopen need a QA Lead or QA Engineer.
            </p>
            {finding.triage?.action ? (
              <p className="mt-2 text-xs text-muted">
                Last decision: {finding.triage.action.replace(/_/g, " ")} by{" "}
                {finding.triage.actor_id} ({finding.triage.role}) on {formatTime(finding.triage.at)}
                {finding.triage.reason ? ` — "${finding.triage.reason}"` : ""}
                {finding.triage.expires_at
                  ? `; expires ${formatTime(finding.triage.expires_at)}`
                  : ""}
                {finding.duplicate_of ? (
                  <>
                    ; duplicate of <span className="mono">{finding.duplicate_of}</span>
                  </>
                ) : null}
              </p>
            ) : null}
            <div className="mt-2 flex flex-wrap gap-2">
              {actions.map((a) => (
                <Button
                  key={a}
                  size="sm"
                  variant={a === "mark_false_positive" ? "danger" : "secondary"}
                  onClick={() => setPending(a)}
                  disabled={triage.isPending}
                >
                  {ACTION_LABEL[a].button}
                </Button>
              ))}
              <Button size="sm" variant="ghost" disabled title="Needs a fresh sandbox (slice 2b)">
                Request reproduction
              </Button>
            </div>
            <p className="mt-1.5 text-2xs text-muted">
              Request reproduction: needs a fresh sandbox (slice 2b).
            </p>
          </section>

          <section aria-label="Patch proposals" className="rounded-md border border-line p-3">
            <SectionTitle>Patch proposals</SectionTitle>
            <p className="mt-1 text-xs text-muted">
              Patch proposals are not available: they need repository source and a sandbox (slice
              3d). Nothing is ever applied to a repository without human review.
            </p>
          </section>
        </aside>
      </div>

      <TriageDialog
        action={pending}
        finding={finding}
        duplicateOptions={duplicateOptions}
        busy={triage.isPending}
        onClose={() => setPending(null)}
        onSubmit={run}
      />
    </article>
  );
}

/* ----------------------------------------------------------------- screen */

export function DefectsScreen() {
  const { jobs, items, jobId, job, setJobId } = useJobSelection();
  const [params] = useSearchParams();
  const [filter, setFilter] = useState<StatusFilter>("all");
  const statuses = STATUS_FILTERS.find((f) => f.key === filter)?.statuses;
  const findings = useFindings(jobId || undefined, statuses ? { status: statuses } : {});
  const [evidenceFor, setEvidenceFor] = useState<{ finding: string; id?: string } | null>(null);
  const [open, setOpen] = useState<EvidenceItem | null>(null);
  const evidence = useFindingEvidence(evidenceFor?.finding);
  const rows: Finding[] = Array.isArray(findings.data?.items) ? findings.data.items : [];
  const highlighted = params.get("finding");

  useEffect(() => {
    if (evidenceFor && evidence.data && Array.isArray(evidence.data.items)) {
      const list = evidence.data.items;
      setOpen(
        (evidenceFor.id ? list.find((e) => e.id === evidenceFor.id) : undefined) ?? list[0] ?? null,
      );
    }
  }, [evidenceFor, evidence.data]);

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Findings and fixes" }, { label: screen.navLabel }]}
        title={screen.name}
        subtitle="Findings the Evidence Analysis Agent derived from persisted test executions, ordered by risk priority. Facts are what was observed; inferences and root-cause hypotheses are labelled as such. A single-run finding cannot score as confirmed."
        badge={rows.length ? <Badge tone="info">{rows.length} findings</Badge> : null}
      />
      <div className="card mb-5 flex flex-wrap items-end gap-4 p-4">
        <div className="min-w-[16rem] flex-1">
          <JobSelect items={items} value={jobId} onChange={setJobId} loading={jobs.isLoading} />
        </div>
        <div role="group" aria-label="Status filter" className="flex flex-wrap gap-1.5">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              aria-pressed={filter === f.key}
              onClick={() => setFilter(f.key)}
              className={`rounded-full border px-2.5 py-0.5 text-xs rao-transition ${
                filter === f.key
                  ? "border-accent bg-accent/15 text-accent"
                  : "border-line text-muted hover:text-text"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {!jobId && !jobs.isLoading ? (
        <EmptyState
          title="No jobs yet"
          description="Findings are produced by jobs; create one with API checks to see defects here."
        />
      ) : findings.isLoading || jobs.isLoading ? (
        <SkeletonRows label="Loading findings" />
      ) : findings.isError ? (
        <ErrorState error={findings.error} onRetry={() => findings.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          title={filter === "all" ? "No findings for this job" : "No findings match this filter"}
          description={
            job
              ? filter === "all"
                ? `${job.display_id} has no persisted finding. Either every executed check passed, nothing executed, or the Evidence Analysis task has not run.`
                : `${job.display_id} has no finding with that status.`
              : "No finding has been persisted."
          }
        />
      ) : (
        <div className="space-y-4">
          {rows.map((f) => (
            <div
              key={f.id}
              className={highlighted === f.id ? "rounded-lg ring-2 ring-accent/60" : ""}
            >
              <FindingCard
                finding={f}
                jobId={jobId || undefined}
                onEvidence={(id) => setEvidenceFor({ finding: f.id, id })}
              />
            </div>
          ))}
        </div>
      )}
      <EvidenceDrawer
        evidence={open}
        onClose={() => {
          setOpen(null);
          setEvidenceFor(null);
        }}
      />
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
