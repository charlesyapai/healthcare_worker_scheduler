/**
 * Plain-English breakdown of how the solver's objective score was built up.
 *
 * Backend returns `penalty_components` as weighted contributions (already
 * multiplied by the component's weight). Client groups them by category,
 * recovers the raw counts by dividing through by the current weight, and
 * annotates each category with what it actually means and what the user
 * can do to reduce it.
 */

import { AlertCircle, ChevronDown, Lightbulb, Sparkles } from "lucide-react";
import { useMemo, useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

type GroupKey =
  | "workload"
  | "sessions"
  | "oncall"
  | "weekend"
  | "reporting"
  | "idle"
  | "preference"
  | "unknown";

interface GroupDetail {
  label: string;
  raw: number;
  contribution: number;
}

interface Group {
  key: GroupKey;
  label: string;
  blurb: string;
  rawUnit: string;
  rawMeaning: string;
  advice: string;
  weight: number;
  details: GroupDetail[];
}

interface SoftWeightsLike {
  workload: number;
  sessions: number;
  oncall: number;
  weekend: number;
  reporting: number;
  idle_weekday: number;
  preference: number;
}

interface TierLabels {
  junior?: string;
  senior?: string;
  consultant?: string;
}

interface Props {
  objective: number | null | undefined;
  bestBound: number | null | undefined;
  components: Record<string, number>;
  weights: SoftWeightsLike;
  tierLabels?: TierLabels;
  assignmentCount?: number;
  /** "full" for the Solve page, "compact" for the Roster sidebar (same info, less padding). */
  mode?: "full" | "compact";
}

export function ObjectiveBreakdown({
  objective,
  bestBound,
  components,
  weights,
  tierLabels,
  assignmentCount,
  mode = "full",
}: Props) {
  const groups = useMemo(
    () => buildGroups(components, weights, tierLabels ?? {}),
    [components, weights, tierLabels],
  );

  const total = objective ?? groups.reduce((s, g) => s + groupTotal(g), 0);
  const gap =
    objective != null && bestBound != null && objective > 0
      ? Math.max(0, (objective - bestBound) / objective) * 100
      : null;

  const scored = groups
    .filter((g) => g.details.length > 0 && groupTotal(g) > 0)
    .sort((a, b) => groupTotal(b) - groupTotal(a));
  const topDriver = scored[0];

  return (
    <Card>
      <CardHeader>
        <CardTitle>Score breakdown</CardTitle>
        <CardDescription>
          The solver minimised a weighted sum of soft penalties.{" "}
          <strong>Lower objective = better roster.</strong> Zero would mean
          every soft goal was satisfied.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
          <Metric label="Total objective" value={fmt(total)}>
            Sum of weighted penalties below. Lower is better; 0 = perfect.
          </Metric>
          <Metric label="Best bound" value={fmt(bestBound ?? null)}>
            Lowest objective the solver could prove is achievable. The
            solver tries to push <em>objective</em> down toward this value.
          </Metric>
          <Metric label="Optimality gap" value={gap != null ? `${gap.toFixed(1)} %` : "—"}>
            (objective − bound) ÷ objective. <strong>0 %</strong> means
            the solver proved no better roster exists.{" "}
            <strong>Under 5 %</strong> is usually good enough; above that
            is a sign the time limit cut the search short.
          </Metric>
          <Metric
            label="Assignments"
            value={assignmentCount != null ? fmt(assignmentCount) : "—"}
          >
            Total filled cells across the horizon. Each station-session,
            on-call night, weekend EXT, and weekend consultant role counts
            as one assignment.
          </Metric>
        </div>

        <MainDriversPanel total={total} top={topDriver} scored={scored} />

        <div>
          <p className="mb-1.5 text-xs font-medium text-slate-600 dark:text-slate-300">
            All categories, sorted by contribution
          </p>
          <ul className="space-y-1">
            {scored.map((g) => (
              <GroupRow key={g.key} group={g} total={total} mode={mode} />
            ))}
            {scored.length === 0 && (
              <li className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-xs text-emerald-800 dark:border-emerald-900 dark:bg-emerald-950/40 dark:text-emerald-200">
                <Sparkles className="mr-1 inline h-3 w-3" />
                Zero penalty — every soft goal is satisfied. This roster is as
                good as the solver can do for this configuration.
              </li>
            )}
          </ul>
        </div>
      </CardContent>
    </Card>
  );
}

function MainDriversPanel({
  total,
  top,
  scored,
}: {
  total: number;
  top: Group | undefined;
  scored: Group[];
}) {
  if (!top || total === 0) return null;
  const topTotal = groupTotal(top);
  const pct = (topTotal / total) * 100;
  const runners = scored.slice(1, 3).filter((g) => groupTotal(g) / total > 0.05);

  return (
    <div className="rounded-md border border-indigo-200 bg-indigo-50/60 p-3 dark:border-indigo-900 dark:bg-indigo-950/30">
      <div className="flex items-start gap-2">
        <AlertCircle className="mt-0.5 h-4 w-4 flex-shrink-0 text-indigo-600 dark:text-indigo-300" />
        <div className="text-sm">
          <p>
            <strong>
              {pct.toFixed(0)}% of the score comes from {top.label.toLowerCase()}
            </strong>{" "}
            ({fmt(topTotal)} of {fmt(total)}).
          </p>
          <p className="mt-0.5 text-xs text-slate-600 dark:text-slate-300">
            {top.rawMeaning}
          </p>
          {runners.length > 0 && (
            <p className="mt-1 text-xs text-slate-600 dark:text-slate-300">
              Also contributing:{" "}
              {runners
                .map((g) => `${g.label.toLowerCase()} (${fmt(groupTotal(g))})`)
                .join(", ")}
              .
            </p>
          )}
        </div>
      </div>
      <div className="mt-2 flex items-start gap-2 rounded-md bg-white/60 px-2.5 py-1.5 dark:bg-slate-950/40">
        <Lightbulb className="mt-0.5 h-3.5 w-3.5 flex-shrink-0 text-amber-500" />
        <p className="text-xs text-slate-700 dark:text-slate-200">{top.advice}</p>
      </div>
    </div>
  );
}

function GroupRow({ group, total, mode }: { group: Group; total: number; mode: "full" | "compact" }) {
  const [open, setOpen] = useState(mode === "full");
  const contribution = groupTotal(group);
  const pct = total > 0 ? (contribution / total) * 100 : 0;
  const hasDetails = group.details.length > 1;

  return (
    <li className="rounded-md border border-slate-200 bg-slate-50/50 dark:border-slate-800 dark:bg-slate-900/40">
      <button
        type="button"
        onClick={() => hasDetails && setOpen(!open)}
        className="flex w-full items-center gap-3 px-3 py-2 text-left"
        aria-expanded={open}
        disabled={!hasDetails}
      >
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <p className="text-sm font-medium">{group.label}</p>
            <span className="text-[10px] text-slate-500 dark:text-slate-400">
              weight {group.weight}
            </span>
          </div>
          <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
            {group.blurb}
          </p>
        </div>
        <div className="flex flex-shrink-0 items-center gap-3">
          <div className="text-right">
            <p className="text-sm font-semibold tabular-nums">{fmt(contribution)}</p>
            <p className="text-[10px] text-slate-500 dark:text-slate-400">
              {pct.toFixed(0)}% of total
            </p>
          </div>
          {hasDetails && (
            <ChevronDown
              className={cn(
                "h-4 w-4 flex-shrink-0 text-slate-400 transition-transform",
                open && "rotate-180",
              )}
            />
          )}
        </div>
      </button>
      {open && group.details.length > 0 && (
        <div className="border-t border-slate-200 bg-white px-3 py-2 dark:border-slate-800 dark:bg-slate-950">
          <p className="mb-1.5 text-[11px] text-slate-500 dark:text-slate-400">
            {group.rawMeaning}
          </p>
          <table className="w-full text-xs">
            <thead className="text-slate-500 dark:text-slate-400">
              <tr>
                <th className="py-1 text-left font-medium">Breakdown</th>
                <th className="py-1 text-right font-medium">{group.rawUnit}</th>
                <th className="py-1 text-right font-medium">× weight</th>
                <th className="py-1 text-right font-medium">= contribution</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {group.details.map((d) => (
                <tr key={d.label}>
                  <td className="py-1.5">{d.label}</td>
                  <td className="py-1.5 text-right tabular-nums">{fmt(d.raw)}</td>
                  <td className="py-1.5 text-right tabular-nums text-slate-500">
                    {group.weight}
                  </td>
                  <td className="py-1.5 text-right font-medium tabular-nums">
                    {fmt(d.contribution)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </li>
  );
}

function Metric({
  label,
  value,
  children,
}: {
  label: string;
  value: string;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-900/40">
      <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      <p className="mt-1 text-[11px] leading-tight text-slate-500 dark:text-slate-400">
        {children}
      </p>
    </div>
  );
}

function groupTotal(g: Group): number {
  return g.details.reduce((s, d) => s + d.contribution, 0);
}

function buildGroups(
  components: Record<string, number>,
  weights: SoftWeightsLike,
  tierLabels: TierLabels,
): Group[] {
  const nameTier = (tier: string) => {
    if (tier === "junior") return tierLabels.junior ?? "juniors";
    if (tier === "senior") return tierLabels.senior ?? "seniors";
    if (tier === "consultant") return tierLabels.consultant ?? "consultants";
    return tier;
  };

  const groups: Record<GroupKey, Group> = {
    idle: {
      key: "idle",
      label: "Idle weekdays",
      blurb:
        "Weekdays where someone had no station, on-call, or excuse (leave / post-call / lieu).",
      rawUnit: "idle days",
      rawMeaning:
        "Number of (person, weekday) slots the solver left unassigned despite no valid excuse. A high count here means you have more people than the roster strictly needs — the solver is filling on-call / stations with 'extras' just to avoid the idle penalty.",
      advice:
        "If you actually want people to have days off: switch to Minimal staffing on the Solve page — it turns off this penalty and leaves extras unassigned. If you want everyone fully utilised: widen station eligibility on Setup → People, or bump required_per_session on under-used stations in Rules → Stations.",
      weight: weights.idle_weekday,
      details: [],
    },
    workload: {
      key: "workload",
      label: "Workload balance",
      blurb:
        "Primary fairness term — spread in weighted workload score across people in each tier.",
      rawUnit: "point spread",
      rawMeaning:
        "Difference in weighted-workload points between the busiest and quietest person within each tier (lower = more even).",
      advice:
        "Raise 'Fairness: balance weighted workload' in Rules → Priorities for a flatter distribution, or check whether some people have much narrower station eligibility than others.",
      weight: weights.workload,
      details: [],
    },
    sessions: {
      key: "sessions",
      label: "Session count balance",
      blurb: "Gap in raw AM+PM session counts, per tier.",
      rawUnit: "session gap",
      rawMeaning:
        "Extra AM+PM sessions the busiest person has over the quietest, counted per tier.",
      advice:
        "Raise 'Balance raw session counts' in Rules → Priorities if you want tighter session-count equality.",
      weight: weights.sessions,
      details: [],
    },
    oncall: {
      key: "oncall",
      label: "On-call balance",
      blurb: "Gap in on-call counts across people in each tier.",
      rawUnit: "on-call gap",
      rawMeaning:
        "Extra on-call nights the busiest person has over the quietest, counted per tier.",
      advice:
        "Raise 'Balance on-call counts' in Rules → Priorities. If some people have a max_oncalls cap, the gap may be structural — check Setup → People.",
      weight: weights.oncall,
      details: [],
    },
    weekend: {
      key: "weekend",
      label: "Weekend duty balance",
      blurb: "Gap in weekend duty counts per tier.",
      rawUnit: "weekend gap",
      rawMeaning:
        "Extra weekend duties (EXT + on-call + consult) the busiest person has over the quietest, per tier.",
      advice:
        "Raise 'Balance weekend-duty counts' in Rules → Priorities. Short horizons naturally cap weekend rotation fairness.",
      weight: weights.weekend,
      details: [],
    },
    reporting: {
      key: "reporting",
      label: "Reporting-desk spread",
      blurb: "Consecutive-day pairs on reporting stations (e.g. XR_REPORT).",
      rawUnit: "back-to-back pairs",
      rawMeaning:
        "Number of (person, day) pairs where the same person was on a reporting station two days in a row.",
      advice:
        "Raise 'Spread out reporting-desk duty' in Rules → Priorities, or add more reporting-capable people.",
      weight: weights.reporting,
      details: [],
    },
    preference: {
      key: "preference",
      label: "Unmet preferences",
      blurb: "Count of 'Prefer AM' / 'Prefer PM' requests the solver couldn't honour.",
      rawUnit: "unmet requests",
      rawMeaning:
        "'Prefer AM' / 'Prefer PM' entries from Setup → Blocks that the solver couldn't satisfy.",
      advice:
        "Check whether the preferences conflict with hard constraints (leave, eligibility, post-call). Raise 'Honour positive session preferences' if you want the solver to try harder.",
      weight: weights.preference,
      details: [],
    },
    unknown: {
      key: "unknown",
      label: "Other",
      blurb: "Components without a known category.",
      rawUnit: "count",
      rawMeaning: "Solver-emitted penalty components that don't match a known prefix.",
      advice: "",
      weight: 1,
      details: [],
    },
  };

  for (const [key, value] of Object.entries(components)) {
    let target: GroupKey = "unknown";
    let label = key;
    const tierMatch = key.match(/^S(\d+)_(?:\w+)_(junior|senior|consultant)$/);
    if (tierMatch) {
      const s = tierMatch[1];
      const tier = tierMatch[2];
      label = nameTier(tier);
      if (s === "0") target = "workload";
      else if (s === "1") target = "sessions";
      else if (s === "2") target = "oncall";
      else if (s === "3") target = "weekend";
    } else if (key.startsWith("S5")) {
      target = "idle";
      label = "Idle doctor-weekdays";
    } else if (key.startsWith("S4")) {
      target = "reporting";
      label = "Back-to-back reporting pairs";
    } else if (key.startsWith("S6")) {
      target = "preference";
      label = "Unmet preferences";
    }

    const grp = groups[target];
    const raw = grp.weight > 0 ? value / grp.weight : value;
    grp.details.push({ label, raw, contribution: value });
  }

  return Object.values(groups);
}

function fmt(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(1);
}
