import { screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import {
  JOB_ID,
  checksFixture,
  findingsFixture,
  mockFetchRoutes,
  phase2Routes,
  renderWithProviders,
} from "../test/utils";

const secretScan = {
  ...checksFixture[1],
  id: "chk_secret",
  engine_id: "secret_scan",
  name: "Secret detection",
  outcome: "failed",
  failure_message:
    "1 potential secret(s) found (1 high): aws-access-key-id in config/settings_example.py",
  log_evidence_id: null,
  evidence_ids: [],
};

const securityFinding = {
  ...findingsFixture.items[0],
  id: "fnd_sec_01",
  display_id: "FND-0042",
  category: "security.secret",
  title: "secret_scan failed at config/settings_example.py",
  severity: "high",
  location: {
    file: "config/settings_example.py",
    engine: "secret_scan",
    rule: "aws-access-key-id",
  },
};

afterEach(() => vi.unstubAllGlobals());

describe("SCR-08 Security Testing Center", () => {
  it("shows the job's security engine runs and security findings from the API", async () => {
    mockFetchRoutes([
      { match: `/jobs/${JOB_ID}/checks`, body: [...checksFixture, secretScan] },
      {
        match: `/jobs/${JOB_ID}/findings`,
        body: { items: [...findingsFixture.items, securityFinding], limit: 2 },
      },
      ...phase2Routes(),
    ]);
    renderWithProviders(<App />, { route: "/security" });
    expect(await screen.findByText("Secret detection")).toBeInTheDocument();
    expect(screen.getByText("1 failed")).toBeInTheDocument();
    // Only the security finding is listed, not the api.contract one.
    expect(screen.getByText("FND-0042")).toBeInTheDocument();
    expect(screen.getByText("security.secret")).toBeInTheDocument();
    expect(screen.queryByText(findingsFixture.items[0].display_id)).toBeNull();
    expect(screen.queryByText(/Not available in this build/)).toBeNull();
    expect(screen.getByText(/SAST, dependency and IaC scanners/)).toBeInTheDocument();
    // Non-security engines are not shown here.
    expect(screen.queryByText("python_syntax")).toBeNull();
  });

  it("says plainly when no security engine ran instead of showing an empty table as clean", async () => {
    mockFetchRoutes(phase2Routes());
    renderWithProviders(<App />, { route: "/security" });
    expect(await screen.findByText("No security engine ran for this job")).toBeInTheDocument();
    expect(screen.getByText(/this is not a clean result/)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByText(/No security finding was derived/)).toBeInTheDocument(),
    );
  });
});

describe("SCR-09 Performance Testing Lab", () => {
  it("explains that the probe needs an authorised target and k6 is slice 3b", async () => {
    mockFetchRoutes(phase2Routes());
    renderWithProviders(<App />, { route: "/performance" });
    expect(await screen.findByText("No performance engine ran for this job")).toBeInTheDocument();
    expect(screen.getByText(/slice 3b/)).toBeInTheDocument();
    expect(screen.queryByText(/Not available in this build/)).toBeNull();
  });
});
