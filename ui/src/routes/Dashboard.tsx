/**
 * Landing page.
 *
 * Deliberately short — first-time users should read one screen and
 * know what to do next. Explains what this tool is, the three inputs
 * the solver needs, and the two ways to get started (load a template
 * or build from scratch). The scenario picker lives on Setup →
 * Templates; this page only links to it.
 */

import {
  ArrowRight,
  Calendar,
  CheckCircle2,
  Cog,
  FlaskConical,
  LayoutDashboard,
  PlayCircle,
  Users,
  Wand2,
} from "lucide-react";
import { Link } from "react-router-dom";

import { useHealth, useSessionState } from "@/api/hooks";
import { CharlesAvatar } from "@/components/CharlesAvatar";
import { useSolveStore } from "@/store/solve";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

export function Dashboard() {
  const health = useHealth();
  const state = useSessionState();
  const solve = useSolveStore();
  const doctors = state.data?.doctors ?? [];
  const stations = state.data?.stations ?? [];
  const horizon = state.data?.horizon;
  const hasConfig = doctors.length > 0 && stations.length > 0;
  const hasResult = !!solve.result;

  const nextTo = hasResult
    ? "/roster"
    : hasConfig
      ? "/solve"
      : "/setup/templates";
  const nextLabel = hasResult
    ? "Open roster"
    : hasConfig
      ? "Run the solver"
      : "Start from a template";
  const NextIcon = hasResult
    ? LayoutDashboard
    : hasConfig
      ? PlayCircle
      : Wand2;

  return (
    <div className="mx-auto max-w-4xl space-y-8">
      <Hero />

      <StatusStrip
        hasConfig={hasConfig}
        hasResult={hasResult}
        nDoctors={doctors.length}
        nStations={stations.length}
        nDays={horizon?.n_days ?? 0}
      />

      <section className="grid gap-3 md:grid-cols-[1fr_auto]">
        <Link
          to={nextTo}
          className="group flex items-center justify-between rounded-lg border border-indigo-300 bg-indigo-50 px-5 py-4 transition-colors hover:border-indigo-500 hover:bg-indigo-100 dark:border-indigo-800 dark:bg-indigo-950/40 dark:hover:border-indigo-600 dark:hover:bg-indigo-950"
        >
          <div className="flex items-center gap-3">
            <NextIcon className="h-5 w-5 text-indigo-600 dark:text-indigo-300" />
            <div>
              <p className="text-sm font-semibold text-indigo-900 dark:text-indigo-100">
                {nextLabel}
              </p>
              <p className="text-xs text-indigo-700/80 dark:text-indigo-300/80">
                {hasResult
                  ? "Review, edit, export, or solve again."
                  : hasConfig
                    ? "Everything is configured — press Solve on the next screen."
                    : "Pick one of the 17 bundled templates to populate the whole setup in one click."}
              </p>
            </div>
          </div>
          <ArrowRight className="h-5 w-5 text-indigo-500 transition-transform group-hover:translate-x-0.5 dark:text-indigo-300" />
        </Link>
        {!hasConfig && (
          <Link
            to="/setup/when"
            className="inline-flex items-center justify-center gap-2 rounded-lg border border-slate-200 bg-white px-5 py-4 text-sm font-medium text-slate-700 transition-colors hover:border-slate-400 hover:bg-slate-50 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300 dark:hover:border-slate-500 dark:hover:bg-slate-900"
          >
            Or build from scratch
            <ArrowRight className="h-4 w-4" />
          </Link>
        )}
      </section>

      <HowItWorks />

      <Inputs />

      <p className="text-center text-xs text-slate-400 dark:text-slate-600">
        Backend{" "}
        {health.data
          ? `ok · ${health.data.scheduler_version}`
          : "checking…"}
      </p>
    </div>
  );
}

function Hero() {
  return (
    <header className="space-y-2 pt-2">
      <div className="flex items-center gap-3">
        <CharlesAvatar size="lg" />
        <h1 className="text-3xl font-semibold tracking-tight">
          Charles' Healthcare Roster Scheduler
        </h1>
      </div>
      <p className="text-base text-slate-600 dark:text-slate-400">
        Turn a list of doctors, a set of stations, and a date range into
        a fair, feasible roster — automatically. The solver respects
        statutory rest rules, sub-specialty cover, and the preferences
        you key in, then balances the workload across the team.
      </p>
    </header>
  );
}

