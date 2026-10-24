import type { ReactNode } from "react";

export interface KV {
  label: ReactNode;
  value: ReactNode;
  mono?: boolean;
}

export function KeyValue({ items, columns = 1 }: { items: KV[]; columns?: 1 | 2 }) {
  return (
    <dl
      className={`grid gap-x-6 gap-y-2 text-sm ${columns === 2 ? "sm:grid-cols-2" : "grid-cols-1"}`}
    >
      {items.map((it, i) => (
        <div
          key={i}
          className="flex items-baseline justify-between gap-3 border-b border-line pb-1.5"
        >
          <dt className="shrink-0 text-muted">{it.label}</dt>
          <dd className={`min-w-0 truncate text-right text-text ${it.mono ? "mono" : ""}`}>
            {it.value}
          </dd>
        </div>
      ))}
    </dl>
  );
}
