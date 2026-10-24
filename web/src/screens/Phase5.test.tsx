import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { etagFor } from "../api/client";
import {
  JOB_ID,
  falsePositiveFindingFixture,
  findingsFixture,
  mockFetchRoutes,
  phase3Routes,
  renderWithProviders,
} from "../test/utils";
import { legalTriageActions, priorityFormula } from "./Defects";

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.setAttribute("data-theme", "dark");
});
afterEach(() => vi.unstubAllGlobals());

const finding = findingsFixture.items[0];

describe("defect helpers", () => {
  it("offers only the transitions the backend allows", () => {
    expect(legalTriageActions("candidate")).toEqual([
      "mark_false_positive",
      "mark_duplicate",
      "accept_risk",
    ]);
    expect(legalTriageActions("reopened")).toContain("accept_risk");
    expect(legalTriageActions("false_positive")).toEqual(["reopen"]);
    expect(legalTriageActions("duplicate")).toEqual(["reopen"]);
    expect(legalTriageActions("accepted_risk")).toEqual(["reopen"]);
    expect(legalTriageActions("fix_proposed")).toEqual([]);
  });

  it("renders the priority formula from the stored breakdown", () => {
    expect(priorityFormula(finding.priority_breakdown)).toBe(
      "severity 4 × confidence 0.6 × exposure 1 = 2.4",
    );
    expect(etagFor("fnd_01", 3)).toBe('"fnd_01:v3"');
  });
});

