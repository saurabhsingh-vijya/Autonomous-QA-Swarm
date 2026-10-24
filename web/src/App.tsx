import { Route, Routes } from "react-router-dom";
import { ProjectProvider } from "./app/ProjectContext";
import { ToastProvider } from "./components/ui/Toast";
import { AppShell } from "./layout/AppShell";
import { AgentGraphScreen } from "./screens/AgentGraph";
import { CompareRunsScreen } from "./screens/CompareRuns";
import { DashboardScreen } from "./screens/Dashboard";
import { DefectsScreen } from "./screens/Defects";
import { EngineResultsScreen } from "./screens/EngineResults";
import { ExecutionResultsScreen } from "./screens/ExecutionResults";
import { JobDetailScreen } from "./screens/JobDetail";
import { JobsScreen } from "./screens/Jobs";
import { NewJobScreen } from "./screens/NewJob";
import { NotAvailableScreen } from "./screens/NotAvailable";
import { ReportsScreen } from "./screens/Reports";
import { RepositoriesScreen } from "./screens/Repositories";
import { SettingsScreen } from "./screens/Settings";
import { SCREENS, screenById } from "./screens/registry";
import { ThemeProvider } from "./theme/ThemeProvider";
import { LinkButton } from "./components/ui/Button";

const CUSTOM = new Set([
  "SCR-01",
  "SCR-02",
  "SCR-03",
  "SCR-04",
  "SCR-05",
  "SCR-06",
  "SCR-07",
  "SCR-11",
  "SCR-14",
  "SCR-15",
  "SCR-08",
  "SCR-09",
]);

export function App() {
  return (
    <ThemeProvider>
      <ToastProvider>
        <ProjectProvider>
          <Routes>
            <Route element={<AppShell />}>
              <Route index element={<DashboardScreen />} />
              <Route path="/repositories" element={<RepositoriesScreen />} />
              <Route path="/jobs" element={<JobsScreen />} />
              <Route path="/jobs/new" element={<NewJobScreen />} />
              <Route path="/jobs/:jobId" element={<JobDetailScreen />} />
              <Route path="/jobs/:jobId/compare/:otherId" element={<CompareRunsScreen />} />
              <Route path="/agent-graph" element={<AgentGraphScreen />} />
              <Route
                path="/results/functional"
                element={
                  <ExecutionResultsScreen screen={screenById("SCR-06")} testType="functional" />
                }
              />
              <Route
                path="/results/api"
                element={<ExecutionResultsScreen screen={screenById("SCR-07")} testType="api" />}
              />
              <Route
                path="/security"
                element={<EngineResultsScreen screen={screenById("SCR-08")} kind="security" />}
              />
              <Route
                path="/performance"
                element={<EngineResultsScreen screen={screenById("SCR-09")} kind="performance" />}
              />
              <Route path="/defects" element={<DefectsScreen />} />
              <Route path="/reports" element={<ReportsScreen />} />
              <Route path="/settings" element={<SettingsScreen />} />
              {SCREENS.filter((s) => !CUSTOM.has(s.id)).map((s) => (
                <Route key={s.id} path={s.path} element={<NotAvailableScreen screen={s} />} />
              ))}
              <Route
                path="*"
                element={
                  <div className="py-10 text-sm text-muted">
                    <h1 className="text-xl font-semibold text-text">Page not found</h1>
                    <p className="mt-1">There is no screen at this address.</p>
                    <div className="mt-4">
                      <LinkButton to="/" variant="primary">
                        Go to Dashboard
                      </LinkButton>
                    </div>
                  </div>
                }
              />
            </Route>
          </Routes>
        </ProjectProvider>
      </ToastProvider>
    </ThemeProvider>
  );
}
