import { AlertTriangle, Bell, Hexagon, Search } from "lucide-react";
import { NavLink, Outlet } from "react-router-dom";
import { useProjects } from "../api/hooks";
import { NAV_GROUPS, SCREENS } from "../screens/registry";

export const CONCEPT_PILL = "Concept build — no repository code executed";

function Sidebar() {
  return (
    <aside className="flex w-[272px] shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex items-center gap-3 px-5 py-5">
        <div className="flex h-10 w-10 items-center justify-center rounded-xl bg-primary text-white">
          <Hexagon className="h-5 w-5" aria-hidden="true" />
        </div>
        <div>
          <div className="text-sm font-semibold leading-tight text-slate-900">
            Autonomous QA Swarm
          </div>
          <div className="text-xs text-slate-500">v0.1 · Concept / Phase 1a</div>
        </div>
      </div>
      <nav aria-label="Primary" className="flex-1 overflow-y-auto px-3 pb-4">
        {NAV_GROUPS.map((g) => (
          <div key={g} className="mb-4">
            <div className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wider text-slate-400">
              {g}
            </div>
            <ul className="space-y-0.5">
              {SCREENS.filter((s) => s.group === g).map((s) => (
                <li key={s.id}>
                  <NavLink
                    to={s.path}
                    end={s.path === "/" || s.path === "/jobs"}
                    className={({ isActive }) =>
                      `flex items-center gap-3 rounded-lg px-3 py-2 text-sm ${
                        isActive
                          ? "bg-primary-light font-medium text-primary"
                          : "text-slate-700 hover:bg-slate-50"
                      }`
                    }
                  >
                    <s.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                    <span className="truncate">{s.navLabel}</span>
                    {s.plannedSlice ? (
                      <span className="ml-auto rounded bg-slate-100 px-1.5 text-[10px] text-slate-500">
                        {s.plannedSlice}
                      </span>
                    ) : null}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        ))}
      </nav>
      <div className="border-t border-slate-200 px-5 py-4 text-xs text-slate-500">
        <div className="font-medium text-slate-800">Phase 1a · Boilerplate</div>
        <div>Policy Engine: not yet wired (slice 2c)</div>
      </div>
    </aside>
  );
}

function TopBar() {
  const projects = useProjects();
  const first = projects.data?.items[0];
  const orgName = first?.org_name ?? (projects.isLoading ? "Loading…" : "No organisation");
  const projectName = first?.name ?? "—";
  return (
    <div className="flex items-center gap-4 border-b border-slate-200 bg-white px-6 py-3">
      <div className="flex items-center gap-2 rounded-lg border border-slate-200 px-3 py-1.5 text-sm">
        <span className="flex h-6 w-6 items-center justify-center rounded bg-emerald-100 text-[10px] font-bold text-emerald-800">
          {orgName.slice(0, 2).toUpperCase()}
        </span>
        <span className="text-slate-700">{orgName}</span>
        <span className="text-slate-300">/</span>
        <span className="font-medium text-slate-900">{projectName}</span>
      </div>
      <label className="relative hidden flex-1 md:block">
        <span className="sr-only">Search</span>
        <Search
          className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400"
          aria-hidden="true"
        />
        <input
          type="search"
          disabled
          title="Search arrives in slice 1d"
          placeholder="Search jobs, findings, tests… (slice 1d)"
          className="input max-w-md pl-9 disabled:bg-slate-50"
        />
      </label>
      <span
        className="ml-auto inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-semibold"
        style={{ background: "#FEF3C7", borderColor: "#D97706", color: "#92400E" }}
      >
        <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
        {CONCEPT_PILL}
      </span>
      <button
        type="button"
        className="rounded-lg border border-slate-200 p-2 text-slate-500"
        aria-label="Notifications (not implemented in this phase)"
        disabled
      >
        <Bell className="h-4 w-4" aria-hidden="true" />
      </button>
      <span className="inline-flex items-center gap-2 text-sm text-slate-800">
        <span className="flex h-7 w-7 items-center justify-center rounded-full bg-sky-100 text-xs font-semibold text-sky-800">
          DV
        </span>
        Dev · QA Lead
      </span>
    </div>
  );
}

export function AppShell() {
  return (
    <div className="flex min-h-screen">
      <Sidebar />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar />
        <main className="flex-1 px-6 py-6">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

export function ScreenFooter({ id, name }: { id: string; name: string }) {
  return (
    <footer className="mt-10 flex items-center justify-between border-t border-slate-200 pt-3 text-xs text-slate-500">
      <span>
        <span className="font-semibold text-slate-700">{id}</span> · {name} · Phase 1a
      </span>
      <span>Proposed UI — only slice 1a behaviour is implemented</span>
    </footer>
  );
}
