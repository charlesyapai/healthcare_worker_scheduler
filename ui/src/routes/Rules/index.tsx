import { NavLink, Outlet } from "react-router-dom";

import { cn } from "@/lib/utils";

const TABS = [
  { to: "tiers", label: "Tiers" },
  { to: "subspecs", label: "Sub-specs" },
  { to: "stations", label: "Stations" },
  { to: "constraints", label: "Rules" },
  { to: "hours", label: "Hours" },
  { to: "fairness", label: "Fairness" },
  { to: "priorities", label: "Priorities" },
];

export function RulesLayout() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Department rules</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Set once per department. Auto-saves after 500&nbsp;ms.
        </p>
      </header>
      <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
        {TABS.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "whitespace-nowrap border-b-2 px-4 py-2 text-sm font-medium transition-colors",
                isActive
                  ? "border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300"
                  : "border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200",
              )
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
