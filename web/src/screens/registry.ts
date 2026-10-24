import type { LucideIcon } from "lucide-react";
import {
  Activity,
  BookOpen,
  Braces,
  Bug,
  CheckCircle2,
  FileText,
  Gauge,
  GitPullRequest,
  LayoutGrid,
  PlusCircle,
  Settings,
  Share2,
  Shield,
  Shuffle,
  SquareCheck,
} from "lucide-react";

export type NavGroup = "Overview" | "Execution" | "Results" | "Findings and fixes" | "Governance";

export interface ScreenDef {
  id: string;
  name: string;
  navLabel: string;
  path: string;
  group: NavGroup;
  icon: LucideIcon;
  purpose: string;
  /** Slice that delivers the screen's data. Undefined = implemented in this build. */
  plannedSlice?: string;
  /** Contract endpoint probed to show the live 501 status; `{job}` is replaced by a job id. */
  probePath?: string;
  /** What the person can do today instead. */
  todayPath?: string;
  todayLabel?: string;
}

export const SCREENS: ScreenDef[] = [
  {
    id: "SCR-01",
    name: "Dashboard — QA Health Overview",
    navLabel: "Dashboard",
    path: "/",
    group: "Overview",
    icon: LayoutGrid,
    purpose: "Give a one-page view of quality across projects, as the landing screen after login.",
  },
  {
    id: "SCR-02",
    name: "Repositories & Projects",
    navLabel: "Repositories",
    path: "/repositories",
    group: "Overview",
    icon: BookOpen,
    purpose: "Manage projects and the repositories registered to them.",
  },
  {
    id: "SCR-03",
    name: "New QA Job Wizard",
    navLabel: "New QA job",
    path: "/jobs/new",
    group: "Overview",
    icon: PlusCircle,
    purpose: "Configure and launch a QA job with explicit scope, profiles, targets and limits.",
  },
  {
    id: "SCR-04",
    name: "Live Job Execution",
    navLabel: "Jobs",
    path: "/jobs",
    group: "Execution",
    icon: Activity,
    purpose: "Follow a running job stage by stage and task by task.",
  },
  {
    id: "SCR-05",
    name: "Agent Collaboration Graph",
    navLabel: "Agents",
    path: "/agent-graph",
    group: "Execution",
    icon: Share2,
    purpose:
      "Show how agents and tasks relate in the job plan, and what each agent received, proposed and produced.",
  },
  {
    id: "SCR-06",
    name: "Functional Test Results",
    navLabel: "Functional tests",
    path: "/results/functional",
    group: "Results",
    icon: SquareCheck,
    purpose: "Present functional test outcomes and failure detail.",
  },
  {
    id: "SCR-07",
    name: "API Test Results",
    navLabel: "API tests",
    path: "/results/api",
    group: "Results",
    icon: Braces,
    purpose:
      "Show API contract and authorization test outcomes with request and response evidence.",
  },
  {
    id: "SCR-08",
    name: "Security Testing Center",
    navLabel: "Security",
    path: "/security",
    group: "Results",
    icon: Shield,
    purpose: "Present security scans and findings for triage.",
    plannedSlice: "2a",
    probePath: "/jobs/{job}/findings",
    todayPath: "/jobs/new",
    todayLabel: "Create a job",
  },
  {
    id: "SCR-09",
    name: "Performance Testing Lab",
    navLabel: "Performance",
    path: "/performance",
    group: "Results",
    icon: Gauge,
    purpose:
      "Configure bounded performance runs and analyze results against thresholds and baseline.",
    plannedSlice: "3b",
    probePath: "/jobs/{job}/performance-runs",
    todayPath: "/jobs/new",
    todayLabel: "Create a job",
  },
  {
    id: "SCR-10",
    name: "Mutation Testing Dashboard",
    navLabel: "Mutation",
    path: "/mutation",
    group: "Results",
    icon: Shuffle,
    purpose: "Show test-suite strength on changed modules.",
    plannedSlice: "3c",
    probePath: "/jobs/{job}/mutation-runs",
    todayPath: "/jobs/new",
    todayLabel: "Create a job",
  },
  {
    id: "SCR-11",
    name: "Defect Evidence & Investigation",
    navLabel: "Defects and evidence",
    path: "/defects",
    group: "Findings and fixes",
    icon: Bug,
    purpose: "Investigate a single finding and record triage decisions.",
  },
  {
    id: "SCR-12",
    name: "Patch Review",
    navLabel: "Patches",
    path: "/patches",
    group: "Findings and fixes",
    icon: GitPullRequest,
    purpose: "Review a proposed patch and decide whether it proceeds to verification.",
    plannedSlice: "3d",
    probePath: "/jobs/{job}/patches",
    todayPath: "/jobs",
    todayLabel: "Follow jobs",
  },
  {
    id: "SCR-13",
    name: "Independent Verification",
    navLabel: "Verification",
    path: "/verification",
    group: "Findings and fixes",
    icon: CheckCircle2,
    purpose: "Show the fresh-sandbox verification result of an approved patch.",
    plannedSlice: "3d",
    probePath: "/verifications/ver_00000000000000000000000000",
    todayPath: "/jobs",
    todayLabel: "Follow jobs",
  },
  {
    id: "SCR-14",
    name: "Reports & Release Readiness",
    navLabel: "Reports",
    path: "/reports",
    group: "Governance",
    icon: FileText,
    purpose:
      "Present gate results, residual risk and the release recommendation, and capture the human decision.",
  },
  {
    id: "SCR-15",
    name: "Settings & Integrations",
    navLabel: "Settings",
    path: "/settings",
    group: "Governance",
    icon: Settings,
    purpose: "Administer the platform's safety limits, permissions, integrations and model access.",
  },
];

export const NAV_GROUPS: NavGroup[] = [
  "Overview",
  "Execution",
  "Results",
  "Findings and fixes",
  "Governance",
];

export const screenById = (id: string): ScreenDef => SCREENS.find((s) => s.id === id)!;

export function screenForPath(pathname: string): ScreenDef | undefined {
  if (pathname === "/") return screenById("SCR-01");
  if (pathname === "/jobs/new") return screenById("SCR-03");
  if (pathname.startsWith("/jobs")) return screenById("SCR-04");
  return SCREENS.find((s) => s.path !== "/" && pathname.startsWith(s.path));
}
