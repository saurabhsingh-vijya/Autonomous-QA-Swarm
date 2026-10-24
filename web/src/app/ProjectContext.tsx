import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useProjects } from "../api/hooks";
import type { Project } from "../api/types";
import { PREF_KEYS, readPref, writePref } from "../theme/prefs";

interface ProjectContextValue {
  /** Selected project id, or undefined for "all projects". */
  projectId: string | undefined;
  project: Project | undefined;
  projects: Project[];
  isLoading: boolean;
  setProjectId: (id: string | undefined) => void;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ children }: { children: ReactNode }) {
  const query = useProjects();
  const [projectId, setState] = useState<string | undefined>(
    () => readPref(PREF_KEYS.project) ?? undefined,
  );
  const projects = useMemo(() => query.data?.items ?? [], [query.data]);

  // A persisted selection that no longer exists falls back to "all projects".
  useEffect(() => {
    if (query.data && projectId && !projects.some((p) => p.id === projectId)) {
      setState(undefined);
      writePref(PREF_KEYS.project, null);
    }
  }, [query.data, projects, projectId]);

  const setProjectId = useCallback((id: string | undefined) => {
    setState(id);
    writePref(PREF_KEYS.project, id ?? null);
  }, []);

  const value = useMemo<ProjectContextValue>(
    () => ({
      projectId,
      project: projects.find((p) => p.id === projectId),
      projects,
      isLoading: query.isLoading,
      setProjectId,
    }),
    [projectId, projects, query.isLoading, setProjectId],
  );
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useProjectContext(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProjectContext must be used inside ProjectProvider");
  return ctx;
}
