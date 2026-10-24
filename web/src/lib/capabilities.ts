import type { Capabilities } from "../api/types";
import { CONCEPT_PILL } from "../layout/AppShell";

export const EXECUTION_OFF_PILL = "Execution off — agent checks on supplied inputs only";

/** Mode pill text, driven by GET /system/capabilities. Unknown (loading / unreachable) → concept text. */
export function capabilityPill(
  c:
    | Pick<Capabilities, "execution_enabled" | "repository_code_execution_allowed" | "sandbox">
    | undefined,
): string {
  if (!c || c.execution_enabled === undefined) return CONCEPT_PILL;
  if (!c.execution_enabled) return EXECUTION_OFF_PILL;
  const sandbox = c.sandbox ?? "unknown runtime";
  if (c.repository_code_execution_allowed)
    return `Execution on (${sandbox}) — repository code runs UNSANDBOXED (dev only)`;
  return `Execution on (${sandbox}) — deterministic checks only, no repository code executed`;
}
