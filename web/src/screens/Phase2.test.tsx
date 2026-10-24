import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { parseTestCounts } from "../api/client";
import { capabilityPill } from "../lib/capabilities";
import {
  JOB_ID,
  capabilitiesFixture,
  findingsFixture,
  mockFetchRoutes,
  partialReportFixture,
  phase2Routes,
  pinnedJobFixture,
  renderWithProviders,
} from "../test/utils";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.setAttribute("data-theme", "dark");
});
afterEach(() => vi.unstubAllGlobals());

describe("capability pill", () => {
  it("names the execution mode honestly for every capability state", () => {
    expect(capabilityPill(undefined)).toBe("Concept build — no repository code executed");
    expect(
      capabilityPill({
        execution_enabled: false,
        repository_code_execution_allowed: false,
        sandbox: "process",
      }),
    ).toBe("Execution off — agent checks on supplied inputs only");
    expect(
      capabilityPill({
        execution_enabled: true,
        repository_code_execution_allowed: false,
        sandbox: "process (no gVisor/Docker on this build)",
      }),
    ).toBe(
      "Execution on (process (no gVisor/Docker on this build)) — deterministic checks only, no repository code executed",
    );
    expect(
      capabilityPill({
        execution_enabled: true,
        repository_code_execution_allowed: true,
        sandbox: "process",
      }),
    ).toBe("Execution on (process) — repository code runs UNSANDBOXED (dev only)");
  });

  it("parses the X-Test-Counts header", () => {
    expect(parseTestCounts("failed=2,passed=5")).toEqual({ failed: 2, passed: 5 });
    expect(parseTestCounts(null)).toEqual({});
    expect(parseTestCounts("bad")).toEqual({});
  });

  it("renders the pill from the capabilities endpoint", async () => {
    mockFetchRoutes([
      {
        match: "/system/capabilities",
        body: { ...capabilitiesFixture, execution_enabled: true },
      },
    ]);
    renderWithProviders(<App />, { route: "/jobs" });
    await screen.findByText(/Execution on \(process/);
    expect(screen.getByTestId("mode-pill")).toHaveTextContent(/deterministic checks only/);
  });
});

describe("job detail with Execution Service results", () => {
  it("shows checks, worker runs, snapshot and previous runs with a compare link", async () => {
    mockFetchRoutes(phase2Routes());
    renderWithProviders(<App />, { route: `/jobs/${JOB_ID}` });
    await screen.findByRole("heading", { level: 1, name: /QA-0001/ });
    await screen.findByText("Python syntax");
    expect(screen.getByText("scripts/legacy_report.py:4 '(' was never closed")).toBeInTheDocument();
    expect(screen.getByText(/snapshot 29dd53829f/)).toBeInTheDocument();
    const checks = screen.getByRole("list", { name: "Checks by outcome" });
    expect(within(checks).getAllByRole("listitem")).toHaveLength(3);
    expect(screen.getByRole("list", { name: "Worker runs" })).toHaveTextContent("exec-host-1");
    const previous = screen.getByRole("list", { name: "Previous runs" });
    expect(within(previous).getByRole("link", { name: "Compare" })).toHaveAttribute(
      "href",
      `/jobs/${JOB_ID}/compare/job_00`,
    );
    expect(screen.getByRole("list", { name: "Pipeline stages" }).firstElementChild).toBeTruthy();
    expect(screen.getByText("7 of 7 succeeded")).toBeInTheDocument();
  });

  it("opens the log evidence of a check and reads its stored text", async () => {
    mockFetchRoutes(phase2Routes());
    renderWithProviders(<App />, { route: `/jobs/${JOB_ID}` });
    await screen.findByText("Python syntax");
    fireEvent.click(screen.getByRole("button", { name: "View log for Python syntax" }));
    await screen.findByLabelText("Evidence content");
    await waitFor(() =>
      expect(screen.getByLabelText("Evidence content")).toHaveTextContent(
        /SyntaxError: '\(' was never closed/,
      ),
    );
  });

  it("labels Execution Service tasks and never shows an agent output for them", async () => {
    mockFetchRoutes(phase2Routes());
    renderWithProviders(<App />, { route: `/jobs/${JOB_ID}` });
    await screen.findByText("7 of 7 succeeded");
    expect(screen.getAllByText("exec host").length).toBeGreaterThanOrEqual(2);
    fireEvent.click(screen.getByText("env_prepare").closest("tr")!);
    await screen.findByText(/Execution Service task/);
    expect(screen.queryByText("Payload")).toBeNull();
  });

  it("shows intake and planner warnings as a plain list", async () => {
    mockFetchRoutes(
      phase2Routes(
        pinnedJobFixture({
          warnings: ["Repository checks were not planned: the Execution Service is disabled."],
        }),
      ),
    );
    renderWithProviders(<App />, { route: `/jobs/${JOB_ID}` });
    expect(await screen.findByRole("note", { name: "Job warnings" })).toHaveTextContent(
      /Execution Service is disabled/,
    );
  });
});

describe("compare runs", () => {
  it("renders check and test deltas from the API", async () => {
    mockFetchRoutes(phase2Routes());
    renderWithProviders(<App />, { route: `/jobs/${JOB_ID}/compare/job_00` });
    await screen.findByRole("heading", { level: 1, name: "QA-0001 vs QA-0000" });
    expect(screen.getByText(/1 improved · 1 removed/)).toBeInTheDocument();
    const improved = document.querySelectorAll("[data-delta='improved']");
    expect(improved).toHaveLength(2);
    expect(document.querySelector("[data-delta='removed']")).toHaveTextContent("Removed");
    expect(screen.getByText("tests/test_rounding.py::test_rounds_half_even")).toBeInTheDocument();
    expect(screen.getByText(/different commits/)).toBeInTheDocument();
  });

  it("shows the problem when the comparison is rejected", async () => {
    mockFetchRoutes([
      {
        match: `/jobs/${JOB_ID}/compare`,
        status: 400,
        body: {
          type: "about:blank",
          title: "Bad request",
          status: 400,
          detail: "A job cannot be compared with itself.",
          error_code: "bad_request",
        },
      },
    ]);
    renderWithProviders(<App />, { route: `/jobs/${JOB_ID}/compare/${JOB_ID}` });
    await screen.findByText(/cannot be compared with itself/);
  });
});

describe("results screens with pytest executions", () => {
  it("lists pytest rows with node id, file and job-wide counts, plus the checks table", async () => {
    mockFetchRoutes(phase2Routes());
    renderWithProviders(<App />, { route: `/results/functional?job=${JOB_ID}` });
    await screen.findByText("test_rounds_half_even");
    expect(screen.getByText("tests/test_rounding.py::test_rounds_half_even")).toBeInTheDocument();
    expect(screen.getAllByText("tests/test_rounding.py").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByLabelText("Job-wide test counts")).toHaveTextContent(
      "blocked 1 · failed 2 · passed 1 · skipped 1",
    );
    expect(screen.getByRole("heading", { name: /Repository checks/ })).toBeInTheDocument();
    expect(screen.getByText("Repository test suite")).toBeInTheDocument();
    expect(screen.getByText(/refused/)).toBeInTheDocument();
  });

  it("keeps the API tab to API executions only", async () => {
    mockFetchRoutes(phase2Routes());
    renderWithProviders(<App />, { route: `/results/api?job=${JOB_ID}` });
    await screen.findByText("GET http://localhost:8000/healthz responds 200");
    expect(screen.queryByText("test_rounds_half_even")).toBeNull();
    expect(screen.queryByRole("heading", { name: /Repository checks/ })).toBeNull();
  });
});

describe("reports with a partial report", () => {
  it("says the job did not complete and shows the recorded checks without gates", async () => {
    const job = pinnedJobFixture({ state: "failed", report_available: true });
    mockFetchRoutes([
      { match: `/jobs/${JOB_ID}/report`, body: partialReportFixture },
      ...phase2Routes(job),
    ]);
    renderWithProviders(<App />, { route: `/reports?job=${JOB_ID}` });
    await screen.findByText("Partial report — job did not complete");
    expect(screen.getByText(/there is no verdict/)).toBeInTheDocument();
    expect(screen.getByText("worker crashed (E-EXEC-003)")).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: /^Narrative/ })).toBeNull();
    expect(screen.getByText("basic-partial")).toBeInTheDocument();
  });

  it("shows the check summary of a full report", async () => {
    mockFetchRoutes(phase2Routes());
    renderWithProviders(<App />, { route: `/reports?job=${JOB_ID}` });
    await screen.findByRole("heading", { name: /^Narrative/ });
    expect(screen.getByText("AG-11 deterministic 1.0")).toBeInTheDocument();
    expect(screen.queryByText("Partial report — job did not complete")).toBeNull();
  });
});

