import { useEffect, useRef } from "react";

export interface ShortcutHandlers {
  openPalette: () => void;
  openHelp: () => void;
  go: (path: string) => void;
}

export const SHORTCUTS: { keys: string[]; label: string }[] = [
  { keys: ["Ctrl", "K"], label: "Open command palette" },
  { keys: ["?"], label: "Show keyboard shortcuts" },
  { keys: ["g", "d"], label: "Go to Dashboard" },
  { keys: ["g", "j"], label: "Go to Jobs" },
  { keys: ["g", "r"], label: "Go to Repositories" },
  { keys: ["g", "s"], label: "Go to Settings" },
  { keys: ["n"], label: "New QA job" },
  { keys: ["Esc"], label: "Close dialog or palette" },
];

const GO_TARGETS: Record<string, string> = {
  d: "/",
  j: "/jobs",
  r: "/repositories",
  s: "/settings",
};

function isTyping(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  const tag = el.tagName;
  return (
    tag === "INPUT" ||
    tag === "TEXTAREA" ||
    tag === "SELECT" ||
    el.isContentEditable ||
    Boolean(el.closest("[role='dialog']"))
  );
}

export function useGlobalShortcuts(handlers: ShortcutHandlers): void {
  const pendingG = useRef<number | null>(null);
  const h = useRef(handlers);
  h.current = handlers;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        h.current.openPalette();
        return;
      }
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (isTyping(e.target)) return;

      if (pendingG.current !== null) {
        window.clearTimeout(pendingG.current);
        pendingG.current = null;
        const target = GO_TARGETS[e.key.toLowerCase()];
        if (target) {
          e.preventDefault();
          h.current.go(target);
          return;
        }
      }
      if (e.key === "?") {
        e.preventDefault();
        h.current.openHelp();
      } else if (e.key === "g") {
        pendingG.current = window.setTimeout(() => {
          pendingG.current = null;
        }, 1000);
      } else if (e.key === "n") {
        e.preventDefault();
        h.current.go("/jobs/new");
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);
}
