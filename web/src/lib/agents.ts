/**
 * Agent registry from the design (06-agent-design/01-agent-catalogue.md). This is the catalogue of
 * agents the platform defines; none of them runs in this build. Permissions are the design's
 * per-agent allow-list. Secrets, network egress and approvals are denied to every agent.
 */

export type AgentKind = "deterministic" | "llm" | "deterministic+llm";

export interface AgentDef {
  id: string;
  name: string;
  kind: AgentKind;
  stage: string;
  plannedSlice: string;
  purpose: string;
  permissions: {
    readSnapshot: string;
    proposeTasks: string;
    modelGateway: string;
    readEvidence: string;
    writeFindings: string;
    proposePatch: string;
  };
}

export const AGENT_KIND_LABEL: Record<AgentKind, string> = {
  deterministic: "Deterministic service",
  llm: "LLM-assisted (local model)",
  "deterministic+llm": "Deterministic + LLM narrative",
};

export const AGENTS: AgentDef[] = [
  {
    id: "AG-01",
    name: "Orchestrator Agent",
    kind: "deterministic+llm",
    stage: "Planning and all stage transitions",
    plannedSlice: "2c",
    purpose: "Turn a validated job into an executable plan and drive it to a terminal state.",
    permissions: {
      readSnapshot: "Metadata only",
      proposeTasks: "Plan tasks",
      modelGateway: "Yes",
      readEvidence: "Status only",
      writeFindings: "No",
      proposePatch: "No",
    },
  },
  {
    id: "AG-02",
    name: "Requirements Analysis Agent",
    kind: "llm",
    stage: "Planning",
    plannedSlice: "2c",
    purpose: "Derive prioritised, traceable scenarios from requirements, OpenAPI and the diff.",
    permissions: {
      readSnapshot: "Yes",
      proposeTasks: "No",
      modelGateway: "Yes",
      readEvidence: "No",
      writeFindings: "No",
      proposePatch: "No",
    },
  },
  {
    id: "AG-03",
    name: "Functional Testing Agent",
    kind: "deterministic+llm",
    stage: "Baseline Run, Functional & API Testing",
    plannedSlice: "1d",
    purpose: "Select and run existing suites; draft candidate tests for human review.",
    permissions: {
      readSnapshot: "Yes",
      proposeTasks: "Yes",
      modelGateway: "Yes",
      readEvidence: "Own results",
      writeFindings: "Signals only",
      proposePatch: "No",
    },
  },
  {
    id: "AG-04",
    name: "API Testing Agent",
    kind: "deterministic+llm",
    stage: "Functional & API Testing",
    plannedSlice: "3a",
    purpose: "Schema, negative and authorisation checks against an authorised target.",
    permissions: {
      readSnapshot: "Yes",
      proposeTasks: "Yes",
      modelGateway: "Yes",
      readEvidence: "Own results",
      writeFindings: "Signals only",
      proposePatch: "No",
    },
  },
  {
    id: "AG-05",
    name: "Security Testing Agent",
    kind: "deterministic+llm",
    stage: "Security Testing",
    plannedSlice: "2a",
    purpose: "Orchestrate scanners and triage alerts; promotion needs evidence.",
    permissions: {
      readSnapshot: "Yes",
      proposeTasks: "Yes",
      modelGateway: "Yes",
      readEvidence: "Own results",
      writeFindings: "Signals only",
      proposePatch: "No",
    },
  },
  {
    id: "AG-06",
    name: "Performance Testing Agent",
    kind: "deterministic+llm",
    stage: "Performance Testing",
    plannedSlice: "3b",
    purpose: "Bounded workloads within caps; compare with thresholds and baseline.",
    permissions: {
      readSnapshot: "Yes",
      proposeTasks: "Yes",
      modelGateway: "Yes",
      readEvidence: "Own results",
      writeFindings: "Signals only",
      proposePatch: "No",
    },
  },
  {
    id: "AG-07",
    name: "Mutation Testing Agent",
    kind: "deterministic+llm",
    stage: "Mutation Testing",
    plannedSlice: "3c",
    purpose: "Mutation score on changed modules; explain surviving mutants.",
    permissions: {
      readSnapshot: "Yes",
      proposeTasks: "Yes",
      modelGateway: "Yes",
      readEvidence: "Own results",
      writeFindings: "Signals only",
      proposePatch: "No",
    },
  },
  {
    id: "AG-08",
    name: "Evidence and Defect Analysis Agent",
    kind: "deterministic+llm",
    stage: "Evidence Correlation & Triage",
    plannedSlice: "2b",
    purpose: "Fingerprint, deduplicate, reproduce and score findings deterministically.",
    permissions: {
      readSnapshot: "Yes",
      proposeTasks: "Reproduction only",
      modelGateway: "Yes",
      readEvidence: "Yes",
      writeFindings: "Yes (non-terminal)",
      proposePatch: "No",
    },
  },
  {
    id: "AG-09",
    name: "Patch Proposal Agent",
    kind: "llm",
    stage: "Patch Proposal",
    plannedSlice: "3d",
    purpose: "Propose minimal diffs for confirmed findings, for human review only.",
    permissions: {
      readSnapshot: "Yes",
      proposeTasks: "No",
      modelGateway: "Yes",
      readEvidence: "Finding evidence",
      writeFindings: "No",
      proposePatch: "Yes",
    },
  },
  {
    id: "AG-10",
    name: "Independent Verification Agent",
    kind: "deterministic+llm",
    stage: "Independent Verification",
    plannedSlice: "3d",
    purpose: "Re-run checks on commit plus approved patch in a fresh sandbox.",
    permissions: {
      readSnapshot: "Yes",
      proposeTasks: "Verification only",
      modelGateway: "Summary only",
      readEvidence: "Original finding only",
      writeFindings: "Verification result",
      proposePatch: "No",
    },
  },
  {
    id: "AG-11",
    name: "QA Report Agent",
    kind: "deterministic+llm",
    stage: "Quality Gates & Reporting",
    plannedSlice: "2d",
    purpose: "Evaluate QG-01 to QG-08 deterministically; write a labelled narrative.",
    permissions: {
      readSnapshot: "No",
      proposeTasks: "No",
      modelGateway: "Narrative only",
      readEvidence: "Yes",
      writeFindings: "No",
      proposePatch: "No",
    },
  },
];
