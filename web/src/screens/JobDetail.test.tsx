import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { emptyPage, jsonResponse, renderWithProviders } from "../test/utils";

const JOB = {
  id: "job_01TEST",
  display_id: "QA-1001",
  state: "completed_with_warnings",
  repository_id: "repo_1",
  project_id: "proj_1",
  ref: "main",
  commit_sha: "abcdef1234567890",
  profiles: { functional: true, security: false, performance: false, mutation: false },
  held_reason: null,
  created_at: "2026-10-24T10:00:00Z",
  deadline_at: null,
  version: 3,
  updated_at: "2026-10-24T10:05:00Z",
  snapshot_sha256: "0123456789abcdef0123",
  warnings: ["pytest skipped: repository code execution is disabled on this host"],
  task_summary: { succeeded: 4 },
  check_summary: { passed: 2, failed: 1, skipped: 1 },
  test_summary: {},
  stages: [
    { stage: "intake_pinning", status: "succeeded", note: null, tasks: 0 },
    { stage: "planning", status: "succeeded", note: null, tasks: 0 },
    { stage: "environment_preparation", status: "succeeded", note: null, tasks: 1 },
    { stage: "baseline_run", status: "succeeded", note: null, tasks: 3 },
    { stage: "functional_api_testing", status: "skipped", note: "not in plan", tasks: 0 },
    { stage: "security_testing", status: "skipped", note: "not in plan", tasks: 0 },
    { stage: "performance_testing", status: "skipped", note: "not in plan", tasks: 0 },
    { stage: "mutation_testing", status: "skipped", note: "not in plan", tasks: 0 },
    { stage: "evidence_correlation_triage", status: "skipped", note: "not in plan", tasks: 0 },
    { stage: "patch_proposal", status: "skipped", note: "not in plan", tasks: 0 },
    { stage: "independent_verification", status: "skipped", note: "not in plan", tasks: 0 },
    { stage: "quality_gates_reporting", status: "succeeded", note: null, tasks: 0 },
    { stage: "cleanup_retention", status: "succeeded", note: null, tasks: 0 },
  ],
};

const CHECK = {
  id: "chk_1",
  job_id: JOB.id,
  task_id: "task_1",
  attempt_no: 1,
  worker_run_id: "wrun_1",
  engine_id: "python_syntax",
  name: "Python syntax",
  outcome: "failed",
  started_at: "2026-10-24T10:01:00Z",
  ended_at: "2026-10-24T10:01:02Z",
  duration_ms: 2000,
  failure_message: "scripts/legacy_report.py:3: invalid syntax",
  summary: { files: 4, errors: 1 },
  tool_name: "python",
  tool_version: "3.12.0",
  executes_repository_code: false,
  log_evidence_id: null,
  evidence_ids: [],
};

function mockApi() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith(`/jobs/${JOB.id}`)) return jsonResponse(JOB);
      if (url.endsWith("/checks")) return jsonResponse([CHECK]);
      if (url.endsWith("/tasks") || url.endsWith("/evidence")) return jsonResponse([]);
      if (url.includes("/repositories/repo_1"))
        return jsonResponse({
          id: "repo_1",
          url: "https://fixtures.local/local/sample-python-app",
        });
      return jsonResponse(emptyPage());
    }),
  );
}

afterEach(() => vi.unstubAllGlobals());

describe("JobDetail (phase 2)", () => {
  it("renders the derived 13-stage timeline, summaries, warnings and real check rows", async () => {
    mockApi();
    renderWithProviders(<App />, { route: `/jobs/${JOB.id}` });
    await waitFor(() =>
      expect(screen.getByRole("heading", { level: 1, name: /QA-1001/ })).toBeInTheDocument(),
    );
    expect(screen.getAllByRole("listitem").filter((li) => li.dataset.stageStatus)).toHaveLength(13);
    expect(document.querySelectorAll('[data-stage-status="skipped"]')).toHaveLength(7);
    expect(screen.getByText(/pytest skipped/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText("scripts/legacy_report.py:3: invalid syntax")).toBeInTheDocument(),
    );
    expect(screen.getByText(/snapshot/)).toBeInTheDocument();
  });
});
