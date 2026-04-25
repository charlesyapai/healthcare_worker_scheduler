/**
 * Solve section layout.
 *
 * The 2026-04-25 IA pass folded Lab in as a secondary sub-section of
 * Solve — the user is here to either *solve* a roster or *probe
 * harder questions about solving*. The sub-nav at the top makes the
 * primary path (Run) visible; Lab is a single click away but does
 * not steal screen space when the user just wants to press Solve.
 *
 * Route shape:
 *   /solve            → Run (default; the existing Solve runner)
 *   /solve/lab/...    → Lab nested layout with its own sub-tabs
 */

import { FlaskConical, Play } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";

export function SolveLayout() {
  const location = useLocation();
  const onLab = location.pathname.startsWith("/solve/lab");

  return (
    <div className="space-y-3">
      <nav
        aria-label="Solve sub-sections"
        className="inline-flex overflow-hidden rounded-md border border-slate-200 bg-white text-xs dark:border-slate-800 dark:bg-slate-950"
      >
        <NavLink
          to="/solve"
          end
          className={({ isActive }) =>
            cn(
              "flex items-center gap-1.5 px-3 py-1.5 font-medium transition-colors",
              isActive && !onLab
                ? "bg-indigo-600 text-white"
                : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
            )
          }
        >
          <Play className="h-3.5 w-3.5" />
          Run
          <span className="ml-1 text-[10px] opacity-70">(main)</span>
        </NavLink>
        <NavLink
          to="/solve/lab/benchmark"
          className={({ isActive }) =>
            cn(
              "flex items-center gap-1.5 border-l border-slate-200 px-3 py-1.5 font-medium transition-colors dark:border-slate-800",
              isActive || onLab
                ? "bg-indigo-600 text-white"
                : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
            )
          }
        >
          <FlaskConical className="h-3.5 w-3.5" />
          Lab
          <span className="ml-1 text-[10px] opacity-70">(harder questions)</span>
        </NavLink>
      </nav>
      <Outlet />
    </div>
  );
}
