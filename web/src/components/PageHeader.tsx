import { ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

export interface Crumb {
  label: string;
  to?: string;
}

export function PageHeader({
  crumbs = [],
  title,
  subtitle,
  actions,
  badge,
}: {
  crumbs?: Crumb[];
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  badge?: ReactNode;
}) {
  return (
    <header className="mb-6">
      {crumbs.length ? (
        <nav
          aria-label="Breadcrumb"
          className="mb-2 flex items-center gap-1 text-sm text-slate-500"
        >
          {crumbs.map((c, i) => (
            <span key={i} className="flex items-center gap-1">
              {i > 0 ? <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" /> : null}
              {c.to ? (
                <Link to={c.to} className="hover:text-slate-800">
                  {c.label}
                </Link>
              ) : (
                <span className="text-slate-800">{c.label}</span>
              )}
            </span>
          ))}
        </nav>
      ) : null}
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <h1 className="flex items-center gap-3 text-2xl font-semibold tracking-tight text-slate-900">
            {title}
            {badge}
          </h1>
          {subtitle ? <p className="mt-1 max-w-3xl text-sm text-slate-600">{subtitle}</p> : null}
        </div>
        {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
      </div>
    </header>
  );
}
