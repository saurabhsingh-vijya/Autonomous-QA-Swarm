import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import {
  agentsFixture,
  capabilitiesFixture,
  jobFixture,
  mockFetchEmpty,
  mockFetchRoutes,
  notImplemented,
  projectFixture,
  renderWithProviders,
  repositoryFixture,
} from "../test/utils";

const baseRoutes = () => [
  { match: "/system/capabilities", body: capabilitiesFixture },
  { match: "/projects", body: { items: [projectFixture], next_cursor: null, limit: 50 } },
  { match: "/repositories", body: { items: [repositoryFixture], next_cursor: null, limit: 50 } },
];

beforeEach(() => {
  window.localStorage.clear();
  document.documentElement.setAttribute("data-theme", "dark");
});
afterEach(() => vi.unstubAllGlobals());

describe("shell", () => {
  it("opens the command palette with Ctrl+K and navigates to a screen", async () => {
    mockFetchRoutes(baseRoutes());
    renderWithProviders(<App />, { route: "/" });
    await screen.findByRole("heading", { level: 1, name: /QA health overview/i });
    fireEvent.keyDown(window, { key: "k", ctrlKey: true });
    const palette = await screen.findByRole("dialog", { name: "Command palette" });
    const input = within(palette).getByRole("combobox");
    fireEvent.change(input, { target: { value: "settings" } });
    const option = await within(palette).findByRole("option", { name: /Settings/ });
    fireEvent.click(option);
    await screen.findByRole("heading", { level: 1, name: /Settings/ });
    expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument();
  });

  it("toggles the theme, persists it and sets data-theme on <html>", async () => {
    mockFetchRoutes(baseRoutes());
    renderWithProviders(<App />, { route: "/" });
    const btn = await screen.findByRole("button", { name: "Switch to light theme" });
    fireEvent.click(btn);
    await waitFor(() => expect(document.documentElement.getAttribute("data-theme")).toBe("light"));
    expect(window.localStorage.getItem("raone.theme")).toBe("light");
    expect(screen.getByRole("button", { name: "Switch to dark theme" })).toBeInTheDocument();
  });

  it("shows the runtime chip from the capabilities endpoint", async () => {
    mockFetchRoutes(baseRoutes());
    renderWithProviders(<App />, { route: "/" });
    await screen.findByLabelText(/Runtime status: Local/);
  });
});

describe("dashboard", () => {
  it("renders the first-run guide when there are no repositories", async () => {
    mockFetchEmpty();
    renderWithProviders(<App />, { route: "/" });
    await screen.findByRole("heading", { name: "Get started in three steps" });
    expect(screen.getByRole("link", { name: /Create project/ })).toHaveAttribute(
      "href",
      "/repositories?new=project",
    );
  });

  it("surfaces held jobs under Needs attention without fabricating metrics", async () => {
    mockFetchRoutes([
      ...baseRoutes(),
      { match: "/jobs", body: { items: [jobFixture()], next_cursor: null, limit: 200 } },
    ]);
    renderWithProviders(<App />, { route: "/" });
    await screen.findByText(/held: waiting for the scheduler/);
    expect(screen.getAllByText("No data yet")).toHaveLength(3);
    expect(screen.queryByRole("heading", { name: "Get started in three steps" })).toBeNull();
  });
});

describe("repositories", () => {
  it("creates a project and shows a toast", async () => {
    const fetchMock = mockFetchRoutes([
      ...baseRoutes(),
      {
        match: "/projects",
        method: "POST",
        status: 201,
        body: { ...projectFixture, id: "prj_02", name: "Billing" },
      },
    ]);
    renderWithProviders(<App />, { route: "/repositories" });
    await screen.findByRole("heading", { level: 1, name: "Repositories & Projects" });
    fireEvent.click(screen.getByRole("button", { name: /New project/ }));
    const dialog = await screen.findByRole("dialog", { name: "New project" });
    fireEvent.change(within(dialog).getByLabelText("Name"), { target: { value: "Billing" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create project" }));
    await screen.findByText("Project created");
    const post = fetchMock.mock.calls.find((c) => (c[1]?.method ?? "GET") === "POST");
    expect(post).toBeDefined();
    expect(JSON.parse(String(post![1]!.body))).toEqual({ name: "Billing", description: null });
  });

  it("opens the add-repository dialog from ?new=repository", async () => {
    mockFetchRoutes(baseRoutes());
    renderWithProviders(<App />, { route: "/repositories?new=repository" });
    await screen.findByRole("dialog", { name: "Add repository" });
  });
});

describe("job detail", () => {
  it("renders the 13-stage rail with the held stage and a cancel button for a live job", async () => {
    const job = jobFixture();
    mockFetchRoutes([
      ...baseRoutes(),
      { match: `/jobs/${job.id}`, body: job },
      { match: "/repositories/repo_01", body: repositoryFixture },
    ]);
    renderWithProviders(<App />, { route: `/jobs/${job.id}` });
    await screen.findByRole("heading", { level: 1, name: /QA-0001/ });
    const rail = screen.getByRole("list", { name: "Pipeline stages" });
    const items = within(rail).getAllByRole("listitem");
    expect(items).toHaveLength(13);
    expect(items[0]).toHaveAttribute("data-status", "held");
    expect(items[1]).toHaveAttribute("data-status", "pending");
    expect(screen.getByRole("button", { name: /Cancel job/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /retry/i })).toBeNull();
  });

  it("hides the cancel button for a terminal job", async () => {
    const job = jobFixture({ state: "cancelled", held_reason: null, stages: [] });
    mockFetchRoutes([...baseRoutes(), { match: `/jobs/${job.id}`, body: job }]);
    renderWithProviders(<App />, { route: `/jobs/${job.id}` });
    await screen.findByRole("heading", { level: 1, name: /QA-0001/ });
    expect(screen.queryByRole("button", { name: /Cancel job/ })).toBeNull();
    expect(screen.getByText("No tasks yet")).toBeInTheDocument();
  });
});

describe("settings", () => {
  it("renders capabilities read-only and never shows credentials", async () => {
    mockFetchRoutes(baseRoutes());
    const { container } = renderWithProviders(<App />, { route: "/settings" });
    await screen.findByRole("heading", { level: 1, name: /Settings/ });
    await screen.findByText("RaOne 0.1.0");
    expect(screen.getByText("localhost:5432")).toBeInTheDocument();
    expect(screen.getByText("slice 1c")).toBeInTheDocument();
    expect(container.textContent?.toLowerCase()).not.toContain("password");
    expect(screen.queryByRole("textbox")).toBeNull();
  });
});

describe("not-available screens", () => {
  it("shows the planned slice returned by the API probe", async () => {
    mockFetchRoutes([
      ...baseRoutes(),
      { match: /\/jobs\/job_0{26}\//, body: notImplemented("3c"), status: 501 },
    ]);
    renderWithProviders(<App />, { route: "/mutation" });
    await screen.findByText("Not available in this build");
    await screen.findByText("Planned for slice 3c");
    await screen.findByText("not_implemented");
  });
});

describe("agents", () => {
  it("lists the registry from the API and labels unimplemented agents honestly", async () => {
    mockFetchRoutes([...baseRoutes(), { match: "/system/agents", body: agentsFixture }]);
    renderWithProviders(<App />, { route: "/agent-graph" });
    await screen.findByRole("heading", { level: 1, name: /Agent/ });
    await screen.findByText(/LLM provider: none/);
    expect(screen.getAllByText("not available")).toHaveLength(5);
    expect(screen.getAllByText("idle")).toHaveLength(6);
    expect(screen.queryByText("running")).toBeNull();
  });
});
