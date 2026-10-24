import { Route, Routes } from "react-router-dom";
import { AppShell } from "./layout/AppShell";
import { CompareRunsScreen } from "./screens/CompareRuns";
import { DashboardScreen } from "./screens/Dashboard";
import { FunctionalResultsScreen } from "./screens/FunctionalResults";
import { JobDetailScreen } from "./screens/JobDetail";
import { JobsScreen } from "./screens/Jobs";
import { NewJobScreen } from "./screens/NewJob";
import { PlaceholderScreen } from "./screens/Placeholder";
import { RepositoriesScreen } from "./screens/Repositories";
import { SCREENS } from "./screens/registry";

export function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<DashboardScreen />} />
        <Route path="/repositories" element={<RepositoriesScreen />} />
        <Route path="/jobs" element={<JobsScreen />} />
        <Route path="/jobs/new" element={<NewJobScreen />} />
        <Route path="/jobs/:jobId" element={<JobDetailScreen />} />
        <Route path="/jobs/:jobId/compare/:otherId" element={<CompareRunsScreen />} />
        <Route path="/results/functional" element={<FunctionalResultsScreen />} />
        {SCREENS.filter((s) => s.plannedSlice).map((s) => (
          <Route key={s.id} path={s.path} element={<PlaceholderScreen screen={s} />} />
        ))}
        <Route
          path="*"
          element={
            <div className="p-6 text-sm text-slate-600">
              <h1 className="text-xl font-semibold text-slate-900">Page not found</h1>
            </div>
          }
        />
      </Route>
    </Routes>
  );
}
