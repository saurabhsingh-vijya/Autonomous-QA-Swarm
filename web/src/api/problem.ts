import { ApiError } from "./client";
import type { Problem } from "./types";

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

/** One-line, user-facing summary of an error for toasts. */
export function problemSummary(error: unknown): string {
  const p = toProblem(error);
  return p.detail ?? p.title;
}
