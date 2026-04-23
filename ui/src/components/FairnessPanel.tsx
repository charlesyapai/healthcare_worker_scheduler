/**
 * Per-tier + per-individual bias audit. Formulae in
 * `docs/RESEARCH_METRICS.md §4`: FTE-normalised weighted workload, then
 * Range, CV, Gini, Std. Gini is our convention; CV is the NRP literature
 * default. Reporting both keeps cross-paper comparisons honest.
 *
 * Lives under the Workload card on /roster. Fires against
 * POST /api/metrics/fairness whenever the viewed roster changes.
 */

import { useEffect, useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  type FairnessPayload,
  type PerDoctorFairness,
  useComputeFairness,
} from "@/api/hooks";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { type AssignmentRow } from "@/store/solve";
import { cn } from "@/lib/utils";

const DOW = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

interface Props {
  assignments: AssignmentRow[];
  tierLabels: { junior: string; senior: string; consultant: string };
}

export function FairnessPanel({ assignments, tierLabels }: Props) {
  const fairness = useComputeFairness();
  const signature = useMemo(() => {
    // Cheap hash of the assignment list so we refetch only when the
    // roster changes. JSON.stringify is fine for this size (< 1 KB per
    // assignment × ≤ 1000 assignments).
    if (assignments.length === 0) return "empty";
    return `${assignments.length}:${assignments[0]?.doctor}:${
      assignments[assignments.length - 1]?.role
    }:${assignments[assignments.length - 1]?.date}`;
  }, [assignments]);

  useEffect(() => {
    if (assignments.length === 0) return;
    fairness.mutate(assignments);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [signature]);

  const data = fairness.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Fairness & bias audit</CardTitle>
        <CardDescription>
          FTE-normalised per-tier metrics. Formulae in{" "}
          <code>docs/RESEARCH_METRICS.md §4</code>. Lower Gini / CV / range
          means a more even distribution of workload.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {fairness.isPending && !data && (
          <p className="text-xs text-slate-500 dark:text-slate-400">Computing…</p>
        )}
        {!data ? null : (
          <>
            <TierCards data={data} tierLabels={tierLabels} />
            <DowLoad data={data} tierLabels={tierLabels} />
            {data.subspec_parity.subspecs &&
              Object.keys(data.subspec_parity.subspecs).length > 0 && (
                <SubspecParity data={data} />
              )}
            <OutlierList data={data} tierLabels={tierLabels} />
          </>
        )}
      </CardContent>
    </Card>
  );
}

function TierCards({
  data,
  tierLabels,
}: {
  data: FairnessPayload;
  tierLabels: { junior: string; senior: string; consultant: string };
}) {
  return (
    <div className="grid gap-3 sm:grid-cols-3">
      {data.tier_order.map((tier) => {
        const summary = data.per_tier[tier];
        if (!summary || summary.n === 0) return null;
        const label = tierLabels[tier as keyof typeof tierLabels] ?? tier;
        return (
          <div
            key={tier}
            className="rounded-md border border-slate-200 p-3 dark:border-slate-800"
          >
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              {label}{" "}
              <span className="font-normal text-slate-400">
                ({summary.n})
              </span>
            </p>
            <Metric
              label="Gini"
              value={summary.gini.toFixed(3)}
              hint={qualitativeGini(summary.gini)}
            />
            <Metric
              label="CV"
              value={summary.cv.toFixed(3)}
              hint={qualitativeCV(summary.cv)}
            />
            <Metric label="Range" value={summary.range.toFixed(0)} />
            <Metric label="Std dev" value={summary.std.toFixed(1)} />
            <Metric label="Mean" value={summary.mean.toFixed(1)} />
          </div>
        );
      })}
    </div>
  );
}

function Metric({
  label,
  value,
  hint,
}: {
  label: string;
  value: string;
  hint?: string;
}) {
  return (
    <div className="mt-1.5 flex items-baseline justify-between gap-2 text-xs">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span className="font-mono text-sm font-medium text-slate-700 dark:text-slate-200">
        {value}
      </span>
      {hint && (
        <span className="text-[10px] text-slate-400 dark:text-slate-500">
          {hint}
        </span>
      )}
    </div>
  );
}

function qualitativeGini(g: number): string {
  if (g < 0.05) return "very even";
  if (g < 0.15) return "even";
  if (g < 0.25) return "uneven";
  return "high bias";
}

function qualitativeCV(cv: number): string {
  if (cv < 0.1) return "tight";
  if (cv < 0.3) return "moderate";
  return "high variance";
}

