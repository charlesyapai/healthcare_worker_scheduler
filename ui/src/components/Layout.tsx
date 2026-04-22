import {
  Calendar,
  ChevronLeft,
  ChevronRight,
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
import { useUIStore } from "@/store/ui";

interface NavItem {
  to: string;
  label: string;
  hint?: string;
  icon: ComponentType<{ className?: string }>;
}

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: Home },
  { to: "/setup", label: "Setup", hint: "per-period", icon: LayoutDashboard },
  { to: "/rules", label: "Rules", hint: "department", icon: Sliders },
  { to: "/solve", label: "Solve", icon: Play },
  { to: "/roster", label: "Roster", icon: Calendar },
  { to: "/export", label: "Export", icon: Download },
];

export function Layout() {
  useGlobalShortcuts();
  return (
    <div className="flex min-h-screen flex-col">
      <TopBar />
      <main className="flex-1 p-4 md:p-6">
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
  const expanded = useUIStore((s) => s.navExpanded);
  const toggle = useUIStore((s) => s.toggleNav);
  return (
    <nav
      aria-label="Primary"
      className={cn(
        "fixed right-3 top-1/2 z-30 hidden -translate-y-1/2 flex-col gap-0.5 rounded-xl border border-slate-200 bg-white/95 p-1.5 shadow-lg backdrop-blur transition-[width] dark:border-slate-800 dark:bg-slate-950/95 md:flex",
        expanded ? "w-40" : "w-11",
      )}
    >
      {NAV.map(({ to, label, hint, icon: Icon }) => (
        <NavLink
          key={to}
          to={to}
          end={to === "/"}
          title={!expanded ? (hint ? `${label} · ${hint}` : label) : undefined}
          className={({ isActive }) =>
            cn(
              "flex items-center gap-2 rounded-md px-2 py-1.5 text-xs transition-colors",
              expanded ? "justify-start" : "justify-center",
              isActive
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800",
            )
          }
        >
          <Icon className="h-4 w-4 flex-shrink-0" />
          {expanded && (
            <span className="flex flex-col leading-tight">
              <span className="font-medium">{label}</span>
              {hint && (
                <span className="text-[10px] text-current opacity-70">{hint}</span>
              )}
            </span>
          )}
        </NavLink>
      ))}
      <button
        type="button"
        onClick={toggle}
        aria-label={expanded ? "Collapse navigation" : "Expand navigation"}
        className="mt-0.5 flex items-center justify-center rounded-md border border-slate-200 bg-slate-50 px-2 py-1.5 text-slate-500 hover:bg-slate-100 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400 dark:hover:bg-slate-800"
      >
        {expanded ? (
          <ChevronRight className="h-3.5 w-3.5" />
        ) : (
          <ChevronLeft className="h-3.5 w-3.5" />
        )}
      </button>
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
