import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { layoutPlan } from "../components/PlanDag";
import { checkWarning, parseRequirements } from "../lib/jobInputs";
import { stageViews } from "../lib/stages";
import {
  JOB_ID,
  finishedJobFixture,
  jobFixture,
  mockFetchRoutes,
  pendingGatesFixture,
  phase3Routes,
  planFixture,
  projectFixture,
  renderWithProviders,
  repositoryFixture,
  tasksFixture,
} from "../test/utils";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.setAttribute("data-theme", "dark");
});
afterEach(() => vi.unstubAllGlobals());

describe("job inputs helpers", () => {
  it("parses one requirement per non-empty line", () => {
    expect(parseRequirements(" a \n\n b\n")).toEqual(["a", "b"]);
  });

  it("warns about checks the local policy will block", () => {
    expect(
      checkWarning({
        method: "GET",
        url: "http://localhost:8000/x",
        expected_status: 200,
        priority: "P1",
      }),
    ).toBeNull();
    expect(
      checkWarning({
        method: "GET",
        url: "https://example.com/",
        expected_status: 200,
        priority: "P1",
      }),
    ).toMatch(/block/);
    expect(
      checkWarning({
        method: "GET",
        url: "http://u:p@localhost/x",
        expected_status: 200,
        priority: "P1",
      }),
    ).toMatch(/Credentials/);
    expect(
      checkWarning({ method: "GET", url: "nope", expected_status: 200, priority: "P1" }),
    ).toMatch(/absolute URL/);
  });
});

describe("plan layout and stages", () => {
  it("levels nodes by their longest dependency chain and joins task states", () => {
    const placed = layoutPlan(planFixture.nodes, tasksFixture.items as never);
    const byKey = Object.fromEntries(placed.map((p) => [p.node.key, p]));
    expect(byKey.requirements.level).toBe(0);
    expect(byKey.api.level).toBe(1);
    expect(byKey.evidence.level).toBe(2);
    expect(byKey.report.level).toBe(3);
    expect(byKey.report.state).toBe("succeeded");
    const noTasks = layoutPlan(planFixture.nodes, []);
    expect(noTasks.every((p) => p.state === "not_enqueued")).toBe(true);
  });

  it("maps the new stage statuses and falls back to pending for unknown ones", () => {
    const views = stageViews(
      finishedJobFixture({
        stages: [
          { stage: "planning", status: "awaiting_approval" },
          { stage: "security_testing", status: "not_planned" },
          { stage: "baseline_run", status: "bogus" },
        ],
      }) as never,
    );
    const s = Object.fromEntries(views.map((v) => [v.key, v.status]));
    expect(s.planning).toBe("awaiting_approval");
    expect(s.security_testing).toBe("not_planned");
    expect(s.baseline_run).toBe("pending");
  });
});

describe("new job wizard inputs", () => {
  it("sends requirements, API checks and the HA-05 flag in the request body", async () => {
    const created = jobFixture({ state: "running", held_reason: null });
    const fetchMock = mockFetchRoutes([
      { match: "/jobs", method: "POST", status: 202, body: created },
      ...phase3Routes(),
    ]);
    renderWithProviders(<App />, { route: "/jobs/new?repository=repo_01" });
    await screen.findByRole("heading", { level: 1, name: /New QA job/ });
    await waitFor(() =>
      expect((screen.getByLabelText("Repository") as HTMLSelectElement).value).toBe("repo_01"),
    );
    fireEvent.click(screen.getByRole("button", { name: /Inputs/ }));
    fireEvent.change(screen.getByLabelText(/^Requirements/), {
      target: { value: "The service must answer health checks\n\nReports should export" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Quick add/ }));
    expect(screen.getByLabelText("URL")).toHaveValue("http://localhost:8000/healthz");
    fireEvent.click(screen.getByLabelText(/Require plan approval/));
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    expect(screen.getByText(/Required \(HA-05\)/)).toBeInTheDocument();
    expect(screen.getByText(/waits for a QA Lead to approve/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Create job/ }));
    await screen.findByText("Job created");
    const post = fetchMock.mock.calls.find((c) => (c[1]?.method ?? "GET") === "POST");
    const body = JSON.parse(String(post![1]!.body));
    expect(body.inputs).toEqual({
      requirements: ["The service must answer health checks", "Reports should export"],
      api_checks: [
        {
          method: "GET",
          url: "http://localhost:8000/healthz",
          expected_status: 200,
          priority: "P0",
        },
      ],
    });
    expect(body.require_plan_approval).toBe(true);
  });

  it("says plainly that a job without inputs is held", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: "/jobs/new?repository=repo_01" });
    await screen.findByRole("heading", { level: 1, name: /New QA job/ });
    await waitFor(() =>
      expect((screen.getByLabelText("Repository") as HTMLSelectElement).value).toBe("repo_01"),
    );
    fireEvent.click(screen.getByRole("button", { name: /Review/ }));
    expect(screen.getByText(/No inputs were supplied/)).toBeInTheDocument();
  });

  it("flags a check whose host is not local before the API blocks it", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: "/jobs/new?repository=repo_01" });
    await screen.findByRole("heading", { level: 1, name: /New QA job/ });
    fireEvent.click(await screen.findByRole("button", { name: /Inputs/ }));
    fireEvent.click(screen.getByRole("button", { name: "Add check" }));
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://example.com/" } });
    expect(screen.getByText(/local policy will block/)).toBeInTheDocument();
  });
});

