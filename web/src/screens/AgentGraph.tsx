import { Bot, Cpu, Lock } from "lucide-react";
import { useState } from "react";
import { useJobs, useProbe } from "../api/hooks";
import { Badge, DataTable, KeyValue, PageHeader, Select } from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { AGENTS, AGENT_KIND_LABEL, type AgentDef } from "../lib/agents";
import { screenById } from "./registry";

const screen = screenById("SCR-05");
const PLACEHOLDER_JOB = "job_00000000000000000000000000";

function KindBadge({ kind }: { kind: AgentDef["kind"] }) {
  const Icon = kind === "llm" ? Bot : Cpu;
  const tone = kind === "deterministic" ? "info" : kind === "llm" ? "violet" : "accent";
  return (
    <Badge tone={tone}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {AGENT_KIND_LABEL[kind]}
    </Badge>
  );
}

export function AgentGraphScreen() {
  const jobs = useJobs({ limit: 50 });
  const [jobId, setJobId] = useState("");
  const effective = jobId || jobs.data?.items[0]?.id || PLACEHOLDER_JOB;
  const plan = useProbe(jobs.isLoading ? null : `/jobs/${effective}/plan`);
  const p = plan.data;
  const selected = jobs.data?.items.find((j) => j.id === effective);

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Execution" }, { label: "Agents" }]}
        title="Agent Collaboration Graph"
        badge={<Badge tone="warn">No agents run in this build</Badge>}
        subtitle="The eleven agents the platform defines, with their kind, stage and permission set from the design. Live handoffs, retries and the plan DAG appear only once planning exists (slice 2c) and only when those events actually happen."
      />

      <div className="mb-5 grid gap-5 lg:grid-cols-3">
        <section className="card p-4 lg:col-span-2" aria-labelledby="plan-heading">
          <h2 id="plan-heading" className="text-sm font-semibold text-text">
            Job plan
          </h2>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            <Select
              id="plan-job"
              label="Job"
              value={jobId}
              onChange={(e) => setJobId(e.target.value)}
              disabled={jobs.isLoading || (jobs.data?.items.length ?? 0) === 0}
              hint={
                (jobs.data?.items.length ?? 0) === 0 && !jobs.isLoading
                  ? "No jobs exist yet."
                  : undefined
              }
            >
              {(jobs.data?.items ?? []).map((j) => (
                <option key={j.id} value={j.id}>
                  {j.display_id} ({j.state.replace(/_/g, " ")})
                </option>
              ))}
            </Select>
            <KeyValue
              items={[
                { label: "Selected", value: selected?.display_id ?? "—", mono: true },
                { label: "GET /jobs/{id}/plan", value: p ? `${p.status} ${p.error_code}` : "—" },
                { label: "Planned slice", value: p?.planned_slice ?? "2c" },
              ]}
            />
          </div>
          <p className="mt-3 text-xs text-muted">
            {p?.status === 501
              ? p.detail
              : "The plan endpoint is probed on every visit; its answer is shown verbatim."}
          </p>
        </section>
        <aside className="card p-4" aria-label="Always denied">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-text">
            <Lock className="h-4 w-4 text-muted" aria-hidden="true" /> Denied to every agent
          </h2>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            <li>Access to secrets</li>
            <li>Network egress (only the Model Gateway, when configured)</li>
            <li>Approving anything (HA-01 to HA-12 are human)</li>
            <li>Executing code or changing a repository</li>
          </ul>
          <p className="mt-3 text-xs text-muted">
            External AI providers are disabled; LLM-assisted agents will use local models only.
          </p>
        </aside>
      </div>

      <section className="card" aria-labelledby="registry-heading">
        <div className="border-b border-line px-3.5 py-2.5">
          <h2 id="registry-heading" className="text-sm font-semibold text-text">
            Registry
            <span className="ml-2 text-xs font-normal text-muted">
              {AGENTS.length} agents defined, 0 running
            </span>
          </h2>
        </div>
        <DataTable<AgentDef>
          caption="Agent registry"
          rows={AGENTS}
          rowKey={(a) => a.id}
          columns={[
            {
              key: "id",
              header: "Agent",
              sortValue: (a) => a.id,
              render: (a) => (
                <div>
                  <span className="mono text-muted">{a.id}</span>{" "}
                  <span className="font-medium text-text">{a.name}</span>
                </div>
              ),
            },
            {
              key: "kind",
              header: "Kind",
              sortValue: (a) => a.kind,
              render: (a) => <KindBadge kind={a.kind} />,
            },
            {
              key: "stage",
              header: "Stage",
              render: (a) => <span className="text-muted">{a.stage}</span>,
            },
            {
              key: "slice",
              header: "Arrives in",
              sortValue: (a) => a.plannedSlice,
              render: (a) => <span className="tabular-nums">slice {a.plannedSlice}</span>,
            },
            {
              key: "status",
              header: "Status",
              render: () => <Badge tone="neutral">not running</Badge>,
            },
          ]}
          renderExpanded={(a) => (
            <div className="grid gap-4 md:grid-cols-2">
              <p className="text-sm text-text">{a.purpose}</p>
              <KeyValue
                columns={1}
                items={[
                  { label: "Read source snapshot", value: a.permissions.readSnapshot },
                  { label: "Propose execution tasks", value: a.permissions.proposeTasks },
                  { label: "Call Model Gateway", value: a.permissions.modelGateway },
                  { label: "Read evidence", value: a.permissions.readEvidence },
                  { label: "Write findings", value: a.permissions.writeFindings },
                  { label: "Propose patch", value: a.permissions.proposePatch },
                ]}
              />
            </div>
          )}
        />
      </section>
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
