import { NavLink, Outlet } from "react-router-dom";

import { cn } from "@/lib/utils";

const TABS = [
  { to: "benchmark", label: "Benchmark" },
  // Sweep / Fairness / Scaling land in Phase 4 per LAB_TAB_SPEC.md.
];

export function LabLayout() {
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Lab</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Research & validation surface. Run comparative benchmarks, measure
          industry-standard reliability metrics, and export reproducibility
          bundles. See <code>docs/VALIDATION_PLAN.md</code>.
        </p>
      </header>
      <nav
        aria-label="Lab sub-tabs"
        className="inline-flex overflow-hidden rounded-md border border-slate-200 dark:border-slate-800"
      >
        {TABS.map((t) => (
          <NavLink
            key={t.to}
            to={t.to}
            className={({ isActive }) =>
              cn(
                "px-4 py-1.5 text-xs font-medium transition-colors",
                isActive
                  ? "bg-indigo-600 text-white"
                  : "bg-white text-slate-700 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800",
              )
            }
          >
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