describe("defects from check engines and pytest", () => {
  it("renders file and node locations instead of raw JSON", async () => {
    const syntax = {
      ...findingsFixture.items[0],
      id: "fnd_03",
      display_id: "FND-0003",
      category: "code.syntax",
      title: "python_syntax failed at scripts/legacy_report.py",
      location: { file: "scripts/legacy_report.py", engine: "python_syntax", rule: null },
    };
    const test = {
      ...findingsFixture.items[0],
      id: "fnd_04",
      display_id: "FND-0004",
      category: "test.failure",
      title: "tests/test_rounding.py::test_rounds_half_even: AssertionError",
      location: {
        file: "tests/test_rounding.py",
        node_id: "tests/test_rounding.py::test_rounds_half_even",
      },
    };
    mockFetchRoutes([
      {
        match: `/jobs/${JOB_ID}/findings`,
        body: { items: [syntax, test], next_cursor: null, limit: 2 },
      },
      { match: "/findings/fnd_03/history", body: { items: [], next_cursor: null, limit: 0 } },
      { match: "/findings/fnd_03/evidence", body: { items: [], next_cursor: null, limit: 0 } },
      ...phase2Routes(),
    ]);
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}&finding=fnd_03` });
    await screen.findByText("python_syntax · scripts/legacy_report.py");
    fireEvent.click(screen.getByText("FND-0004"));
    await screen.findByText("tests/test_rounding.py::test_rounds_half_even");
  });
});

describe("settings", () => {
  it("shows the execution flags from the capabilities endpoint", async () => {
    mockFetchRoutes([{ match: "/system/capabilities", body: capabilitiesFixture }]);
    renderWithProviders(<App />, { route: "/settings" });
    await screen.findByRole("heading", { name: "Execution" });
    expect(screen.getByText("disabled (AQS_EXEC_TOKEN unset)")).toBeInTheDocument();
    expect(
      screen.getByText("snapshot_integrity, python_syntax, secret_scan, pytest"),
    ).toBeInTheDocument();
  });
});
