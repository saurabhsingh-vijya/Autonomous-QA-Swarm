import { useCapabilities } from "../api/hooks";
import type { Capability } from "../api/types";
import { Badge, DataTable, ErrorState, KeyValue, PageHeader, SkeletonRows } from "../components";
import { ScreenFooter } from "../layout/AppShell";
import { PREF_KEYS, readPref } from "../theme/prefs";
import { useTheme } from "../theme/ThemeProvider";
import { screenById } from "./registry";

const screen = screenById("SCR-15");

function Avail({ c }: { c: Capability }) {
  return c.available ? (
    <Badge tone="ok">available</Badge>
  ) : (
    <Badge tone="neutral">unavailable</Badge>
  );
}

const INTEGRATION_LABEL: Record<string, string> = {
  github: "GitHub",
  gitlab: "GitLab",
  jenkins: "Jenkins",
  github_actions: "GitHub Actions",
  slack: "Slack",
  teams: "Microsoft Teams",
};

const LIMIT_LABEL: Record<string, string> = {
  job_wall_clock_seconds: "Job wall clock",
  task_wall_clock_seconds: "Task wall clock",
  lease_ttl_seconds: "Task lease",
  heartbeat_seconds: "Heartbeat interval",
  task_max_retries: "Max retries per task",
};

function seconds(n: number): string {
  if (n % 3600 === 0) return `${n / 3600} h`;
  if (n % 60 === 0) return `${n / 60} min`;
  return `${n} s`;
}

