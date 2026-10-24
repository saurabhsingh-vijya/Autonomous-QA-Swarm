import type { PlanNode, TaskRecord, TaskState } from "../api/types";
import { stateLabel } from "./status";

const W = 168;
const H = 48;
const COL = 230;
const ROW = 72;
const PAD = 16;

const FILL: Record<string, string> = {
  succeeded: "rgb(var(--c-ok) / 0.18)",
  running: "rgb(var(--c-info) / 0.18)",
  leased: "rgb(var(--c-accent) / 0.18)",
  failed: "rgb(var(--c-danger) / 0.18)",
  invalid_output: "rgb(var(--c-danger) / 0.18)",
  timed_out: "rgb(var(--c-orange) / 0.18)",
  failed_retryable: "rgb(var(--c-warn) / 0.18)",
  retry_scheduled: "rgb(var(--c-warn) / 0.18)",
  cancelled: "rgb(var(--c-neutral) / 0.25)",
  skipped: "rgb(var(--c-neutral) / 0.25)",
};

const STROKE: Record<string, string> = {
  succeeded: "rgb(var(--c-ok))",
  running: "rgb(var(--c-info))",
  leased: "rgb(var(--c-accent))",
  failed: "rgb(var(--c-danger))",
  invalid_output: "rgb(var(--c-danger))",
  timed_out: "rgb(var(--c-orange))",
  failed_retryable: "rgb(var(--c-warn))",
  retry_scheduled: "rgb(var(--c-warn))",
};

interface Placed {
  node: PlanNode;
  level: number;
  row: number;
  state: TaskState | "not_enqueued";
  attempts: number;
}

/** Longest-path levelling: a node sits one column right of its furthest dependency. */
// eslint-disable-next-line react-refresh/only-export-components
export function layoutPlan(nodes: PlanNode[], tasks: TaskRecord[]): Placed[] {
  const byKey = new Map(nodes.map((n) => [n.key, n]));
  const level = new Map<string, number>();
  const depth = (key: string, seen: Set<string>): number => {
    const cached = level.get(key);
    if (cached !== undefined) return cached;
    if (seen.has(key)) return 0;
    seen.add(key);
    const n = byKey.get(key);
    const deps = n ? [...n.depends_on, ...n.soft_depends_on] : [];
    const d = deps.length ? Math.max(...deps.map((k) => depth(k, seen) + 1)) : 0;
    level.set(key, d);
    return d;
  };
  nodes.forEach((n) => depth(n.key, new Set()));
  const rows = new Map<number, number>();
  return nodes.map((node) => {
    const l = level.get(node.key) ?? 0;
    const r = rows.get(l) ?? 0;
    rows.set(l, r + 1);
    const task = tasks.find((t) => t.task_type === node.task_type);
    return {
      node,
      level: l,
      row: r,
      state: task?.state ?? "not_enqueued",
      attempts: task?.attempt_count ?? 0,
    };
  });
}

/**
 * The plan DAG as an inline SVG. Node colour comes from the persisted task state; a node with
 * no task yet is drawn hollow. Hard dependencies are solid, soft ones dashed.
 */
export function PlanDag({ nodes, tasks }: { nodes: PlanNode[]; tasks: TaskRecord[] }) {
  const placed = layoutPlan(nodes, tasks);
  const cols = Math.max(0, ...placed.map((p) => p.level)) + 1;
  const rows = Math.max(0, ...placed.map((p) => p.row)) + 1;
  const width = PAD * 2 + (cols - 1) * COL + W;
  const height = PAD * 2 + (rows - 1) * ROW + H;
  const pos = new Map(
    placed.map((p) => [p.node.key, { x: PAD + p.level * COL, y: PAD + p.row * ROW }] as const),
  );
  const edges = placed.flatMap((p) =>
    [
      ...p.node.depends_on.map((d) => ({ from: d, to: p.node.key, soft: false })),
      ...p.node.soft_depends_on.map((d) => ({ from: d, to: p.node.key, soft: true })),
    ].filter((e) => pos.has(e.from)),
  );
  const label = placed
    .map((p) => `${p.node.agent_id} ${p.node.key}: ${stateLabel(p.state)}`)
    .join("; ");

  return (
    <div className="overflow-x-auto">
      <svg
        role="img"
        aria-label={`Plan graph: ${label}`}
        width={width}
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        className="block text-text"
        data-testid="plan-dag"
      >
        <defs>
          <marker id="dag-arrow" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto">
            <path d="M0,0 L8,4 L0,8 z" fill="rgb(var(--c-line-strong))" />
          </marker>
        </defs>
        {edges.map((e) => {
          const a = pos.get(e.from)!;
          const b = pos.get(e.to)!;
          const x1 = a.x + W;
          const y1 = a.y + H / 2;
          const x2 = b.x;
          const y2 = b.y + H / 2;
          const mx = (x1 + x2) / 2;
          return (
            <path
              key={`${e.from}-${e.to}`}
              d={`M${x1},${y1} C${mx},${y1} ${mx},${y2} ${x2},${y2}`}
              fill="none"
              stroke="rgb(var(--c-line-strong))"
              strokeWidth={1.5}
              strokeDasharray={e.soft ? "5 4" : undefined}
              markerEnd="url(#dag-arrow)"
              data-edge={e.soft ? "soft" : "hard"}
            />
          );
        })}
        {placed.map((p) => {
          const { x, y } = pos.get(p.node.key)!;
          const fill = FILL[p.state] ?? "rgb(var(--c-surface))";
          const stroke = STROKE[p.state] ?? "rgb(var(--c-line-strong))";
          return (
            <g key={p.node.key} data-node={p.node.key} data-state={p.state}>
              <title>
                {`${p.node.agent_id} · ${p.node.task_type} · ${stateLabel(p.state)}${
                  p.attempts ? ` · ${p.attempts} attempt${p.attempts === 1 ? "" : "s"}` : ""
                }`}
              </title>
              <rect
                x={x}
                y={y}
                width={W}
                height={H}
                rx={6}
                fill={fill}
                stroke={stroke}
                strokeWidth={p.node.critical ? 2 : 1.25}
                strokeDasharray={p.state === "not_enqueued" ? "4 3" : undefined}
              />
              <text x={x + 10} y={y + 19} fontSize={12} fontWeight={600} fill="currentColor">
                {p.node.agent_id} · {p.node.key}
              </text>
              <text x={x + 10} y={y + 36} fontSize={11} fill="rgb(var(--c-muted))">
                {stateLabel(p.state)}
                {p.attempts > 1 ? ` · ${p.attempts} attempts` : ""}
              </text>
            </g>
          );
        })}
      </svg>
      <p className="mt-1 text-2xs text-muted">
        Solid edge: hard dependency (upstream must succeed). Dashed edge: soft dependency (upstream
        must finish). Dashed node: not enqueued yet. Thick border: critical path.
      </p>
    </div>
  );
}
