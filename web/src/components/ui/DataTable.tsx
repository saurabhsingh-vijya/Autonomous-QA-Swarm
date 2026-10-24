import { ChevronDown, ChevronUp, ChevronsUpDown } from "lucide-react";
import { Fragment, useMemo, useState, type ReactNode } from "react";

export interface Column<T> {
  key: string;
  header: string;
  render: (row: T) => ReactNode;
  /** Value used for client-side sorting. Omit to make the column unsortable. */
  sortValue?: (row: T) => string | number | null | undefined;
  className?: string;
  align?: "left" | "right";
}

export type SortDir = "asc" | "desc";

export function DataTable<T>({
  columns,
  rows,
  rowKey,
  caption,
  defaultSort,
  renderExpanded,
  dense = true,
  emptyLabel,
}: {
  columns: Column<T>[];
  rows: T[];
  rowKey: (row: T) => string;
  caption?: string;
  defaultSort?: { key: string; dir: SortDir };
  renderExpanded?: (row: T) => ReactNode;
  dense?: boolean;
  emptyLabel?: string;
}) {
  const [sort, setSort] = useState<{ key: string; dir: SortDir } | null>(defaultSort ?? null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const sorted = useMemo(() => {
    if (!sort) return rows;
    const col = columns.find((c) => c.key === sort.key);
    if (!col?.sortValue) return rows;
    const sv = col.sortValue;
    const copy = [...rows];
    copy.sort((a, b) => {
      const va = sv(a);
      const vb = sv(b);
      if (va == null && vb == null) return 0;
      if (va == null) return 1;
      if (vb == null) return -1;
      const cmp =
        typeof va === "number" && typeof vb === "number"
          ? va - vb
          : String(va).localeCompare(String(vb), undefined, { numeric: true });
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return copy;
  }, [rows, sort, columns]);

  const toggleSort = (key: string) => {
    setSort((prev) =>
      prev?.key === key ? { key, dir: prev.dir === "asc" ? "desc" : "asc" } : { key, dir: "asc" },
    );
  };

  const toggleExpand = (key: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  };

  const pad = dense ? "px-3 py-1.5" : "px-4 py-2.5";

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead className="border-b border-line text-xs text-muted">
          <tr>
            {columns.map((c) => {
              const active = sort?.key === c.key;
              const ariaSort = active ? (sort?.dir === "asc" ? "ascending" : "descending") : "none";
              return (
                <th
                  key={c.key}
                  scope="col"
                  aria-sort={c.sortValue ? ariaSort : undefined}
                  className={`${pad} font-medium ${c.align === "right" ? "text-right" : ""} ${c.className ?? ""}`}
                >
                  {c.sortValue ? (
                    <button
                      type="button"
                      onClick={() => toggleSort(c.key)}
                      className="inline-flex items-center gap-1 rounded hover:text-text"
                    >
                      {c.header}
                      {active ? (
                        sort?.dir === "asc" ? (
                          <ChevronUp className="h-3 w-3" aria-hidden="true" />
                        ) : (
                          <ChevronDown className="h-3 w-3" aria-hidden="true" />
                        )
                      ) : (
                        <ChevronsUpDown className="h-3 w-3 opacity-50" aria-hidden="true" />
                      )}
                    </button>
                  ) : (
                    c.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody className="divide-y divide-line">
          {sorted.length === 0 && emptyLabel ? (
            <tr>
              <td colSpan={columns.length} className={`${pad} text-muted`}>
                {emptyLabel}
              </td>
            </tr>
          ) : null}
          {sorted.map((r) => {
            const key = rowKey(r);
            const isOpen = expanded.has(key);
            return (
              <Fragment key={key}>
                <tr
                  className={`rao-transition hover:bg-raised ${renderExpanded ? "cursor-pointer" : ""} ${isOpen ? "bg-raised" : ""}`}
                  tabIndex={renderExpanded ? 0 : undefined}
                  aria-expanded={renderExpanded ? isOpen : undefined}
                  onClick={renderExpanded ? () => toggleExpand(key) : undefined}
                  onKeyDown={
                    renderExpanded
                      ? (e) => {
                          if (e.key === "Enter" || e.key === " ") {
                            e.preventDefault();
                            toggleExpand(key);
                          }
                        }
                      : undefined
                  }
                >
                  {columns.map((c) => (
                    <td
                      key={c.key}
                      className={`${pad} align-middle ${c.align === "right" ? "text-right tabular-nums" : ""} ${c.className ?? ""}`}
                    >
                      {c.render(r)}
                    </td>
                  ))}
                </tr>
                {renderExpanded && isOpen ? (
                  <tr className="bg-canvas">
                    <td colSpan={columns.length} className="px-3 py-3">
                      {renderExpanded(r)}
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
