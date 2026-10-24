/** Per-viewer preferences kept in localStorage. Every access is guarded: storage may be unavailable. */

export const PREF_KEYS = {
  theme: "raone.theme",
  sidebar: "raone.sidebar",
  project: "raone.project",
} as const;

export function readPref(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function writePref(key: string, value: string | null): void {
  try {
    if (value === null) window.localStorage.removeItem(key);
    else window.localStorage.setItem(key, value);
  } catch {
    /* storage unavailable: preference is per-session only */
  }
}
