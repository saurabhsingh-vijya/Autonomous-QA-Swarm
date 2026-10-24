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
