import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter } from "react-router-dom";
import { vi } from "vitest";

export function renderWithProviders(ui: ReactElement, { route = "/" } = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[route]}>{ui}</MemoryRouter>
    </QueryClientProvider>,
  );
}

export function jsonResponse(body: unknown, status = 200, contentType = "application/json") {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": contentType } });
}

export function emptyPage() {
  return { items: [], next_cursor: null, limit: 50 };
}

/** fetch mock that returns an empty page for every list endpoint. */
export function mockFetchEmpty() {
  const fn = vi.fn(async () => jsonResponse(emptyPage()));
  vi.stubGlobal("fetch", fn);
  return fn;
}

export type Route = {
  /** Substring or regex matched against the request path (without query string). */
  match: string | RegExp;
  method?: string;
  body: unknown;
  status?: number;
  contentType?: string;
};

/**
 * fetch mock that routes by URL. Unmatched requests get an empty page so screens
 * never hang. The problem+json 501 shape mirrors the backend contract table.
 */
export function mockFetchRoutes(routes: Route[]) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const path = url.split("?")[0];
    const method = (init?.method ?? "GET").toUpperCase();
    const r = routes.find(
      (x) =>
        (x.method ?? "GET").toUpperCase() === method &&
        (typeof x.match === "string" ? path.includes(x.match) : x.match.test(path)),
    );
    if (!r) return jsonResponse(emptyPage());
    const ct = r.contentType ?? ((r.status ?? 200) >= 400 ? "application/problem+json" : undefined);
    return jsonResponse(r.body, r.status ?? 200, ct);
  });
  vi.stubGlobal("fetch", fn);
  return fn;
}

export function notImplemented(planned_slice: string, detail = "Not implemented in this build.") {
  return {
    type: "https://raone.dev/problems/not_implemented",
    title: "Not implemented",
    status: 501,
    detail,
    error_code: "not_implemented",
    trace_id: "trace_test",
    planned_slice,
  };
}

export const capabilitiesFixture = {
  product: "RaOne",
  version: "0.1.0",
  local_only: true,
  external_ai_providers: "disabled",
  telemetry_export: "none",
  auth_mode: "dev-headers",
  database: { available: true, status: "ok" },
  storage: { driver: "postgresql+psycopg", host: "localhost", port: 5432, database: "raone" },
  execution_service: { available: false, status: "not deployed", planned_slice: "1c" },
  evidence_store: { available: false, status: "not configured", planned_slice: "1b" },
  model_gateway: { available: false, status: "disabled", planned_slice: "2c" },
  test_engines: [],
  integrations: {
    github: { available: false, status: "not connected", planned_slice: "3e" },
    slack: { available: false, status: "not connected", planned_slice: "3e" },
  },
  limits: {
    job_wall_clock_seconds: 7200,
    task_wall_clock_seconds: 1800,
    lease_ttl_seconds: 60,
    heartbeat_seconds: 15,
    task_max_retries: 2,
  },
};

export const projectFixture = {
  id: "prj_01",
  org_id: "org_01",
  org_name: "Local org",
  name: "Payments",
  description: null,
  created_at: "2026-10-20T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
  version: 1,
  repository_count: 1,
};

export const repositoryFixture = {
  id: "repo_01",
  project_id: "prj_01",
  provider: "github",
  url: "https://github.com/acme/payments",
  default_branch: "main",
  validation_status: "pending_validation",
  validation_note: null,
  last_pinned_sha: null,
  language_support: null,
  created_at: "2026-10-20T10:05:00Z",
};

export function jobFixture(overrides: Record<string, unknown> = {}) {
  return {
    id: "job_01HZZZZZZZZZZZZZZZZZZZZZZZ",
    display_id: "QA-0001",
    state: "validating",
    repository_id: "repo_01",
    project_id: "prj_01",
    ref: "main",
    commit_sha: null,
    profiles: { functional: "standard", security: "quick", performance: "none" },
    held_reason: "intake arrives in slice 1b",
    created_at: "2026-10-21T09:00:00Z",
    updated_at: "2026-10-21T09:00:00Z",
    deadline_at: "2026-10-21T11:00:00Z",
    version: 1,
    stages: [{ stage: "intake_and_pinning", status: "held", note: "intake arrives in slice 1b" }],
    ...overrides,
  };
}