describe("job detail after orchestration", () => {
  it("shows persisted tasks, adapters, warnings, the plan graph and report actions", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/jobs/${JOB_ID}` });
    await screen.findByRole("heading", { level: 1, name: /QA-0001/ });
    const rail = screen.getByRole("list", { name: "Pipeline stages" });
    const items = within(rail).getAllByRole("listitem");
    expect(items[0]).toHaveAttribute("data-status", "not_run");
    expect(items[1]).toHaveAttribute("data-status", "succeeded");
    expect(items[5]).toHaveAttribute("data-status", "not_planned");
    await screen.findByText("4 of 4 succeeded");
    expect(screen.getAllByText("deterministic")).toHaveLength(4);
    expect(screen.getByRole("note", { name: "Job warnings" })).toHaveTextContent(
      /no execution engine/,
    );
    expect(screen.getByRole("img", { name: /Plan graph/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open HTML report/ })).toHaveAttribute(
      "href",
      expect.stringContaining(`/jobs/${JOB_ID}/report?format=html`),
    );
    expect(screen.getByRole("link", { name: "FND-0001" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Cancel job/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Approve plan/ })).toBeNull();
  });

  it("expands a task to show its attempts and output payload", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/jobs/${JOB_ID}` });
    await screen.findByText("4 of 4 succeeded");
    fireEvent.click(screen.getByText("requirements.analyze").closest("tr")!);
    await screen.findByText(/^hard: none/);
    expect(screen.getByText("raone-runner")).toBeInTheDocument();
    expect(screen.getByText("Payload")).toBeInTheDocument();
  });

  it("offers approve and reject only while awaiting approval and posts the decision", async () => {
    const job = finishedJobFixture({
      state: "awaiting_approval",
      held_reason: "Plan approval required (HA-05)",
      report_available: false,
      task_summary: {},
      warnings: {},
      stages: [{ stage: "planning", status: "awaiting_approval", note: "HA-05" }],
    });
    const fetchMock = mockFetchRoutes([
      {
        match: `/jobs/${JOB_ID}/plan/approval`,
        method: "POST",
        status: 202,
        body: { job_id: JOB_ID, state: "running", approval_id: "apr_01", decision: "approved" },
      },
      { match: `/jobs/${JOB_ID}/plan`, body: { ...planFixture, approval_required: true } },
      { match: `/jobs/${JOB_ID}/tasks`, body: { items: [], next_cursor: null, limit: 0 } },
      ...phase3Routes(job),
    ]);
    renderWithProviders(<App />, { route: `/jobs/${JOB_ID}` });
    await screen.findByText("Human approval required (HA-05).");
    expect(screen.getByText("No tasks yet")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(screen.getByRole("button", { name: /Reject plan/ })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Back" }));
    fireEvent.click(screen.getByRole("button", { name: /Approve plan/ }));
    await screen.findByText("Plan approved");
    const post = fetchMock.mock.calls.find((c) => (c[1]?.method ?? "GET") === "POST");
    expect(JSON.parse(String(post![1]!.body))).toEqual({ decision: "approve", reason: null });
  });
});

