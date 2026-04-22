import {
  Calendar,
  Download,
  Home,
  LayoutDashboard,
  Play,
  Settings2,
  Sliders,
} from "lucide-react";
import type { ComponentType } from "react";
import { NavLink, Outlet } from "react-router-dom";

import { DarkModeToggle } from "@/components/DarkModeToggle";
import { SaveIndicator } from "@/components/SaveIndicator";
import { YamlMenu } from "@/components/YamlMenu";
import { useGlobalShortcuts } from "@/lib/keys";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  hint?: string;
  icon: ComponentType<{ className?: string }>;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: Home },
  {
    to: "/setup",
    label: "Setup",
    hint: "per-period",
    icon: LayoutDashboard,
  },
  { to: "/rules", label: "Rules", hint: "once per dept", icon: Sliders },
  { to: "/solve", label: "Solve", icon: Play },
  { to: "/roster", label: "Roster", icon: Calendar },
  { to: "/export", label: "Export", icon: Download },
];

export function Layout() {
  useGlobalShortcuts();
  return (
    <div className="flex min-h-screen flex-col">
      <TopBar />
      <div className="flex flex-1 flex-col md:flex-row">
        <SideNav />
        <main className="flex-1 p-4 md:p-6">
          <Outlet />
        </main>
      </div>
      <BottomNav />
    </div>
  );
}

function TopBar() {
  return (
    <header className="sticky top-0 z-20 flex h-14 items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur dark:border-slate-800 dark:bg-slate-950/90">
      <div className="flex items-center gap-2">
        <Settings2 className="h-5 w-5 text-indigo-600 dark:text-indigo-400" />
        <span className="text-sm font-semibold">Roster Scheduler</span>
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
    <nav className="sticky top-14 hidden h-[calc(100vh-3.5rem)] w-52 border-r border-slate-200 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-950/60 md:block">
      <ul className="flex flex-col gap-1">
        {NAV.map(({ to, label, hint, icon: Icon }) => (
          <li key={to}>
            <NavLink
              to={to}
              end={to === "/"}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors",
                  isActive
                    ? "bg-indigo-600 text-white shadow-sm"
                    : "text-slate-700 hover:bg-slate-200 dark:text-slate-300 dark:hover:bg-slate-800",
                )
              }
            >
              {({ isActive }: { isActive: boolean }) => (
                <>
                  <Icon className="h-4 w-4" />
                  <div className="flex flex-col leading-tight">
                    <span>{label}</span>
                    {hint && (
                      <span
                        className={cn(
                          "text-[10px]",
                          isActive
                            ? "text-indigo-100"
                            : "text-slate-400 dark:text-slate-500",
                        )}
                      >
                        {hint}
                      </span>
                    )}
                  </div>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}

function BottomNav() {
  return (
    <nav className="sticky bottom-0 z-10 border-t border-slate-200 bg-white/95 backdrop-blur dark:border-slate-800 dark:bg-slate-950/95 md:hidden">
      <ul className="grid grid-cols-6">
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
