import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { Layout } from "@/components/Layout";
import { Dashboard } from "@/routes/Dashboard";
import { LabLayout } from "@/routes/Lab";
import { LabBenchmark } from "@/routes/Lab/Benchmark";
import { LabCapacity } from "@/routes/Lab/Capacity";
import { LabFairness } from "@/routes/Lab/Fairness";
import { LabScaling } from "@/routes/Lab/Scaling";
import { LabSweep } from "@/routes/Lab/Sweep";
import { Roster } from "@/routes/Roster";
import { Constraints } from "@/routes/Rules/Constraints";
import { Shape } from "@/routes/Rules/Shape";
import { Teams } from "@/routes/Rules/Teams";
import { Weights } from "@/routes/Rules/Weights";
import { Blocks } from "@/routes/Setup/Blocks";
import { Doctors } from "@/routes/Setup/Doctors";
import { Overrides } from "@/routes/Setup/Overrides";
import { Preferences } from "@/routes/Setup/Preferences";
import { SetupLayout } from "@/routes/Setup";
import { Templates } from "@/routes/Setup/Templates";
import { When } from "@/routes/Setup/When";
import { Solve } from "@/routes/Solve";
import { SolveLayout } from "@/routes/Solve/Layout";
import { useThemeEffect, useUIStore } from "@/store/ui";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

export function App() {
  useThemeEffect();
  const theme = useUIStore((s) => s.theme);
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Dashboard />} />

            {/* Setup absorbs Rules — both are inputs to the solver. */}
            <Route path="setup" element={<SetupLayout />}>
              <Route index element={<Navigate to="templates" replace />} />
              {/* Per-period (flexible) inputs */}
              <Route path="templates" element={<Templates />} />
              <Route path="when" element={<When />} />
              <Route path="doctors" element={<Doctors />} />
              <Route path="blocks" element={<Blocks />} />
              <Route path="preferences" element={<Preferences />} />
              <Route path="overrides" element={<Overrides />} />
              {/* Department (set-once) inputs — formerly /rules/* */}
              <Route path="shape" element={<Shape />} />
              <Route path="teams" element={<Teams />} />
              <Route path="constraints" element={<Constraints />} />
              <Route path="weights" element={<Weights />} />
            </Route>

            {/* Solve hosts Lab as a secondary sub-section. */}
            <Route path="solve" element={<SolveLayout />}>
              <Route index element={<Solve />} />
              <Route path="lab" element={<LabLayout />}>
                <Route index element={<Navigate to="benchmark" replace />} />
                <Route path="benchmark" element={<LabBenchmark />} />
                <Route path="capacity" element={<LabCapacity />} />
                <Route path="sweep" element={<LabSweep />} />
                <Route path="fairness" element={<LabFairness />} />
                <Route path="scaling" element={<LabScaling />} />
              </Route>
            </Route>

            {/* Roster page hosts Export controls inline. */}
            <Route path="roster" element={<Roster />} />

            {/* Back-compat redirects for the pre-IA-pass routes. */}
            <Route path="rules/*" element={<Navigate to="/setup/shape" replace />} />
            <Route path="lab" element={<Navigate to="/solve/lab/benchmark" replace />} />
            <Route path="lab/*" element={<RedirectLab />} />
            <Route path="export" element={<Navigate to="/roster" replace />} />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Route>
        </Routes>
      </BrowserRouter>
      <Toaster
        position="bottom-right"
        theme={theme}
        richColors
        closeButton
      />
    </QueryClientProvider>
  );
}

/** Map old /lab/<sub> URLs onto /solve/lab/<sub> so any bookmark or
 *  external link a user has saved keeps working after the move. */
function RedirectLab() {
  const path = window.location.pathname.replace(/^\/lab\/?/, "");
  return <Navigate to={`/solve/lab/${path || "benchmark"}`} replace />;
}
