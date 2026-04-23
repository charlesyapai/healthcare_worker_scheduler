import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { Layout } from "@/components/Layout";
import { Dashboard } from "@/routes/Dashboard";
import { Export } from "@/routes/Export";
import { LabLayout } from "@/routes/Lab";
import { LabBenchmark } from "@/routes/Lab/Benchmark";
import { LabFairness } from "@/routes/Lab/Fairness";
import { LabScaling } from "@/routes/Lab/Scaling";
import { LabSweep } from "@/routes/Lab/Sweep";
import { Roster } from "@/routes/Roster";
import { RulesLayout } from "@/routes/Rules";
import { Constraints } from "@/routes/Rules/Constraints";
import { Teams } from "@/routes/Rules/Teams";
import { Weights } from "@/routes/Rules/Weights";
import { Blocks } from "@/routes/Setup/Blocks";
import { Doctors } from "@/routes/Setup/Doctors";
import { Overrides } from "@/routes/Setup/Overrides";
import { SetupLayout } from "@/routes/Setup";
import { When } from "@/routes/Setup/When";
import { Solve } from "@/routes/Solve";
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
            <Route path="setup" element={<SetupLayout />}>
              <Route index element={<Navigate to="when" replace />} />
              <Route path="when" element={<When />} />
              <Route path="doctors" element={<Doctors />} />
              <Route path="blocks" element={<Blocks />} />
              <Route path="overrides" element={<Overrides />} />
            </Route>
            <Route path="rules" element={<RulesLayout />}>
              <Route index element={<Navigate to="teams" replace />} />
              <Route path="teams" element={<Teams />} />
              <Route path="constraints" element={<Constraints />} />
              <Route path="weights" element={<Weights />} />
              {/* Back-compat redirects for old per-concept URLs. */}
              <Route path="tiers" element={<Navigate to="../teams" replace />} />
              <Route path="subspecs" element={<Navigate to="../teams" replace />} />
              <Route path="stations" element={<Navigate to="../teams" replace />} />
              <Route path="hours" element={<Navigate to="../weights" replace />} />
              <Route path="fairness" element={<Navigate to="../weights" replace />} />
              <Route path="priorities" element={<Navigate to="../weights" replace />} />
            </Route>
            <Route path="solve" element={<Solve />} />
            <Route path="roster" element={<Roster />} />
            <Route path="export" element={<Export />} />
            <Route path="lab" element={<LabLayout />}>
              <Route index element={<Navigate to="benchmark" replace />} />
              <Route path="benchmark" element={<LabBenchmark />} />
              <Route path="sweep" element={<LabSweep />} />
              <Route path="fairness" element={<LabFairness />} />
              <Route path="scaling" element={<LabScaling />} />
            </Route>
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
