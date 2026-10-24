import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "./App";
import { SCREENS } from "./screens/registry";
import { mockFetchEmpty, renderWithProviders } from "./test/utils";

// Headings rendered per route (functional screens use their own titles).
const TITLE_BY_ID: Record<string, string> = {
  "SCR-01": "QA Health Overview",
  "SCR-02": "Repositories & Projects",
  "SCR-03": "New QA job",
  "SCR-04": "Live Job Execution",
};

afterEach(() => vi.unstubAllGlobals());

describe("routing", () => {
  it("routes all 15 screens", async () => {
    expect(SCREENS).toHaveLength(15);
    for (const s of SCREENS) {
      mockFetchEmpty();
      const { unmount } = renderWithProviders(<App />, { route: s.path });
      const title = TITLE_BY_ID[s.id] ?? s.name;
      await waitFor(() =>
        expect(
          screen.getByRole("heading", { level: 1, name: new RegExp(title) }),
        ).toBeInTheDocument(),
      );
      expect(screen.getByTestId("mode-pill")).toBeInTheDocument();
      expect(screen.getByText(s.id)).toBeInTheDocument();
      unmount();
    }
  });

  it("shows the empty dashboard state with a repository CTA", async () => {
    mockFetchEmpty();
    renderWithProviders(<App />, { route: "/" });
    await waitFor(() => expect(screen.getByText("No jobs yet")).toBeInTheDocument());
    expect(screen.getByRole("link", { name: "Add a repository" })).toHaveAttribute(
      "href",
      "/repositories",
    );
  });
});
