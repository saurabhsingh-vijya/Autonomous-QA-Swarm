import {
  AlertTriangle,
  ChevronLeft,
  ChevronRight,
  Command,
  Database,
  Hexagon,
  Menu,
  Moon,
  Sun,
  X,
} from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useCapabilities } from "../api/hooks";
import { capabilityPill } from "../lib/capabilities";
import { useProjectContext } from "../app/ProjectContext";
import { useGlobalShortcuts } from "../app/shortcuts";
import { CommandPalette } from "../components/CommandPalette";
import { ShortcutsDialog } from "../components/ShortcutsDialog";
import { Kbd } from "../components/ui/Kbd";
import { Tooltip } from "../components/ui/Tooltip";
import { NAV_GROUPS, SCREENS } from "../screens/registry";
import { PREF_KEYS, readPref, writePref } from "../theme/prefs";
import { useTheme } from "../theme/ThemeProvider";

export const CONCEPT_PILL = "Concept build — no repository code executed";
function ModePill() {
  const caps = useCapabilities();
  const text = capabilityPill(caps.data);
  const unsandboxed = Boolean(caps.data?.repository_code_execution_allowed);
  const on = Boolean(caps.data?.execution_enabled);
  const tone = unsandboxed
    ? "border-danger/50 bg-danger/15 text-danger"
    : on
      ? "border-ok/50 bg-ok/15 text-ok"
      : "border-warn/50 bg-warn/15 text-warn";
  return (
    <Tooltip
      content={
        on
          ? "Repository checks run on an Execution Service host that leases tasks from the control plane. The control plane itself never executes repository code."
          : "No Execution Service is configured (AQS_EXEC_TOKEN unset): jobs run their agent tasks on supplied inputs only and repository checks are not planned."
      }
    >
      <span
        className={`inline-flex h-7 cursor-default items-center gap-1.5 rounded-md border px-2 text-xs font-medium ${tone}`}
        tabIndex={0}
        data-testid="mode-pill"
      >
        <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" />
        <span className="hidden md:inline">{text}</span>
        <span className="md:hidden">{on ? "Execution on" : "Execution off"}</span>
      </span>
    </Tooltip>
  );
}

