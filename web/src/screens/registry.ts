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

export interface ScreenDef {
  id: string;
  name: string;
  navLabel: string;
  path: string;
  group: "OVERVIEW" | "EXECUTION" | "RESULTS" | "FINDINGS & FIXES" | "GOVERNANCE";
  icon: LucideIcon;
  purpose: string;
  plannedSlice?: string;
}

export const SCREENS: ScreenDef[] = [
  {
    id: "SCR-01",
    name: "Dashboard — QA Health Overview",
    navLabel: "Dashboard",
    path: "/",
    group: "OVERVIEW",
    icon: LayoutGrid,
    purpose: "Give a one-page view of quality across projects, as the landing screen after login.",
  },
  {
    id: "SCR-02",
    name: "Repositories & Projects",
    navLabel: "Repositories",
    path: "/repositories",
    group: "OVERVIEW",
    icon: BookOpen,
    purpose: "Manage projects and the repositories registered to them.",
  },
  {
    id: "SCR-03",
    name: "New QA Job Wizard",
    navLabel: "New QA Job",
    path: "/jobs/new",
    group: "OVERVIEW",
    icon: PlusCircle,
    purpose: "Configure and launch a QA job with explicit scope, profiles, targets and limits.",
  },
  {
    id: "SCR-04",
    name: "Live Job Execution",
    navLabel: "Jobs · live",
    path: "/jobs",
    group: "EXECUTION",
    icon: Activity,
    purpose: "Follow a running job stage by stage and task by task.",
  },
  {
    id: "SCR-05",
    name: "Agent Collaboration Graph",
    navLabel: "Agent Graph",
    path: "/agent-graph",
    group: "EXECUTION",
    icon: Share2,
    purpose:
      "Show how agents and tasks relate in the job plan, and what each agent received, proposed and produced.",
    plannedSlice: "1d",
  },
  {
    id: "SCR-06",
    name: "Functional Test Results",
    navLabel: "Functional Tests",
    path: "/results/functional",
    group: "RESULTS",
    icon: SquareCheck,
    purpose: "Present functional test outcomes and failure detail.",
  },
  {
    id: "SCR-07",
    name: "API Test Results",
    navLabel: "API Tests",
    path: "/results/api",
    group: "RESULTS",
    icon: Braces,
    purpose:
      "Show API contract and authorization test outcomes with request and response evidence.",
    plannedSlice: "1d",
  },
  {
    id: "SCR-08",
    name: "Security Testing Center",
    navLabel: "Security Center",
    path: "/security",
    group: "RESULTS",
    icon: Shield,
    purpose: "Present security scans and findings for triage.",
    plannedSlice: "2a",
  },
  {
    id: "SCR-09",
    name: "Performance Testing Lab",
    navLabel: "Performance Lab",
    path: "/performance",
    group: "RESULTS",
    icon: Gauge,
    purpose:
      "Configure bounded performance runs and analyze results against thresholds and baseline.",
    plannedSlice: "3b",
  },
  {
    id: "SCR-10",
    name: "Mutation Testing Dashboard",
    navLabel: "Mutation",
    path: "/mutation",
    group: "RESULTS",
    icon: Shuffle,
    purpose: "Show test-suite strength on changed modules.",
    plannedSlice: "3c",
  },
  {
    id: "SCR-11",
    name: "Defect Evidence & Investigation",
    navLabel: "Defects & Evidence",
    path: "/defects",
    group: "FINDINGS & FIXES",
    icon: Bug,
    purpose: "Investigate a single finding and record triage decisions.",
    plannedSlice: "2b",
  },
  {
    id: "SCR-12",
    name: "Patch Review",
    navLabel: "Patches",
    path: "/patches",
    group: "FINDINGS & FIXES",
    icon: GitPullRequest,
    purpose: "Review a proposed patch and decide whether it proceeds to verification.",
    plannedSlice: "3d",
  },
  {
    id: "SCR-13",
    name: "Independent Verification",
    navLabel: "Verification",
    path: "/verification",
    group: "FINDINGS & FIXES",
    icon: CheckCircle2,
    purpose: "Show the fresh-sandbox verification result of an approved patch.",
    plannedSlice: "3d",
  },
  {
    id: "SCR-14",
    name: "Reports & Release Readiness",
    navLabel: "Reports",
    path: "/reports",
    group: "GOVERNANCE",
    icon: FileText,
    purpose:
      "Present gate results, residual risk and the release recommendation, and capture the human decision.",
    plannedSlice: "2d",
  },
  {
    id: "SCR-15",
    name: "Settings & Integrations",
    navLabel: "Settings",
    path: "/settings",
    group: "GOVERNANCE",
    icon: Settings,
    purpose: "Administer the platform's safety limits, permissions, integrations and model access.",
    plannedSlice: "3e",
  },
];

export const NAV_GROUPS: ScreenDef["group"][] = [
  "OVERVIEW",
  "EXECUTION",
  "RESULTS",
  "FINDINGS & FIXES",
  "GOVERNANCE",
];

export const screenById = (id: string): ScreenDef => SCREENS.find((s) => s.id === id)!;
