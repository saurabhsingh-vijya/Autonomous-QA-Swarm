import { Bot, Cpu, Lock } from "lucide-react";
import { useAgents, usePlan, useTasks } from "../api/hooks";
import type { AgentCatalogueEntry, TaskRecord } from "../api/types";
import {
  Badge,
  DataTable,
  EmptyState,
  ErrorState,
  KeyValue,
  PageHeader,
  SkeletonRows,
  StatusBadge,
} from "../components";
import { JobSelect } from "../components/JobSelect";
import { PlanDag } from "../components/PlanDag";
import { ScreenFooter } from "../layout/AppShell";
import { AGENTS } from "../lib/agents";
import { useJobSelection } from "../lib/useJobSelection";
import { screenById } from "./registry";

const screen = screenById("SCR-05");

const KIND_LABEL: Record<string, string> = {
  deterministic: "Deterministic",
  llm_assisted: "LLM-assisted (local model)",
  deterministic_with_llm: "Deterministic, LLM optional",
};

function KindBadge({ kind }: { kind: string }) {
  const Icon = kind === "deterministic" ? Cpu : Bot;
  const tone = kind === "deterministic" ? "info" : kind === "llm_assisted" ? "violet" : "accent";
  return (
    <Badge tone={tone}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {KIND_LABEL[kind] ?? kind}
    </Badge>
  );
}