function Sidebar({
  collapsed,
  onToggle,
  mobileOpen,
  onCloseMobile,
}: {
  collapsed: boolean;
  onToggle: () => void;
  mobileOpen: boolean;
  onCloseMobile: () => void;
}) {
  const width = collapsed ? "lg:w-14" : "lg:w-[248px]";
  return (
    <>
      {mobileOpen ? (
        <button
          type="button"
          aria-label="Close navigation"
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={onCloseMobile}
        />
      ) : null}
      <aside
        className={`fixed inset-y-0 left-0 z-40 flex w-[248px] shrink-0 flex-col border-r border-line bg-surface rao-transition lg:static lg:translate-x-0 ${width} ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        aria-label="Sidebar"
      >
        <div className="flex h-12 items-center gap-2.5 border-b border-line px-3">
          <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-accent text-accent-fg">
            <Hexagon className="h-4 w-4" aria-hidden="true" />
          </span>
          {!collapsed ? (
            <span className="min-w-0 leading-tight">
              <span className="block truncate text-sm font-semibold text-text">RaOne</span>
              <span className="block truncate text-2xs text-muted">Autonomous AI-powered QA</span>
            </span>
          ) : null}
          <button
            type="button"
            onClick={onCloseMobile}
            className="ml-auto rounded p-1 text-muted hover:text-text lg:hidden"
            aria-label="Close navigation"
          >
            <X className="h-4 w-4" aria-hidden="true" />
          </button>
        </div>
        <nav aria-label="Primary" className="flex-1 overflow-y-auto px-2 py-2">
          {NAV_GROUPS.map((g) => (
            <div key={g} className="mb-3">
              {!collapsed ? (
                <div className="px-2 pb-1 pt-1 text-2xs font-medium text-muted">{g}</div>
              ) : (
                <div className="mx-2 my-2 border-t border-line" aria-hidden="true" />
              )}
              <ul className="space-y-px">
                {SCREENS.filter((s) => s.group === g).map((s) => (
                  <li key={s.id}>
                    <NavLink
                      to={s.path}
                      end={s.path === "/" || s.path === "/jobs"}
                      onClick={onCloseMobile}
                      title={collapsed ? s.navLabel : undefined}
                      className={({ isActive }) =>
                        `flex h-8 items-center gap-2.5 rounded-md px-2 text-sm rao-transition ${
                          isActive
                            ? "bg-accent/15 font-medium text-text"
                            : "text-muted hover:bg-raised hover:text-text"
                        } ${collapsed ? "justify-center" : ""}`
                      }
                    >
                      <s.icon className="h-4 w-4 shrink-0" aria-hidden="true" />
                      {!collapsed ? (
                        <>
                          <span className="truncate">{s.navLabel}</span>
                          {s.plannedSlice ? (
                            <span
                              className="ml-auto rounded border border-line px-1 text-2xs text-muted"
                              aria-label={`planned in slice ${s.plannedSlice}`}
                            >
                              {s.plannedSlice}
                            </span>
                          ) : null}
                        </>
                      ) : (
                        <span className="sr-only">{s.navLabel}</span>
                      )}
                    </NavLink>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </nav>
        <div className="hidden border-t border-line p-2 lg:block">
          <button
            type="button"
            onClick={onToggle}
            className="flex h-8 w-full items-center justify-center gap-2 rounded-md text-xs text-muted hover:bg-raised hover:text-text"
            aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
            aria-pressed={collapsed}
          >
            {collapsed ? (
              <ChevronRight className="h-4 w-4" aria-hidden="true" />
            ) : (
              <>
                <ChevronLeft className="h-4 w-4" aria-hidden="true" /> Collapse
              </>
            )}
          </button>
        </div>
      </aside>
    </>
  );
}

function RuntimeChip() {
  const caps = useCapabilities();
  const dbOk = caps.data?.database?.available;
  const label = caps.isLoading
    ? "Checking runtime"
    : caps.isError
      ? "API unreachable"
      : dbOk
        ? "Local · DB ok"
        : "DB unreachable";
  const tone = caps.isLoading
    ? "text-muted border-line"
    : caps.isError || !dbOk
      ? "text-danger border-danger/40"
      : "text-ok border-ok/40";
  return (
    <Tooltip
      content={
        caps.data
          ? `RaOne ${caps.data.version}. Local only, telemetry ${caps.data.telemetry_export}, external AI providers ${caps.data.external_ai_providers}. Database ${caps.data.database?.status ?? "unknown"}.`
          : "Runtime status from GET /api/v1/system/capabilities"
      }
    >
      <a
        href="/settings"
        onClick={(e) => e.preventDefault()}
        className={`hidden h-7 items-center gap-1.5 rounded-md border px-2 text-xs md:inline-flex ${tone}`}
        aria-label={`Runtime status: ${label}`}
      >
        <Database className="h-3.5 w-3.5" aria-hidden="true" />
        {label}
      </a>
    </Tooltip>
  );
}

function ProjectSwitcher() {
  const { projectId, projects, setProjectId, isLoading } = useProjectContext();
  const orgName = projects[0]?.org_name;
  return (
    <label className="flex min-w-0 items-center gap-2 text-sm">
      <span className="sr-only">Project context</span>
      {orgName ? (
        <span className="hidden max-w-[180px] truncate text-muted md:inline" title={orgName}>
          {orgName}
        </span>
      ) : null}
      <select
        className="input h-7 w-auto max-w-[200px] py-0 pr-7 text-sm"
        value={projectId ?? ""}
        onChange={(e) => setProjectId(e.target.value || undefined)}
        disabled={isLoading}
        aria-label="Project context"
      >
        <option value="">All projects</option>
        {projects.map((p) => (
          <option key={p.id} value={p.id}>
            {p.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function TopBar({
  onOpenPalette,
  onOpenMenu,
}: {
  onOpenPalette: () => void;
  onOpenMenu: () => void;
}) {
  const { theme, toggleTheme } = useTheme();
  return (
    <header className="sticky top-0 z-20 flex h-12 items-center gap-2 border-b border-line bg-surface/95 px-3 backdrop-blur md:px-4">
      <button
        type="button"
        onClick={onOpenMenu}
        className="rounded-md p-1.5 text-muted hover:bg-raised hover:text-text lg:hidden"
        aria-label="Open navigation"
      >
        <Menu className="h-4 w-4" aria-hidden="true" />
      </button>
      <ProjectSwitcher />
      <button
        type="button"
        onClick={onOpenPalette}
        className="ml-auto hidden h-7 items-center gap-2 rounded-md border border-line bg-canvas px-2 text-xs text-muted hover:border-line-strong hover:text-text sm:inline-flex"
        aria-label="Open command palette"
      >
        <Command className="h-3.5 w-3.5" aria-hidden="true" />
        <span>Search or jump to</span>
        <Kbd>Ctrl</Kbd>
        <Kbd>K</Kbd>
      </button>
      <ModePill />
      <RuntimeChip />
      <button
        type="button"
        onClick={toggleTheme}
        className="rounded-md border border-line p-1.5 text-muted hover:text-text"
        aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
        aria-pressed={theme === "light"}
      >
        {theme === "dark" ? (
          <Sun className="h-4 w-4" aria-hidden="true" />
        ) : (
          <Moon className="h-4 w-4" aria-hidden="true" />
        )}
      </button>
      <span
        className="hidden items-center gap-1.5 text-xs text-text sm:inline-flex"
        title="Dev-only header authentication; OIDC arrives in slice 3e"
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-full bg-accent/20 text-2xs font-semibold text-accent">
          DV
        </span>
        Dev · QA Lead
      </span>
    </header>
  );
}

export function AppShell() {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(() => readPref(PREF_KEYS.sidebar) === "collapsed");
  const [mobileOpen, setMobileOpen] = useState(false);
  const [palette, setPalette] = useState(false);
  const [help, setHelp] = useState(false);
  const location = useLocation();

  useEffect(() => {
    setMobileOpen(false);
  }, [location.pathname]);

  const toggleSidebar = useCallback(() => {
    setCollapsed((c) => {
      writePref(PREF_KEYS.sidebar, c ? "expanded" : "collapsed");
      return !c;
    });
  }, []);

  useGlobalShortcuts({
    openPalette: () => setPalette(true),
    openHelp: () => setHelp(true),
    go: (path) => navigate(path),
  });

  return (
    <div className="flex min-h-screen">
      <Sidebar
        collapsed={collapsed}
        onToggle={toggleSidebar}
        mobileOpen={mobileOpen}
        onCloseMobile={() => setMobileOpen(false)}
      />
      <div className="flex min-w-0 flex-1 flex-col">
        <TopBar onOpenPalette={() => setPalette(true)} onOpenMenu={() => setMobileOpen(true)} />
        <main className="mx-auto w-full max-w-page flex-1 px-4 py-5 md:px-6">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
      <ShortcutsDialog open={help} onClose={() => setHelp(false)} />
    </div>
  );
}

export function ScreenFooter({ id, name }: { id: string; name: string }) {
  return (
    <footer className="mt-10 flex flex-wrap items-center justify-between gap-2 border-t border-line pt-3 text-xs text-muted">
      <span>
        <span className="font-medium text-text">{id}</span> {name}, phases 2 · 3 · 5
      </span>
      <span>
        Screens marked with a slice badge are not implemented yet; nothing shown is simulated.
      </span>
    </footer>
  );
}
