/**
 * Setup section layout.
 *
 * Setup absorbed Rules in the 2026-04-25 IA pass — both are inputs to
 * the solver, so keeping them separate at the top level was double-
 * counting. The sub-nav splits them into two visual groups so the
 * user keeps the intuition:
 *
 *   - "This period" — flexible, per-roster inputs (templates, dates,
 *     people, leave, preferences, overrides).
 *   - "Department"  — slow-moving, set-once-per-team inputs (rota
 *     shape, teams & stations, hard rules, hours & weights).
 *
 * Old /rules/* routes redirect into here; see App.tsx.
 */

import { NavLink, Outlet } from "react-router-dom";

import { cn } from "@/lib/utils";

interface Tab {
  to: string;
  label: string;
}

const PERIOD_TABS: Tab[] = [
  { to: "templates", label: "Templates" },
  { to: "when", label: "When" },
  { to: "doctors", label: "People" },
  { to: "blocks", label: "Leave & blocks" },
  { to: "preferences", label: "Role preferences" },
  { to: "overrides", label: "Manual overrides" },
];

const DEPARTMENT_TABS: Tab[] = [
  { to: "shape", label: "Shape" },
  { to: "teams", label: "Teams & stations" },
  { to: "constraints", label: "Rules" },
  { to: "weights", label: "Hours & weights" },
];

export function SetupLayout() {
  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Setup</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Everything the solver needs. Edits auto-save after
          500&nbsp;ms of inactivity.
        </p>
      </header>

      <NavGroup
        label="This period"
        hint="Per-roster inputs — flexible, change every cycle."
        tabs={PERIOD_TABS}
      />
      <NavGroup
        label="Department"
        hint="Set once for your team — rarely changes after that."
        tabs={DEPARTMENT_TABS}
      />

      <div className="pt-2">
        <Outlet />
      </div>
    </div>
  );
}

function NavGroup({
  label,
  hint,
  tabs,
}: {
  label: string;
  hint: string;
  tabs: Tab[];
}) {
  return (
    <div className="space-y-1">
      <div className="flex items-baseline gap-2">
        <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
          {label}
        </span>
        <span className="text-[11px] text-slate-400 dark:text-slate-500">
          {hint}
        </span>
      </div>
      <nav className="flex gap-1 overflow-x-auto border-b border-slate-200 dark:border-slate-800">
        {tabs.map(({ to, label: tabLabel }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                "whitespace-nowrap border-b-2 px-3 py-1.5 text-sm font-medium transition-colors",
                isActive
                  ? "border-indigo-600 text-indigo-700 dark:border-indigo-400 dark:text-indigo-300"
                  : "border-transparent text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-200",
              )
            }
          >
            {tabLabel}
          </NavLink>
        ))}
      </nav>
    </div>
  );
}
