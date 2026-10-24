export function Skeleton({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`rao-pulse rounded bg-raised ${className}`} />;
}

export function SkeletonRows({ rows = 4, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-live="polite" aria-label={label} className="space-y-1.5 p-4">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-8" />
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}
