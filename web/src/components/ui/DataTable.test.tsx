import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DataTable } from "./DataTable";

const rows = [
  { id: "b", name: "beta", n: 2 },
  { id: "a", name: "alpha", n: 3 },
  { id: "c", name: "gamma", n: 1 },
];

function names() {
  return screen
    .getAllByRole("row")
    .slice(1)
    .map((r) => within(r).getAllByRole("cell")[0].textContent);
}

describe("DataTable", () => {
  it("sorts by a column on header click and exposes aria-sort", () => {
    render(
      <DataTable
        caption="t"
        rows={rows}
        rowKey={(r) => r.id}
        columns={[
          { key: "name", header: "Name", sortValue: (r) => r.name, render: (r) => r.name },
          { key: "n", header: "Count", sortValue: (r) => r.n, render: (r) => r.n },
        ]}
      />,
    );
    expect(names()).toEqual(["beta", "alpha", "gamma"]);
    const header = screen.getByRole("button", { name: /Name/ });
    fireEvent.click(header);
    expect(names()).toEqual(["alpha", "beta", "gamma"]);
    expect(screen.getByRole("columnheader", { name: /Name/ })).toHaveAttribute(
      "aria-sort",
      "ascending",
    );
    fireEvent.click(header);
    expect(names()).toEqual(["gamma", "beta", "alpha"]);
  });

  it("renders the empty label when there are no rows", () => {
    render(
      <DataTable
        caption="t"
        rows={[]}
        rowKey={(r: { id: string }) => r.id}
        emptyLabel="Nothing here"
        columns={[{ key: "id", header: "Id", render: (r) => r.id }]}
      />,
    );
    expect(screen.getByText("Nothing here")).toBeInTheDocument();
  });
});
