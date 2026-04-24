import { NavLink, Outlet } from "react-router-dom";

import { cn } from "@/lib/utils";

const TABS = [
  { to: "templates", label: "Templates" },
  { to: "when", label: "When" },
  { to: "doctors", label: "People" },
  { to: "blocks", label: "Leave & blocks" },
  { to: "preferences", label: "Role preferences" },
  { to: "overrides", label: "Manual overrides" },
];

export function SetupLayout() {
  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Setup</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Per-period inputs. Edits auto-save after 500&nbsp;ms of inactivity.
        </p>
      </header>
      <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
        {TABS.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "border-b-2 px-4 py-2 text-sm font-medium transition-colors",
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