export function SettingsScreen() {
  const caps = useCapabilities();
  const { theme } = useTheme();
  const c = caps.data;
  const sidebar = readPref(PREF_KEYS.sidebar) === "collapsed" ? "Collapsed" : "Expanded";

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Governance" }, { label: "Settings" }]}
        title="Settings & Integrations"
        badge={<Badge tone="neutral">read-only</Badge>}
        subtitle="What this local runtime can do right now, read from the API. Editing limits, permissions and integrations arrives in slice 3e. Secrets are never shown."
      />
      {caps.isLoading ? <SkeletonRows rows={6} label="Loading capabilities" /> : null}
      {caps.isError ? <ErrorState error={caps.error} onRetry={() => caps.refetch()} /> : null}
      {c ? (
        <div className="grid gap-5 lg:grid-cols-2">
          <section className="card p-4" aria-labelledby="runtime-heading">
            <h2 id="runtime-heading" className="mb-3 text-sm font-semibold text-text">
              Runtime
            </h2>
            <KeyValue
              items={[
                { label: "Product", value: `${c.product} ${c.version}` },
                { label: "Local only", value: c.local_only ? "Yes" : "No" },
                { label: "Telemetry export", value: c.telemetry_export },
                { label: "External AI providers", value: c.external_ai_providers },
                { label: "Authentication", value: c.auth_mode },
                ...(c.phase ? [{ label: "Phase", value: c.phase }] : []),
                ...(c.llm_provider ? [{ label: "LLM provider", value: c.llm_provider }] : []),
              ]}
            />
          </section>
          <section className="card p-4" aria-labelledby="exec-heading">
            <h2 id="exec-heading" className="mb-3 text-sm font-semibold text-text">
              Execution
            </h2>
            <KeyValue
              items={[
                {
                  label: "Execution Service",
                  value: c.execution_enabled ? (
                    <Badge tone="ok">enabled</Badge>
                  ) : (
                    <Badge tone="neutral">disabled (AQS_EXEC_TOKEN unset)</Badge>
                  ),
                },
                { label: "Runtime", value: c.sandbox ?? "—" },
                {
                  label: "Repository code may run",
                  value: c.repository_code_execution_allowed ? (
                    <Badge tone="danger">yes — unsandboxed (dev only)</Badge>
                  ) : (
                    <Badge tone="ok">no</Badge>
                  ),
                },
                { label: "Check engines", value: (c.engines ?? []).join(", ") || "—" },
                {
                  label: "Agent runner in API",
                  value: c.agent_runner_enabled ? "yes" : "no",
                },
                { label: "Embedded scheduler", value: c.embedded_scheduler ? "yes" : "no" },
                { label: "Embedded exec worker", value: c.embedded_exec_worker ? "yes" : "no" },
                { label: "Dev fixture repositories", value: c.dev_fixture_repos ? "yes" : "no" },
              ]}
            />
            <p className="mt-3 text-xs text-muted">
              Without an Execution Service, jobs run their agent tasks on supplied inputs only and
              repository checks are not planned.
            </p>
          </section>
          <section className="card p-4" aria-labelledby="storage-heading">
            <h2 id="storage-heading" className="mb-3 text-sm font-semibold text-text">
              Database and storage
            </h2>
            <KeyValue
              items={[
                {
                  label: "Database",
                  value: (
                    <span className="inline-flex items-center gap-2">
                      <Avail c={c.database} /> {c.database.status}
                    </span>
                  ),
                },
                { label: "Driver", value: c.storage.driver, mono: true },
                { label: "Host", value: `${c.storage.host}:${c.storage.port}`, mono: true },
                { label: "Database name", value: c.storage.database, mono: true },
                {
                  label: "Evidence store",
                  value: (
                    <span className="inline-flex items-center gap-2">
                      <Avail c={c.evidence_store} />{" "}
                      {c.evidence_store.planned_slice
                        ? `slice ${c.evidence_store.planned_slice}`
                        : c.evidence_store.status}
                    </span>
                  ),
                },
              ]}
            />
            <p className="mt-3 text-xs text-muted">
              Credentials come from the environment and are never returned.
            </p>
          </section>

          <section className="card lg:col-span-2" aria-labelledby="caps-heading">
            <div className="border-b border-line px-3.5 py-2.5">
              <h2 id="caps-heading" className="text-sm font-semibold text-text">
                Capabilities
              </h2>
            </div>
            <DataTable
              caption="Capabilities"
              rowKey={(r) => r.name}
              rows={[
                { name: "Execution service (sandbox workers)", cap: c.execution_service },
                { name: "Evidence store", cap: c.evidence_store },
                { name: "Model gateway (local models)", cap: c.model_gateway },
                {
                  name: "Test engines",
                  cap: {
                    available: c.test_engines.length > 0,
                    status:
                      c.test_engines.length > 0 ? c.test_engines.join(", ") : "none registered",
                    planned_slice: null,
                  },
                },
              ]}
              columns={[
                { key: "name", header: "Capability", render: (r) => r.name },
                { key: "avail", header: "State", render: (r) => <Avail c={r.cap} /> },
                {
                  key: "status",
                  header: "Detail",
                  render: (r) => <span className="text-muted">{r.cap.status}</span>,
                },
                {
                  key: "slice",
                  header: "Arrives in",
                  render: (r) => (r.cap.planned_slice ? `slice ${r.cap.planned_slice}` : "—"),
                },
              ]}
            />
          </section>

          <section className="card" aria-labelledby="int-heading">
            <div className="border-b border-line px-3.5 py-2.5">
              <h2 id="int-heading" className="text-sm font-semibold text-text">
                Integrations
              </h2>
            </div>
            <DataTable
              caption="Integrations"
              rowKey={(r) => r.key}
              rows={Object.entries(c.integrations).map(([key, cap]) => ({ key, cap }))}
              columns={[
                {
                  key: "name",
                  header: "Integration",
                  render: (r) => INTEGRATION_LABEL[r.key] ?? r.key,
                },
                {
                  key: "state",
                  header: "State",
                  render: (r) =>
                    r.cap.available ? (
                      <Badge tone="ok">connected</Badge>
                    ) : (
                      <Badge tone="neutral">not connected</Badge>
                    ),
                },
                {
                  key: "slice",
                  header: "Arrives in",
                  render: (r) => (r.cap.planned_slice ? `slice ${r.cap.planned_slice}` : "—"),
                },
              ]}
            />
          </section>

          <section className="card p-4" aria-labelledby="limits-heading">
            <h2 id="limits-heading" className="mb-3 text-sm font-semibold text-text">
              Execution limits
            </h2>
            <KeyValue
              items={Object.entries(c.limits).map(([k, v]) => ({
                label: LIMIT_LABEL[k] ?? k,
                value: k.endsWith("_seconds") ? seconds(v) : v,
              }))}
            />
            <p className="mt-3 text-xs text-muted">
              Defaults from the design; editable in slice 3e.
            </p>
          </section>

          <section className="card p-4 lg:col-span-2" aria-labelledby="prefs-heading">
            <h2 id="prefs-heading" className="mb-3 text-sm font-semibold text-text">
              This browser
            </h2>
            <KeyValue
              columns={2}
              items={[
                { label: "Theme", value: theme === "dark" ? "Dark" : "Light" },
                { label: "Sidebar", value: sidebar },
              ]}
            />
            <p className="mt-3 text-xs text-muted">
              Stored only in this browser. Use the top bar to change the theme or the sidebar.
            </p>
          </section>
        </div>
      ) : null}
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
