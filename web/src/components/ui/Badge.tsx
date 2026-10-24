import type { ReactNode } from "react";

export type BadgeTone = "neutral" | "ok" | "warn" | "danger" | "info" | "violet" | "accent";

const TONES: Record<BadgeTone, string> = {
  neutral: "bg-neutral/15 text-muted border-line",
  ok: "bg-ok/15 text-ok border-ok/40",
  warn: "bg-warn/15 text-warn border-warn/40",
  danger: "bg-danger/15 text-danger border-danger/40",
  info: "bg-info/15 text-info border-info/40",
  violet: "bg-violet/15 text-violet border-violet/40",
  accent: "bg-accent/15 text-accent border-accent/40",
};

export function Badge({
  tone = "neutral",
  children,
  className = "",
  title,
}: {
  tone?: BadgeTone;
  children: ReactNode;
  className?: string;
  title?: string;
}) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 rounded border px-1.5 py-px text-2xs font-medium ${TONES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
