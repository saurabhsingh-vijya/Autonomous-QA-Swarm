import { CornerDownLeft, Search } from "lucide-react";
import { useEffect, useId, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useJobs, useProjects, useRepositories } from "../api/hooks";
import { SCREENS } from "../screens/registry";
import { useTheme } from "../theme/ThemeProvider";
import { repoShortName } from "../lib/format";
import { Kbd } from "./ui/Kbd";

interface Item {
  id: string;
  group: "Actions" | "Screens" | "Projects" | "Repositories" | "Jobs";
  label: string;
  hint?: string;
  run: () => void;
}

export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const { toggleTheme, theme } = useTheme();
  const [query, setQuery] = useState("");
  const [index, setIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listId = useId();
  const projects = useProjects();
  const repos = useRepositories();
  const jobs = useJobs({ limit: 50 });

  useEffect(() => {
    if (open) {
      setQuery("");
      setIndex(0);
      window.setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const items = useMemo<Item[]>(() => {
    const go = (path: string) => () => {
      navigate(path);
      onClose();
    };
    const actions: Item[] = [
      {
        id: "a-new-project",
        group: "Actions",
        label: "New project",
        run: go("/repositories?new=project"),
      },
      {
        id: "a-add-repo",
        group: "Actions",
        label: "Add repository",
        run: go("/repositories?new=repository"),
      },
      { id: "a-new-job", group: "Actions", label: "New QA job", run: go("/jobs/new") },
      {
        id: "a-theme",
        group: "Actions",
        label: theme === "dark" ? "Switch to light theme" : "Switch to dark theme",
        run: () => {
          toggleTheme();
          onClose();
        },
      },
    ];
    const screens: Item[] = SCREENS.map((s) => ({
      id: `s-${s.id}`,
      group: "Screens",
      label: s.name,
      hint: s.id,
      run: go(s.path),
    }));
    const projectItems: Item[] = (projects.data?.items ?? []).map((p) => ({
      id: `p-${p.id}`,
      group: "Projects",
      label: p.name,
      hint: `${p.repository_count ?? 0} repositories`,
      run: go("/repositories"),
    }));
    const repoItems: Item[] = (repos.data?.items ?? []).map((r) => ({
      id: `r-${r.id}`,
      group: "Repositories",
      label: repoShortName(r.url),
      hint: r.validation_status,
      run: go(`/jobs/new?repository=${encodeURIComponent(r.id)}`),
    }));
    const jobItems: Item[] = (jobs.data?.items ?? []).map((j) => ({
      id: `j-${j.id}`,
      group: "Jobs",
      label: j.display_id,
      hint: `${j.ref}, ${j.state.replace(/_/g, " ")}`,
      run: go(`/jobs/${j.id}`),
    }));
    return [...actions, ...screens, ...projectItems, ...repoItems, ...jobItems];
  }, [navigate, onClose, projects.data, repos.data, jobs.data, theme, toggleTheme]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return items.slice(0, 40);
    return items
      .filter((i) => `${i.label} ${i.hint ?? ""} ${i.group}`.toLowerCase().includes(q))
      .slice(0, 40);
  }, [items, query]);

  useEffect(() => {
    setIndex(0);
  }, [query]);

  if (!open) return null;

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setIndex((i) => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      filtered[index]?.run();
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  };

  let lastGroup: string | null = null;

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center bg-black/55 p-4 pt-[12vh]">
      <button
        type="button"
        aria-label="Close command palette"
        className="absolute inset-0 cursor-default"
        onClick={onClose}
        tabIndex={-1}
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Command palette"
        data-motion="rise"
        className="relative w-full max-w-xl overflow-hidden rounded-lg border border-line bg-raised shadow-dialog"
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-2 border-b border-line px-3">
          <Search className="h-4 w-4 shrink-0 text-muted" aria-hidden="true" />
          <input
            ref={inputRef}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-activedescendant={filtered[index] ? `${listId}-${filtered[index].id}` : undefined}
            aria-autocomplete="list"
            aria-label="Search screens, projects, repositories and jobs"
            className="h-11 w-full bg-transparent text-sm text-text outline-none placeholder:text-muted/70"
            placeholder="Type a screen, project, repository, job id or action"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
          />
          <Kbd>Esc</Kbd>
        </div>
        <ul id={listId} role="listbox" className="max-h-[50vh] overflow-y-auto py-1">
          {filtered.length === 0 ? (
            <li className="px-3 py-6 text-center text-sm text-muted">No matches for “{query}”.</li>
          ) : null}
          {filtered.map((it, i) => {
            const showGroup = it.group !== lastGroup;
            lastGroup = it.group;
            return (
              <li key={it.id} role="presentation">
                {showGroup ? (
                  <div className="px-3 pb-0.5 pt-2 text-2xs font-medium text-muted">{it.group}</div>
                ) : null}
                <button
                  id={`${listId}-${it.id}`}
                  role="option"
                  aria-selected={i === index}
                  type="button"
                  onMouseEnter={() => setIndex(i)}
                  onClick={it.run}
                  className={`flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left text-sm ${
                    i === index ? "bg-accent/15 text-text" : "text-text"
                  }`}
                >
                  <span className="truncate">{it.label}</span>
                  <span className="flex items-center gap-2 text-2xs text-muted">
                    {it.hint ? <span className="truncate">{it.hint}</span> : null}
                    {i === index ? <CornerDownLeft className="h-3 w-3" aria-hidden="true" /> : null}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
