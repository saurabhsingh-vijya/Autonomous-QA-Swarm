import { Construction } from "lucide-react";
import { useJobs, useProbe } from "../api/hooks";
import { Badge, EmptyState, KeyValue, LinkButton, PageHeader, Skeleton } from "../components";
import { ScreenFooter } from "../layout/AppShell";
import type { ScreenDef } from "./registry";

const PLACEHOLDER_JOB = "job_00000000000000000000000000";

/**
 * Screens whose backend does not exist in this build. The status is read live from the API
 * (the contract endpoint returns 501 with its planned slice), never hardcoded.
 */
export function NotAvailableScreen({ screen }: { screen: ScreenDef }) {
  const jobs = useJobs({ limit: 1 });
  const jobId = jobs.data?.items[0]?.id ?? PLACEHOLDER_JOB;
  const path = screen.probePath?.replace("{job}", jobId) ?? null;
  const probe = useProbe(jobs.isLoading ? null : path);
  const p = probe.data;

  return (
    <div>
      <PageHeader
        crumbs={[{ label: "Home", to: "/" }, { label: screen.navLabel }]}
        title={screen.name}
        subtitle={screen.purpose}
        badge={
          p?.status === 501 ? (
            <Badge tone="neutral">Planned for slice {p.planned_slice ?? screen.plannedSlice}</Badge>
          ) : screen.plannedSlice ? (
            <Badge tone="neutral">Planned for slice {screen.plannedSlice}</Badge>
          ) : null
        }
      />
      <div className="grid gap-5 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <EmptyState
            icon={Construction}
            title="Not available in this build"
            description={
              p?.status === 501
                ? `${p.detail ?? ""} Nothing is shown here until real data exists.`
                : probe.isLoading || jobs.isLoading
                  ? "Checking the API for this capability."
                  : p
                    ? `The API answered ${p.status} ${p.error_code}: ${p.detail ?? p.title}`
                    : "The API reports this endpoint as implemented; reload to see data."
            }
            action={
              screen.todayPath ? (
                <LinkButton to={screen.todayPath} variant="primary">
                  {screen.todayLabel ?? "Go to jobs"}
                </LinkButton>
              ) : (
                <LinkButton to="/jobs" variant="primary">
                  Follow jobs
                </LinkButton>
              )
            }
          />
        </div>
        <aside className="card p-4" aria-label="Live API status">
          <h2 className="mb-3 text-sm font-semibold text-text">Live API status</h2>
          {probe.isLoading || jobs.isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-4" />
              <Skeleton className="h-4 w-2/3" />
            </div>
          ) : (
            <KeyValue
              items={[
                { label: "Endpoint", value: path ?? "—", mono: true },
                { label: "Status", value: p ? p.status : "200" },
                { label: "Error code", value: p?.error_code ?? "—", mono: true },
                { label: "Planned slice", value: p?.planned_slice ?? screen.plannedSlice ?? "—" },
                { label: "Trace id", value: p?.trace_id ?? "—", mono: true },
              ]}
            />
          )}
          <p className="mt-3 text-xs text-muted">
            Read from the local API on each visit. No fabricated values.
          </p>
        </aside>
      </div>
      <ScreenFooter id={screen.id} name={screen.name} />
    </div>
  );
}