function DowLoad({
  data,
  tierLabels,
}: {
  data: FairnessPayload;
  tierLabels: { junior: string; senior: string; consultant: string };
}) {
  const rows = DOW.map((dow) => ({
    dow,
    junior: data.dow_load.junior?.[dow] ?? 0,
    senior: data.dow_load.senior?.[dow] ?? 0,
    consultant: data.dow_load.consultant?.[dow] ?? 0,
  }));
  const anyData = rows.some((r) => r.junior + r.senior + r.consultant > 0);
  if (!anyData) return null;
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Load by day of week
      </p>
      <div className="h-48 rounded-md border border-slate-200 p-2 dark:border-slate-800">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={rows} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
            <XAxis dataKey="dow" tick={{ fontSize: 11 }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip contentStyle={{ fontSize: 12 }} />
            <Bar dataKey="junior" stackId="a" fill="#6366f1" name={tierLabels.junior} />
            <Bar dataKey="senior" stackId="a" fill="#14b8a6" name={tierLabels.senior} />
            <Bar
              dataKey="consultant"
              stackId="a"
              fill="#f59e0b"
              name={tierLabels.consultant}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}

function SubspecParity({ data }: { data: FairnessPayload }) {
  const entries = Object.entries(data.subspec_parity.subspecs);
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Consultant subspec parity{" "}
        <span className="font-normal text-slate-400">
          (range {data.subspec_parity.range.toFixed(1)})
        </span>
      </p>
      <div className="rounded-md border border-slate-200 p-2 dark:border-slate-800">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-left text-slate-500 dark:text-slate-400">
              <th className="py-1">Subspec</th>
              <th className="py-1">n</th>
              <th className="py-1 text-right">Mean</th>
              <th className="py-1 text-right">Min</th>
              <th className="py-1 text-right">Max</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(([ss, v]) => (
              <tr key={ss}>
                <td className="py-1 font-medium">{ss}</td>
                <td className="py-1 text-slate-500">{v.n}</td>
                <td className="py-1 text-right font-mono">{v.mean.toFixed(1)}</td>
                <td className="py-1 text-right font-mono">{v.min.toFixed(1)}</td>
                <td className="py-1 text-right font-mono">{v.max.toFixed(1)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function OutlierList({
  data,
  tierLabels,
}: {
  data: FairnessPayload;
  tierLabels: { junior: string; senior: string; consultant: string };
}) {
  // Flag the top and bottom 25% of each tier by delta_from_median.
  const outliers: Array<PerDoctorFairness & { direction: "high" | "low" }> = [];
  for (const tier of data.tier_order) {
    const rows = data.per_individual.filter((r) => r.tier === tier);
    if (rows.length < 4) continue;
    const sorted = [...rows].sort(
      (a, b) => a.delta_from_median - b.delta_from_median,
    );
    const lowCut = sorted[Math.floor(rows.length * 0.25)]?.delta_from_median ?? 0;
    const highCut =
      sorted[Math.ceil(rows.length * 0.75) - 1]?.delta_from_median ?? 0;
    for (const r of rows) {
      if (r.delta_from_median <= lowCut && r.delta_from_median < 0)
        outliers.push({ ...r, direction: "low" });
      else if (r.delta_from_median >= highCut && r.delta_from_median > 0)
        outliers.push({ ...r, direction: "high" });
    }
  }
  if (outliers.length === 0) {
    return (
      <p className="text-xs text-slate-500 dark:text-slate-400">
        No per-individual outliers (tiers with &lt; 4 members skipped).
      </p>
    );
  }
  return (
    <div>
      <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Per-individual outliers (Δ from tier median)
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        {outliers.slice(0, 10).map((r) => {
          const label = tierLabels[r.tier as keyof typeof tierLabels] ?? r.tier;
          return (
            <div
              key={r.doctor}
              className={cn(
                "flex items-center justify-between gap-2 rounded-md border px-2 py-1.5 text-xs",
                r.direction === "high"
                  ? "border-rose-200 bg-rose-50 dark:border-rose-900 dark:bg-rose-950/40"
                  : "border-sky-200 bg-sky-50 dark:border-sky-900 dark:bg-sky-950/40",
              )}
            >
              <div>
                <span className="font-medium">{r.doctor}</span>
                <span className="ml-2 text-slate-500 dark:text-slate-400">
                  {label}
                  {r.fte !== 1 && ` · FTE ${r.fte}`}
                </span>
              </div>
              <span
                className={cn(
                  "font-mono",
                  r.direction === "high"
                    ? "text-rose-700 dark:text-rose-200"
                    : "text-sky-700 dark:text-sky-200",
                )}
              >
                {r.delta_from_median > 0 ? "+" : ""}
                {r.delta_from_median.toFixed(1)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
