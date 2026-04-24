import { FlaskConical, HelpCircle } from "lucide-react";
import { NavLink, Outlet, useLocation } from "react-router-dom";

import { cn } from "@/lib/utils";

/**
 * Lab layout — the "harder questions" workspace.
 *
 * Each sub-tab is framed as a single user-facing question rather than
 * a method name. The tab label stays short (one-word nav), but the
 * active tab expands to show its question so the user always knows
 * why they're here.
 */

interface TabMeta {
  to: string;
  label: string;
  /** One-sentence question this tab answers, shown in plain English.
   *  This is the primary communication — the page inside each tab
   *  should mirror this wording so the user keeps their mental model. */
  question: string;
  /** Short cue for the summary card on the Lab landing header. */
  cue: string;
}

const TABS: TabMeta[] = [
  {
    to: "benchmark",
    label: "Benchmark",
    question: "Is the solver's roster actually better than a naïve heuristic?",
    cue: "Compare CP-SAT vs greedy vs random+repair on the same scenario.",
  },
  {
    to: "capacity",
    label: "Capacity",
    question: "Do I have the right number of people for this workload?",
    cue: "Hours vs target per doctor, tier workload shares, team-reduction sweep.",
  },
  {
    to: "sweep",
    label: "Sweep",
    question:
      "Does this one solver setting actually matter for my scenario?",
    cue: "Vary one CP-SAT parameter across a value list, compare objectives + times.",
  },
  {
    to: "fairness",
    label: "Fairness",
    question: "Is the roster fair across tiers and individual people?",
    cue: "Gini, CV, per-doctor delta from tier median, day-of-week load, subspec parity.",
  },
  {
    to: "scaling",
    label: "Scaling",
    question:
      "How will solve time grow if my department (or horizon) gets bigger?",
    cue: "Log-log fit of solve time vs instance size across a synthetic grid.",
  },
];

export function LabLayout() {
  const location = useLocation();
  const active =
    TABS.find((t) => location.pathname.endsWith(`/lab/${t.to}`)) ?? null;

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <header className="space-y-1">
        <div className="flex items-center gap-2">
          <FlaskConical className="h-5 w-5 text-indigo-600 dark:text-indigo-300" />
          <h1 className="text-2xl font-semibold tracking-tight">Lab</h1>
        </div>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          A roster that <em>works</em> is only half the story. The Lab is
          for the harder questions — the ones you can't answer by
          looking at a single solved week. Pick the question below.
        </p>
      </header>

      <LabExplainer active={active} />

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

      {active && (
        <div
          className="flex items-start gap-2 rounded-md border border-indigo-200 bg-indigo-50/70 px-3 py-2 text-sm text-indigo-900 dark:border-indigo-900 dark:bg-indigo-950/40 dark:text-indigo-100"
          role="note"
        >
          <HelpCircle className="mt-0.5 h-4 w-4 flex-shrink-0" />
          <div>
            <span className="text-[10px] font-semibold uppercase tracking-wide opacity-80">
              This tab answers
            </span>
            <p className="mt-0.5 text-sm font-medium leading-tight">
              {active.question}
            </p>
          </div>
        </div>
      )}

      <Outlet />
    </div>
  );
}

/** Compact "what is the Lab" card listed before the nav. Shown on every
 *  sub-tab so a coordinator who lands on /lab/sweep still sees the
 *  context. Uses a dense 5-column table (question → tab) rather than
 *  prose — a coordinator scanning sideways for "the right question to
 *  ask" is exactly the use-case. */
function LabExplainer({ active }: { active: TabMeta | null }) {
  return (
    <div className="rounded-md border border-slate-200 bg-white p-3 text-xs dark:border-slate-800 dark:bg-slate-950">
      <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">
        Pick your question
      </div>
      <ul className="grid gap-1 sm:grid-cols-2 lg:grid-cols-3">
        {TABS.map((t) => {
          const isActive = active?.to === t.to;
          return (
            <li
              key={t.to}
              className={cn(
                "rounded-md border px-2.5 py-1.5 text-[11px] leading-tight transition-colors",
                isActive
                  ? "border-indigo-400 bg-indigo-50 text-indigo-900 dark:border-indigo-500 dark:bg-indigo-950 dark:text-indigo-100"
                  : "border-slate-200 text-slate-700 dark:border-slate-800 dark:text-slate-300",
              )}
            >
              <span className="font-semibold">{t.label}</span>{" "}
              <span className="opacity-80">— {t.cue}</span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