describe("result screens", () => {
  it("lists API executions with expected and observed status and opens evidence", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/results/api?job=${JOB_ID}` });
    await screen.findByRole("heading", { level: 1, name: "API Test Results" });
    await screen.findByText("2 executed of 3");
    expect(screen.getByText("200 / 404")).toBeInTheDocument();
    expect(screen.getByText(/not in the local allow-list/)).toBeInTheDocument();
    fireEvent.click(
      screen.getByRole("button", {
        name: /View evidence for GET http:\/\/localhost:8000\/missing/,
      }),
    );
    const dialog = await screen.findByRole("dialog", { name: /Evidence evd_02/ });
    expect(within(dialog).getByText("redaction redacted")).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Evidence content")).toHaveTextContent("[REDACTED]");
  });

  it("shows functional scenarios as skipped, never passed", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/results/functional?job=${JOB_ID}` });
    await screen.findByRole("heading", { level: 1, name: "Functional Test Results" });
    await screen.findByText("0 executed of 1");
    expect(screen.getAllByText("Skipped").length).toBeGreaterThan(0);
    expect(screen.queryByText("Passed")).toBeNull();
  });

  it("renders a finding with DCS, facts and inferred notes separated", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByRole("heading", { level: 1, name: /Defect Evidence/ });
    await screen.findByText(/FND-0001/);
    expect(screen.getByRole("meter", { name: "Defect Confidence Score" })).toHaveAttribute(
      "aria-valuenow",
      "63",
    );
    expect(
      within(screen.getByLabelText("Verified facts")).getByText(/Observed HTTP 404/),
    ).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Inferred notes")).getByText(/Inference:/),
    ).toBeInTheDocument();
    expect(screen.getByText(/Request reproduction: needs a fresh sandbox/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /View evidence \(1\)/ }));
    await screen.findByRole("dialog", { name: /Evidence evd_02/ });
  });

  it("renders gates, verdict and report actions, and keeps the release decision unavailable", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/reports?job=${JOB_ID}` });
    await screen.findByRole("heading", { level: 1, name: /Reports/ });
    await screen.findByText("Blocking gate(s) failed: QG-03.");
    expect(screen.getAllByText("Not Applicable")).toHaveLength(3);
    expect(screen.getByText("Inconclusive")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Open HTML report/ })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Download JSON/ })).toBeInTheDocument();
    expect(screen.getByText(/deterministic template/)).toBeInTheDocument();
    expect(screen.getByText(/Not available \(slice 2d\)/)).toBeInTheDocument();
  });

  it("shows pending gates with no verdict when no report exists", async () => {
    const job = finishedJobFixture({ state: "running", report_available: false });
    mockFetchRoutes([
      { match: `/jobs/${JOB_ID}/quality-gates`, body: pendingGatesFixture },
      {
        match: `/jobs/${JOB_ID}/report`,
        status: 404,
        body: { type: "about:blank", title: "Not found", status: 404, error_code: "not_found" },
      },
      ...phase3Routes(job),
    ]);
    renderWithProviders(<App />, { route: `/reports?job=${JOB_ID}` });
    await screen.findByText("Gates are evaluated when the report is produced.");
    expect(screen.getByText("No verdict yet")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Open HTML report/ })).toBeNull();
    await screen.findByText("No report has been generated for this job yet.");
  });

  it("explains the empty state when there are no jobs", async () => {
    mockFetchRoutes([
      { match: "/projects", body: { items: [projectFixture], next_cursor: null, limit: 50 } },
      {
        match: "/repositories",
        body: { items: [repositoryFixture], next_cursor: null, limit: 50 },
      },
    ]);
    renderWithProviders(<App />, { route: "/defects" });
    await screen.findByText("No jobs yet");
  });
});

describe("agent graph with a job", () => {
  it("draws the plan DAG coloured by persisted task state", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/agent-graph?job=${JOB_ID}` });
    const dag = await screen.findByRole("img", { name: /Plan graph/ });
    expect(dag.querySelectorAll("[data-node]")).toHaveLength(4);
    expect(dag.querySelector('[data-node="report"]')).toHaveAttribute("data-state", "succeeded");
    expect(dag.querySelectorAll('[data-edge="soft"]')).toHaveLength(2);
    expect(dag.querySelectorAll('[data-edge="hard"]')).toHaveLength(1);
    await screen.findByText("4 of 4 tasks succeeded");
  });
});

describe("dashboard outcome tiles", () => {
  it("reads the latest finished job's executions, findings and verdict", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: "/" });
    await screen.findByText("Test executions · QA-0001");
    await screen.findByText("NOT READY");
    expect(screen.getByText("1 failed, 2 skipped or blocked")).toBeInTheDocument();
    expect(screen.queryByText("No data yet")).toBeNull();
  });
});
