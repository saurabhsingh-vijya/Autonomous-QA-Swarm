import { AlertTriangle } from "lucide-react";
import type { ReactNode } from "react";
import { ApiError } from "../api/client";
import type { Problem } from "../api/types";

export function toProblem(error: unknown): Problem {
  if (error instanceof ApiError) return error.problem;
  return {
    type: "about:blank",
    title: "Unexpected error",
    status: 0,
    detail: error instanceof Error ? error.message : String(error),
    error_code: "client_error",
  };
}

export function ProblemAlert({ error, children }: { error: unknown; children?: ReactNode }) {
  const p = toProblem(error);
  return (
    <div
      role="alert"
      className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-900"
    >
      <div className="flex items-start gap-3">
        <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-red-600" aria-hidden="true" />
        <div className="min-w-0 flex-1">
          <p className="font-semibold">
            {p.title}
            {p.status ? (
              <span className="ml-2 font-mono text-xs text-red-700">{p.status}</span>
            ) : null}
          </p>
          {p.detail ? <p className="mt-1">{p.detail}</p> : null}
          <p className="mt-1 font-mono text-xs text-red-700">
            error_code: {p.error_code}
            {p.reason ? ` · reason: ${p.reason}` : ""}
            {p.trace_id ? ` · trace_id: ${p.trace_id}` : ""}
          </p>
          {p.errors?.length ? (
            <ul className="mt-2 list-disc space-y-0.5 pl-5">
              {p.errors.map((e, i) => (
                <li key={i}>
                  {e.pointer ? <code className="font-mono text-xs">{e.pointer}</code> : null}
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
