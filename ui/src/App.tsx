import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { Toaster } from "sonner";

import { Layout } from "@/components/Layout";
import { Dashboard } from "@/routes/Dashboard";
import { Export } from "@/routes/Export";
import { Roster } from "@/routes/Roster";
import { Rules } from "@/routes/Rules";
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
            <Route path="rules" element={<Rules />} />
            <Route path="solve" element={<Solve />} />
            <Route path="roster" element={<Roster />} />
            <Route path="export" element={<Export />} />
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
