import type { ApiCheck } from "../api/types";

export const QUICK_CHECK: ApiCheck = {
  method: "GET",
  url: "http://localhost:8000/healthz",
  expected_status: 200,
  priority: "P0",
};

/** The local policy only lets read-only methods reach localhost; warn before the API blocks. */
export function checkWarning(c: ApiCheck): string | null {
  try {
    const u = new URL(c.url);
    if (!["localhost", "127.0.0.1"].includes(u.hostname))
      return "Host is not localhost or 127.0.0.1: the local policy will block this check.";
    if (u.protocol !== "http:" && u.protocol !== "https:") return "Only http(s) URLs are allowed.";
    if (u.username || u.password) return "Credentials in URLs are rejected.";
    return null;
  } catch {
    return c.url ? "Not a valid absolute URL." : null;
  }
}

export function parseRequirements(text: string): string[] {
  return text
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);
}
