import type { ReactNode } from "react";

export function Kbd({ children }: { children: ReactNode }) {
  return (
    <kbd className="inline-flex h-5 min-w-[20px] items-center justify-center rounded border border-line-strong bg-canvas px-1 font-sans text-2xs text-muted">
      {children}
    </kbd>
  );
}