export function AgentGraphScreen() {
  const agents = useAgents();
  const { jobs, items, jobId, job, setJobId } = useJobSelection();
  const plan = usePlan(jobId || undefined);
  const tasks = useTasks(jobId || undefined);
  const catalogue: AgentCatalogueEntry[] = Array.isArray(agents.data?.items)
    ? agents.data.items
    : [];
  const taskRows: TaskRecord[] = Array.isArray(tasks.data?.items) ? tasks.data.items : [];
  const implemented = catalogue.filter((a) => a.implemented).length;
  const provider = agents.data?.llm_provider;
  const activeAgents = new Set(
    taskRows.filter((t) => t.state === "leased" || t.state === "running").map((t) => t.agent_id),
  );
  const designById = new Map(AGENTS.map((a) => [a.id, a]));

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Execution" }, { label: "Agents" }]}
        title="Agent Collaboration Graph"
        badge={
          agents.data ? (
            <Badge tone={provider && provider !== "none" ? "violet" : "info"}>
              {`LLM provider: ${provider ?? "unknown"}${
                provider === "none" ? " (deterministic adapters only)" : ""
              }`}
            </Badge>
          ) : null
        }
        subtitle="The agent registry as the API reports it, and the plan graph of one job coloured by its persisted task states. Nothing here is simulated: a node is only marked running or done when a task record says so."
      />

      <div className="mb-5 grid gap-5 lg:grid-cols-3">
        <section className="card p-4 lg:col-span-2" aria-labelledby="plan-heading">
          <h2 id="plan-heading" className="text-sm font-semibold text-text">
            Job plan
          </h2>
          <div className="mt-3">
            <JobSelect items={items} value={jobId} onChange={setJobId} loading={jobs.isLoading} />
          </div>
          <div className="mt-4">
            {!jobId ? (
              <EmptyState
                compact
                title="No job to show"
                description="Create a job with requirements or API checks to see its plan here."
              />
            ) : plan.isLoading || tasks.isLoading ? (
              <SkeletonRows rows={3} label="Loading plan" />
            ) : plan.isError ? (
              <ErrorState error={plan.error} onRetry={() => plan.refetch()} />
            ) : !plan.data ? (
              <EmptyState
                compact
                title="This job has no plan"
                description={
                  job?.held_reason
                    ? `${job.display_id} is held: ${job.held_reason}. No plan was built.`
                    : "No plan has been persisted for this job."
                }
              />
            ) : (
              <>
                <div className="mb-3 flex flex-wrap items-center gap-2 text-xs text-muted">
                  <span>
                    {plan.data.nodes.length} nodes · revision {plan.data.revision} ·{" "}
                    {plan.data.planner}
                  </span>
                  <span>
                    {taskRows.filter((t) => t.state === "succeeded").length} of {taskRows.length}{" "}
                    tasks succeeded
                  </span>
                  {job ? <StatusBadge state={job.state} /> : null}
                </div>
                <PlanDag nodes={plan.data.nodes} tasks={taskRows} />
              </>
            )}
          </div>
        </section>
        <aside className="card p-4" aria-label="Always denied">
          <h2 className="flex items-center gap-2 text-sm font-semibold text-text">
            <Lock className="h-4 w-4 text-muted" aria-hidden="true" /> Denied to every agent
          </h2>
          <ul className="mt-2 space-y-1 text-sm text-muted">
            <li>Access to secrets (evidence is redacted before storage)</li>
            <li>Network egress beyond read-only requests to localhost</li>
            <li>Approving anything (HA-01 to HA-12 are human)</li>
            <li>Executing repository code or changing a repository</li>
          </ul>
          <p className="mt-3 text-xs text-muted">
            {agents.data?.note ??
              "External AI providers are disabled; LLM-assisted agents use local models only."}
          </p>
        </aside>
      </div>

      <section className="card" aria-labelledby="registry-heading">
        <div className="border-b border-line px-3.5 py-2.5">
          <h2 id="registry-heading" className="text-sm font-semibold text-text">
            Registry
            {agents.data ? (
              <span className="ml-2 text-xs font-normal text-muted">
                {catalogue.length} agents defined, {implemented} implemented, {activeAgents.size}{" "}
                running for the selected job
              </span>
            ) : null}
          </h2>
        </div>
        {agents.isLoading ? <SkeletonRows label="Loading agents" /> : null}
        {agents.isError ? (
          <ErrorState error={agents.error} onRetry={() => agents.refetch()} />
        ) : null}
        {agents.data ? (
          <DataTable<AgentCatalogueEntry>
            caption="Agent registry"
            rows={catalogue}
            rowKey={(a) => a.agent_id}
            emptyLabel="The API returned no agents."
            columns={[
              {
                key: "id",
                header: "Agent",
                sortValue: (a) => a.agent_id,
                render: (a) => (
                  <div>
                    <span className="mono text-muted">{a.agent_id}</span>{" "}
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
                key: "adapter",
                header: "Adapter",
                render: (a) =>
                  a.implemented ? (
                    <span className="mono text-xs">{a.adapter ?? "—"}</span>
                  ) : (
                    <span className="text-xs text-muted">
                      not implemented{a.planned_slice ? ` · slice ${a.planned_slice}` : ""}
                    </span>
                  ),
              },
              {
                key: "status",
                header: "Status",
                render: (a) =>
                  activeAgents.has(a.agent_id) ? (
                    <StatusBadge state="running" />
                  ) : a.implemented ? (
                    <Badge tone="neutral">idle</Badge>
                  ) : (
                    <Badge tone="neutral">not available</Badge>
                  ),
              },
            ]}
            renderExpanded={(a) => {
              const d = designById.get(a.agent_id);
              return (
                <div className="grid gap-4 md:grid-cols-2">
                  <div className="text-sm text-text">
                    <p>{d?.purpose ?? "No design note."}</p>
                    <p className="mono mt-2 text-xs text-muted">
                      task types: {a.task_types.length ? a.task_types.join(", ") : "none"}
                    </p>
                  </div>
                  {d ? (
                    <KeyValue
                      columns={1}
                      items={[
                        { label: "Read source snapshot", value: d.permissions.readSnapshot },
                        { label: "Propose execution tasks", value: d.permissions.proposeTasks },
                        { label: "Call Model Gateway", value: d.permissions.modelGateway },
                        { label: "Read evidence", value: d.permissions.readEvidence },
                        { label: "Write findings", value: d.permissions.writeFindings },
                        { label: "Propose patch", value: d.permissions.proposePatch },
                      ]}
                    />
                  ) : null}
                </div>
              );
            }}
          />
        ) : null}
      </section>
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
