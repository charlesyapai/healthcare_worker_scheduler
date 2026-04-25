import {
  Calendar,
  Home,
  LayoutDashboard,
  Play,
} from "lucide-react";
import type { ComponentType } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { CharlesAvatar } from "@/components/CharlesAvatar";
import { DarkModeToggle } from "@/components/DarkModeToggle";
import { SaveIndicator } from "@/components/SaveIndicator";
import { YamlMenu } from "@/components/YamlMenu";
import { useGlobalShortcuts } from "@/lib/keys";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: ComponentType<{ className?: string }>;
}

// Top-level nav consolidated to four sections after the 2026-04-25 IA pass:
// Setup absorbed Rules (department-level + per-period inputs live together);
// Solve hosts Lab as a secondary "harder questions" sub-section; Roster
// hosts Export inline as an action card under the heatmap.
const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: Home },
  { to: "/setup", label: "Setup", icon: LayoutDashboard },
  { to: "/solve", label: "Solve", icon: Play },
  { to: "/roster", label: "Roster", icon: Calendar },
];

export function Layout() {
  useGlobalShortcuts();
  return (
    <div className="flex min-h-screen flex-col">
      <TopBar />
      <main className="flex-1 p-4 md:p-6 md:pr-44">
        <Outlet />
      </main>
      <SideNav />
      <BottomNav />
    </div>
  );
}

function TopBar() {
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
      <div className="flex items-center gap-2">
        <CharlesAvatar size="sm" />
        <span className="text-sm font-semibold">Charles' Healthcare Roster Scheduler</span>
        <span className="ml-2 hidden rounded-full bg-indigo-50 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300 md:inline">
          v2
        </span>
      </div>
      <div className="flex items-center gap-2">
        <SaveIndicator />
        <div className="flex items-center gap-1">
          <YamlMenu />
          <DarkModeToggle />
        </div>
      </div>
    </header>
  );
}

function SideNav() {
  return (
    <nav
      aria-label="Primary"
      className="fixed right-3 top-1/2 z-30 hidden w-36 -translate-y-1/2 flex-col gap-0.5 rounded-xl border border-slate-200 bg-white/95 p-1.5 shadow-lg backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 md:flex"
    >
      {NAV.map(({ to, label, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2 rounded-md px-2.5 py-2 text-sm font-medium transition-colors",
              isActive
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
            )
          }
        >
          <Icon className="h-4 w-4 flex-shrink-0" />
          <span>{label}</span>
        </NavLink>
      ))}
    </nav>
  );
}

function BottomNav() {
  return (
    <nav className="sticky bottom-0 z-10 border-t border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 md:hidden">
      <ul className="grid grid-cols-4">
        {NAV.map(({ to, label, icon: Icon }) => (
          <li key={to} className="contents">
            <NavLink
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex flex-col items-center gap-0.5 py-2 text-[0.68rem]",
                  isActive
                    ? "text-indigo-600 dark:text-indigo-400"
                    : "text-slate-500 dark:text-slate-400",
                )
              }
            >
              <Icon className="h-4 w-4" />
              <span>{label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
