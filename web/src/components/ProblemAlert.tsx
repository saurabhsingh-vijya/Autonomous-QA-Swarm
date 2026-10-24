import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import { toProblem } from "../api/problem";

export function ProblemAlert({ error, children }: { error: unknown; children?: ReactNode }) {
  const p = toProblem(error);
  return (
    <div role="alert" className="rounded-md border border-danger/40 bg-danger/10 p-3 text-sm">
      <div className="flex items-start gap-2.5">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-danger" aria-hidden="true" />
        <div className="min-w-0 flex-1 text-text">
          <p className="font-semibold">
            {p.title}
            {p.status ? <span className="mono ml-2 text-danger">{p.status}</span> : null}
          </p>
          {p.detail ? <p className="mt-1 text-muted">{p.detail}</p> : null}
          <p className="mono mt-1 text-muted">
            error_code: {p.error_code}
            {p.reason ? ` · reason: ${p.reason}` : ""}
            {p.trace_id ? ` · trace_id: ${p.trace_id}` : ""}
          </p>
          {p.errors?.length ? (
            <ul className="mt-2 list-disc space-y-0.5 pl-5 text-muted">
              {p.errors.map((e, i) => (
                <li key={i}>
                  {e.pointer ? <code className="mono text-text">{e.pointer}</code> : null}
                  {e.pointer ? " — " : ""}
                  {e.message}
                </li>
              ))}
            </ul>
          ) : null}
          {children}
        </div>
      </div>
    </div>
  );
}