function StatusStrip({
  hasConfig,
  hasResult,
  nDoctors,
  nStations,
  nDays,
}: {
  hasConfig: boolean;
  hasResult: boolean;
  nDoctors: number;
  nStations: number;
  nDays: number;
}) {
  if (!hasConfig) {
    return (
      <p className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-600 dark:border-slate-800 dark:bg-slate-900 dark:text-slate-300">
        No configuration loaded yet. Start with a template below, or
        build from scratch.
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-4 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs dark:border-emerald-900 dark:bg-emerald-950/40">
      <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-300" />
      <span className="font-medium text-emerald-900 dark:text-emerald-100">
        Configuration loaded:
      </span>
      <span className="text-emerald-800 dark:text-emerald-200">
        {nDoctors} people · {nStations} stations · {nDays}-day horizon
      </span>
      {hasResult && (
        <span className="ml-auto rounded-full bg-emerald-600 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
          Roster solved
        </span>
      )}
    </div>
  );
}

function HowItWorks() {
  const steps: Array<{
    n: number;
    icon: React.ComponentType<{ className?: string }>;
    title: string;
    body: string;
  }> = [
    {
      n: 1,
      icon: Users,
      title: "Tell us about your team and week",
      body: "Pick a template or enter your own people, stations, and rota pattern. The Shape page lets you describe whether your week is clinic AM/PM, 12h day/night, surgical lists, or 24/7 shifts.",
    },
    {
      n: 2,
      icon: Cog,
      title: "The solver does the hard bit",
      body: "CP-SAT finds an assignment that satisfies every hard rule (rest periods, sub-specialty cover, manual overrides) and then balances the workload across the team as a soft objective.",
    },
    {
      n: 3,
      icon: Calendar,
      title: "Review, edit, export",
      body: "Inspect the roster heatmap, make targeted edits with live validation, and export to JSON / CSV / printable calendar / per-doctor mailto.",
    },
  ];
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        <FlaskConical className="h-3.5 w-3.5" />
        How it works
      </h2>
      <div className="grid gap-3 md:grid-cols-3">
        {steps.map(({ n, icon: Icon, title, body }) => (
          <Card key={n} className="flex flex-col">
            <CardHeader className="pb-2">
              <div className="flex items-center gap-2">
                <div
                  className={cn(
                    "flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full text-[11px] font-bold",
                    "bg-indigo-600 text-white",
                  )}
                >
                  {n}
                </div>
                <Icon className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
                <CardTitle className="text-sm leading-tight">
                  {title}
                </CardTitle>
              </div>
            </CardHeader>
            <CardContent className="text-xs text-slate-600 dark:text-slate-400">
              {body}
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}

function Inputs() {
  const items: Array<{ label: string; detail: string; to: string }> = [
    {
      label: "Who works here",
      detail:
        "Names, tiers (junior / senior / consultant), sub-specialty, eligible stations, FTE, and any max on-call cap.",
      to: "/setup/doctors",
    },
    {
      label: "What needs covering",
      detail:
        "Stations and which tiers can staff them. Decide whether each station runs AM/PM half-sessions or a single Full-day booking.",
      to: "/rules/teams",
    },
    {
      label: "When the roster runs",
      detail:
        "Start date, number of days, public holidays. Plus leave and session preferences per person.",
      to: "/setup/when",
    },
    {
      label: "How strict the rules are",
      detail:
        "Rest rules, weekend cover, on-call frequency cap, weekday utilisation. Pick a preset or tweak each toggle.",
      to: "/rules/constraints",
    },
  ];
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        <LayoutDashboard className="h-3.5 w-3.5" />
        What you'll key in
      </h2>
      <div className="grid gap-2 md:grid-cols-2">
        {items.map((it) => (
          <Link
            key={it.label}
            to={it.to}
            className="group rounded-md border border-slate-200 bg-white p-3 transition-colors hover:border-indigo-300 hover:bg-indigo-50/40 dark:border-slate-800 dark:bg-slate-950 dark:hover:border-indigo-700 dark:hover:bg-indigo-950/30"
          >
            <div className="flex items-start justify-between gap-2">
              <p className="text-sm font-medium">{it.label}</p>
              <ArrowRight className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-slate-400 transition-transform group-hover:translate-x-0.5 dark:text-slate-600" />
            </div>
            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
              {it.detail}
            </p>
          </Link>
        ))}
      </div>
    </section>
  );
}
