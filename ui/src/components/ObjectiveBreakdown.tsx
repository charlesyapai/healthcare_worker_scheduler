/**
 * Plain-English breakdown of how the solver's objective score was built up.
 *
 * The backend returns `penalty_components` as a dict of weighted
 * contributions (already multiplied by the component's weight). We group
 * them by category, recover the raw counts by dividing through by the
 * current weight, and label each group with what it actually means.
 */

import { ChevronDown } from "lucide-react";
import { useMemo, useState } from "react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { cn } from "@/lib/utils";

interface GroupDetail {
  label: string;
  raw: number;
  contribution: number;
}

interface Group {
  key: "workload" | "sessions" | "oncall" | "weekend" | "reporting" | "idle" | "preference" | "unknown";
  label: string;
  blurb: string;
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
  /** Display mode: "full" for the Solve page, "compact" for the Roster sidebar. */
  mode?: "full" | "compact";
}

export function ObjectiveBreakdown({
  objective,
  bestBound,
  components,
  weights,
  tierLabels,
  mode = "full",
}: Props) {
  const groups = useMemo(
    () => buildGroups(components, weights, tierLabels ?? {}),
    [components, weights, tierLabels],
  );

  const total = objective ?? groups.reduce((sum, g) => sum + g.details.reduce((s, d) => s + d.contribution, 0), 0);
  const gap =
    objective != null && bestBound != null && objective > 0
      ? Math.max(0, (objective - bestBound) / objective) * 100
      : null;

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
        <div className="grid gap-3 text-sm sm:grid-cols-3">
          <Metric label="Total objective" value={fmt(total)}>
            Sum of weighted penalties below.
          </Metric>
          <Metric label="Best bound" value={fmt(bestBound ?? null)}>
            Lowest objective the solver could prove is achievable.
          </Metric>
          <Metric
            label="Optimality gap"
            value={gap != null ? `${gap.toFixed(1)} %` : "—"}
          >
            0 % means optimal. Under 5 % is usually good enough.
          </Metric>
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between text-xs font-medium text-slate-600 dark:text-slate-300">
            <span>Category</span>
            <span>Contribution to objective</span>
          </div>
          <ul className="space-y-1">
            {groups
              .filter((g) => g.details.length > 0)
              .sort(
                (a, b) =>
                  b.details.reduce((s, d) => s + d.contribution, 0) -
                  a.details.reduce((s, d) => s + d.contribution, 0),
              )
              .map((g) => (
                <GroupRow key={g.key} group={g} total={total} mode={mode} />
              ))}
          </ul>
          {groups.every((g) => g.details.length === 0) && (
            <p className="py-3 text-xs text-slate-500 dark:text-slate-400">
              No penalty breakdown available. The solver either ran in
              feasibility-only mode, or hasn't completed yet.
            </p>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function GroupRow({ group, total, mode }: { group: Group; total: number; mode: "full" | "compact" }) {
  const [open, setOpen] = useState(mode === "full");
  const contribution = group.details.reduce((s, d) => s + d.contribution, 0);
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
            <p className="text-sm font-semibold tabular-nums">
              {fmt(contribution)}
            </p>
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
          <table className="w-full text-xs">
            <thead className="text-slate-500 dark:text-slate-400">
              <tr>
                <th className="py-1 text-left font-medium">Breakdown</th>
                <th className="py-1 text-right font-medium">
                  Raw {rawUnit(group.key)}
                </th>
                <th className="py-1 text-right font-medium">× weight</th>
                <th className="py-1 text-right font-medium">= contribution</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {group.details.map((d) => (
                <tr key={d.label}>
                  <td className="py-1.5">{d.label}</td>
                  <td className="py-1.5 text-right tabular-nums">
                    {fmt(d.raw)}
                  </td>
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

function Metric({ label, value, children }: { label: string; value: string; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/60 p-3 dark:border-slate-800 dark:bg-slate-900/40">
      <p className="text-[10px] font-medium uppercase tracking-wide text-slate-500 dark:text-slate-400">
        {label}
      </p>
      <p className="mt-1 text-xl font-semibold tabular-nums">{value}</p>
      <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{children}</p>
    </div>
  );
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

  const groups: Record<Group["key"], Group> = {
    idle: {
      key: "idle",
      label: "Idle weekdays",
      blurb:
        "Weekdays where someone had no station, on-call, or excuse (leave / post-call / lieu).",
      weight: weights.idle_weekday,
      details: [],
    },
    workload: {
      key: "workload",
      label: "Workload balance",
      blurb:
        "Primary fairness term. Gap in weighted workload score across doctors within each tier.",
      weight: weights.workload,
      details: [],
    },
    sessions: {
      key: "sessions",
      label: "Session count balance",
      blurb: "Gap in raw AM+PM session counts, per tier.",
      weight: weights.sessions,
      details: [],
    },
    oncall: {
      key: "oncall",
      label: "On-call balance",
      blurb: "Gap in on-call counts across doctors in each tier.",
      weight: weights.oncall,
      details: [],
    },
    weekend: {
      key: "weekend",
      label: "Weekend duty balance",
      blurb: "Gap in weekend duty counts per tier.",
      weight: weights.weekend,
      details: [],
    },
    reporting: {
      key: "reporting",
      label: "Reporting-desk spread",
      blurb: "Consecutive-day pairs on reporting stations (e.g. XR_REPORT).",
      weight: weights.reporting,
      details: [],
    },
    preference: {
      key: "preference",
      label: "Unmet preferences",
      blurb: "Count of 'Prefer AM' / 'Prefer PM' requests the solver could not honour.",
      weight: weights.preference,
      details: [],
    },
    unknown: {
      key: "unknown",
      label: "Other",
      blurb: "Components without a known category.",
      weight: 1,
      details: [],
    },
  };

  for (const [key, value] of Object.entries(components)) {
    let target: Group["key"] = "unknown";
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
      label = "Idle count";
    } else if (key.startsWith("S4")) {
      target = "reporting";
      label = "Consecutive pairs";
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

function rawUnit(key: Group["key"]): string {
  switch (key) {
    case "idle":
      return "weekday-count";
    case "reporting":
      return "pairs";
    case "preference":
      return "count";
    case "workload":
    case "sessions":
    case "oncall":
    case "weekend":
      return "max−min gap";
    default:
      return "count";
  }
}

function fmt(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(1);
}