describe("defects screen (SCR-11) with phase 5 records", () => {
  it("shows description, root causes with uncertainty, priority, reproducibility and affected tests", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByText(/FND-0001/);
    expect(
      within(screen.getByLabelText("Description")).getByText(/grouping does not discard/),
    ).toBeInTheDocument();
    const causes = screen.getByLabelText("Likely root causes");
    expect(within(causes).getByText(/route is not registered/)).toBeInTheDocument();
    expect(within(causes).getByText("Medium")).toBeInTheDocument();
    expect(within(causes).getByText(/Basis: observed 404/)).toBeInTheDocument();
    expect(
      within(causes).getByText("Hypotheses are rule-based and unverified; none changes the score."),
    ).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Priority")).getByText(
        "severity 4 × confidence 0.6 × exposure 1 = 2.4",
      ),
    ).toBeInTheDocument();
    const repro = screen.getByLabelText("Reproducibility");
    expect(within(repro).getByText("no")).toBeInTheDocument();
    expect(within(repro).getByText(/arrive in slice 2b/)).toBeInTheDocument();
    expect(
      within(screen.getByLabelText("Affected tests")).getByText("SCN-API-002"),
    ).toBeInTheDocument();
    expect(screen.getByRole("meter", { name: "Defect Confidence Score" })).toHaveAttribute(
      "aria-valuenow",
      "63",
    );
  });

  it("opens the evidence drawer from a hypothesis evidence link", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByText(/FND-0001/);
    fireEvent.click(
      within(screen.getByLabelText("Likely root causes")).getByRole("button", { name: "evd_02" }),
    );
    await screen.findByRole("dialog", { name: /Evidence evd_02/ });
  });

  it("lists earlier occurrences and the status timeline", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByText(/FND-0001/);
    const seen = screen.getByLabelText("Seen before");
    await within(seen).findAllByText("FND-0000");
    expect(within(seen).getByText(/First seen in QA-0000/)).toBeInTheDocument();
    expect(within(seen).getByText(/QA-0000 @ main/)).toBeInTheDocument();
    expect(screen.getByText("Seen before", { selector: "span" })).toBeInTheDocument();
    const timeline = screen.getByLabelText("Status history");
    expect(within(timeline).getByText("created")).toBeInTheDocument();
    expect(within(timeline).getByText(/AG-08 \(agent\)/)).toBeInTheDocument();
  });

  it("offers false positive, duplicate and accept risk for a candidate, never reopen", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByText(/FND-0001/);
    const triage = screen.getByLabelText("Triage");
    expect(within(triage).getByRole("button", { name: "Mark false positive" })).toBeEnabled();
    expect(within(triage).getByRole("button", { name: "Mark duplicate" })).toBeEnabled();
    expect(within(triage).getByRole("button", { name: "Accept risk" })).toBeEnabled();
    expect(within(triage).queryByRole("button", { name: "Reopen" })).toBeNull();
    expect(within(triage).getByRole("button", { name: "Request reproduction" })).toBeDisabled();
    expect(
      within(triage).getByText("Request reproduction: needs a fresh sandbox (slice 2b)."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Patch proposals are not available: they need repository source and a sandbox \(slice 3d\)/,
      ),
    ).toBeInTheDocument();
  });

  it("offers only reopen for a false positive and shows the last decision", async () => {
    const fp = falsePositiveFindingFixture();
    mockFetchRoutes([
      { match: `/jobs/${JOB_ID}/findings`, body: { items: [fp], next_cursor: null, limit: 1 } },
      ...phase3Routes(),
    ]);
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByText(/FND-0002/);
    const triage = screen.getByLabelText("Triage");
    expect(within(triage).getByRole("button", { name: "Reopen" })).toBeEnabled();
    expect(within(triage).queryByRole("button", { name: "Mark false positive" })).toBeNull();
    expect(within(triage).getByText(/Last decision: mark false positive/)).toBeInTheDocument();
    expect(within(triage).getByText(/"fixture route"/)).toBeInTheDocument();
  });

  it("posts the triage action with the reason and If-Match, then toasts in the past tense", async () => {
    const updated = { ...finding, status: "false_positive", confidence: "rejected", version: 2 };
    const fetchMock = mockFetchRoutes([
      { match: "/findings/fnd_01/triage", method: "POST", body: updated },
      ...phase3Routes(),
    ]);
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByText(/FND-0001/);
    fireEvent.click(screen.getByRole("button", { name: "Mark false positive" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark false positive" });
    const submit = within(dialog).getByRole("button", { name: "Mark false positive" });
    expect(submit).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Reason"), {
      target: { value: "Route intentionally absent" },
    });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);
    await screen.findByText("Marked false positive");
    const post = fetchMock.mock.calls.find((c) => (c[1]?.method ?? "GET") === "POST");
    expect(JSON.parse(String(post![1]!.body))).toEqual({
      action: "mark_false_positive",
      reason: "Route intentionally absent",
    });
    expect(new Headers(post![1]!.headers).get("If-Match")).toBe('"fnd_01:v1"');
  });

  it("sends duplicate_of and accept_risk fields from their dialogs", async () => {
    const fetchMock = mockFetchRoutes([
      { match: "/findings/fnd_01/triage", method: "POST", body: finding },
      ...phase3Routes(),
    ]);
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByText(/FND-0001/);
    await within(screen.getByLabelText("Seen before")).findAllByText("FND-0000");
    fireEvent.click(screen.getByRole("button", { name: "Mark duplicate" }));
    let dialog = await screen.findByRole("dialog", { name: "Mark duplicate" });
    expect(within(dialog).getByRole("combobox", { name: "Duplicate of" })).toHaveValue("fnd_00");
    fireEvent.click(within(dialog).getByRole("button", { name: "Mark duplicate" }));
    await screen.findByText("Marked duplicate");
    fireEvent.click(screen.getByRole("button", { name: "Accept risk" }));
    dialog = await screen.findByRole("dialog", { name: "Accept risk" });
    const accept = within(dialog).getByRole("button", { name: "Accept risk" });
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "low impact" } });
    expect(accept).toBeDisabled();
    fireEvent.change(within(dialog).getByLabelText("Expires on"), {
      target: { value: "2027-01-31" },
    });
    fireEvent.click(accept);
    await screen.findByText("Risk accepted");
    const posts = fetchMock.mock.calls.filter((c) => (c[1]?.method ?? "GET") === "POST");
    expect(JSON.parse(String(posts[0]![1]!.body))).toEqual({
      action: "mark_duplicate",
      reason: null,
      duplicate_of: "fnd_00",
    });
    const risk = JSON.parse(String(posts[1]![1]!.body));
    expect(risk.action).toBe("accept_risk");
    expect(risk.reason).toBe("low impact");
    expect(risk.expires_at).toMatch(/^2027-01-31T/);
  });

  it("tells the user when the finding changed since they read it (412)", async () => {
    mockFetchRoutes([
      {
        match: "/findings/fnd_01/triage",
        method: "POST",
        status: 412,
        body: {
          type: "about:blank",
          title: "Precondition Failed",
          status: 412,
          detail: "The finding changed since you read it; re-read it.",
          error_code: "etag_mismatch",
        },
      },
      ...phase3Routes(),
    ]);
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByText(/FND-0001/);
    fireEvent.click(screen.getByRole("button", { name: "Mark false positive" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark false positive" });
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "x" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Mark false positive" }));
    await screen.findByText("Finding changed since you read it");
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
  });

  it("surfaces the problem detail when the role is not allowed (403)", async () => {
    mockFetchRoutes([
      {
        match: "/findings/fnd_01/triage",
        method: "POST",
        status: 403,
        body: {
          type: "about:blank",
          title: "Forbidden",
          status: 403,
          detail: "Role 'QA Engineer' may not mark false positive this finding (HA-07).",
          error_code: "insufficient_role",
        },
      },
      ...phase3Routes(),
    ]);
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByText(/FND-0001/);
    fireEvent.click(screen.getByRole("button", { name: "Mark false positive" }));
    const dialog = await screen.findByRole("dialog", { name: "Mark false positive" });
    fireEvent.change(within(dialog).getByLabelText("Reason"), { target: { value: "x" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Mark false positive" }));
    await screen.findByText("Mark false positive failed");
    expect(screen.getByText(/may not mark false positive/)).toBeInTheDocument();
  });

  it("filters by status through the API query string", async () => {
    const fetchMock = mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/defects?job=${JOB_ID}` });
    await screen.findByText(/FND-0001/);
    fireEvent.click(screen.getByRole("button", { name: "Rejected" }));
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some((c) =>
          String(c[0]).includes(`/jobs/${JOB_ID}/findings?status=false_positive%2Cduplicate`),
        ),
      ).toBe(true),
    );
    expect(screen.getByRole("button", { name: "Rejected" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

describe("reports screen (SCR-14) findings by priority", () => {
  it("renders the priority table with status and counts", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: `/reports?job=${JOB_ID}` });
    await screen.findByRole("heading", { name: "Findings by priority" });
    const table = screen.getByRole("table", { name: "Findings by priority" });
    expect(within(table).getByText("FND-0001")).toBeInTheDocument();
    expect(within(table).getByText("2.4")).toBeInTheDocument();
    expect(within(table).getByText("Candidate")).toBeInTheDocument();
    expect(screen.getByText("1 open · 0 excluded from gates")).toBeInTheDocument();
  });
});

describe("dashboard open findings", () => {
  it("counts only candidate and reopened findings as open", async () => {
    mockFetchRoutes(phase3Routes());
    renderWithProviders(<App />, { route: "/" });
    await screen.findByText("Open findings · QA-0001");
    expect(screen.getByText("1 recorded, 0 confirmed")).toBeInTheDocument();
  });
});
