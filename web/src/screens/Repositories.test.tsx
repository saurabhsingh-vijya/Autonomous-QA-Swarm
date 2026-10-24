import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Project } from "../api/types";
import { jsonResponse, renderWithProviders } from "../test/utils";
import { AddRepositoryDialog } from "./Repositories";

const project: Project = {
  id: "prj_01TEST",
  org_id: "org_01TEST",
  org_name: "Northwind Fintech (sample org)",
  name: "Payments Platform",
  description: null,
  created_at: "2026-10-24T08:00:00Z",
  updated_at: "2026-10-24T08:00:00Z",
  version: 1,
};

afterEach(() => vi.unstubAllGlobals());

describe("AddRepositoryDialog", () => {
  it("renders 422 problem+json errors inline, including the /url pointer", async () => {
    const problem = {
      type: "https://raone.dev/problems/repository-url-rejected",
      title: "Repository URL rejected",
      status: 422,
      detail: "Only HTTPS URLs on allow-listed hosts are accepted.",
      instance: "/api/v1/repositories",
      error_code: "repository_url_rejected",
      reason: "scheme_not_https",
      trace_id: "abc123",
      errors: [{ pointer: "/url", code: "scheme_not_https", message: "Scheme must be https." }],
    };
    const fetchMock = vi.fn(async () => jsonResponse(problem, 422, "application/problem+json"));
    vi.stubGlobal("fetch", fetchMock);

    renderWithProviders(
      <AddRepositoryDialog open onClose={() => undefined} projects={[project]} />,
    );
    const user = userEvent.setup();
    await user.type(screen.getByLabelText("Repository URL"), "http://10.0.4.12/internal/repo.git");
    await user.click(screen.getByRole("button", { name: /validate & add/i }));

    await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
    expect(screen.getByRole("alert")).toHaveTextContent("Repository URL rejected");
    expect(screen.getByRole("alert")).toHaveTextContent("repository_url_rejected");
    expect(screen.getByRole("alert")).toHaveTextContent("scheme_not_https");
    expect(screen.getByText("Scheme must be https.", { selector: "p" })).toBeInTheDocument();
    expect(screen.getByLabelText("Repository URL")).toHaveAttribute("aria-invalid", "true");

    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/v1/repositories");
    expect((init.headers as Headers).get("X-Dev-Role")).toBe("QA Lead");
  });
});
