/**
 * /lab/fairness — deep-dive bias audit for one recorded run.
 *
 * Reuses FairnessView over a SingleRunDetail's stored fairness payload,
 * so no extra backend call is needed beyond fetching the batch detail.
 * Per `docs/LAB_TAB_SPEC.md §4`.
 */

import { BookOpen } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import {
  type PerDoctorFairness,
  type SingleRunDetail,
  useBatchDetail,
  useBatchHistory,
  useSessionState,
} from "@/api/hooks";
import { FairnessView } from "@/components/FairnessPanel";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const TIER_COLORS: Record<string, string> = {
  junior: "#6366f1",      // indigo-500
  senior: "#14b8a6",      // teal-500
  consultant: "#f59e0b",  // amber-500
};

export function LabFairness() {
  const history = useBatchHistory();
  const { data: sessionState } = useSessionState();
  const [batchId, setBatchId] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);

  const effectiveBatch = batchId ?? history.data?.[0]?.batch_id ?? null;
  const detail = useBatchDetail(effectiveBatch);

  const runs: Array<[string, SingleRunDetail]> = useMemo(() => {
    if (!detail.data) return [];
    return Object.entries(detail.data.details);
  }, [detail.data]);

  const effectiveRun: SingleRunDetail | null = useMemo(() => {
    if (runs.length === 0) return null;
    if (runId && detail.data?.details[runId]) return detail.data.details[runId];
    return runs[0][1];
  }, [runs, runId, detail.data]);

  const tierLabels = sessionState?.tier_labels ?? {
    junior: "Junior",
    senior: "Senior",
    consultant: "Consultant",
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>Run picker</CardTitle>
          <CardDescription>
            Pick any cell from a recent batch to see its per-tier + per-
            individual bias metrics. Source of truth: the SingleRunDetail
            already stored by the batch runner.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-xs">
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              Batch
            </span>
            <select
              className="mt-1 h-8 w-full rounded-md border border-slate-300 bg-white px-2 dark:border-slate-700 dark:bg-slate-900"
              value={effectiveBatch ?? ""}
              onChange={(e) => {
                setBatchId(e.target.value || null);
                setRunId(null);
              }}
            >
              <option value="" disabled>
                Pick a batch…
              </option>
              {(history.data ?? []).map((h) => (
                <option key={h.batch_id} value={h.batch_id}>
                  {h.instance_label} — {new Date(h.created_at).toLocaleTimeString()}
                </option>
              ))}
            </select>
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              Run (solver × seed)
            </span>
            <select
              className="mt-1 h-8 w-full rounded-md border border-slate-300 bg-white px-2 dark:border-slate-700 dark:bg-slate-900"
              value={runId ?? runs[0]?.[0] ?? ""}
              onChange={(e) => setRunId(e.target.value || null)}
            >
              {runs.map(([rid, d]) => (
                <option key={rid} value={rid}>
                  {d.solver} · seed {d.seed}
                </option>
              ))}
              {runs.length === 0 && <option disabled>No runs recorded yet</option>}
            </select>
          </label>
          {(history.data?.length ?? 0) === 0 && (
            <p className="rounded-md border border-amber-200 bg-amber-50 px-2 py-1.5 text-[11px] text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
              No batches yet. Go to <strong>/lab/benchmark</strong> and run
              one first.
            </p>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <FairnessIntro />
        {effectiveRun ? (
          <>
            <Card>
              <CardHeader>
                <CardTitle>Fairness deep-dive</CardTitle>
                <CardDescription>
                  Solver: <strong>{effectiveRun.solver}</strong> · seed{" "}
                  <strong>{effectiveRun.seed}</strong> · status{" "}
                  <strong>{"status" in (effectiveRun.result as object) ? (effectiveRun.result as { status: string }).status : "—"}</strong>
                </CardDescription>
              </CardHeader>
              <CardContent>
                <FairnessView data={effectiveRun.fairness} tierLabels={tierLabels} />
              </CardContent>
            </Card>
            <IndividualWorkloadChart
              rows={effectiveRun.fairness.per_individual}
              tierLabels={tierLabels}
            />
            <CoveragePanel detail={effectiveRun} />
          </>
        ) : (
          <Card>
            <CardContent className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
              Pick a batch + run on the left to see its fairness audit.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function FairnessIntro() {
  return (
    <Card className="border-indigo-200 bg-indigo-50/50 dark:border-indigo-900 dark:bg-indigo-950/30">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <CardTitle className="text-sm">
            How to answer "is this roster fair?"
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
        <p>
          Pick any recorded run and we break down the workload by
          tier, by individual, by day-of-week, and by consultant
          sub-spec. All numbers are <strong>FTE-normalised</strong> —
          a 0.5-FTE doctor doing half the work is not flagged as
          unfair.
        </p>
        <p>
          <strong>When this is useful:</strong> someone asks "why is
          Dr A on call every other week?", or you want to check a
          solved roster isn't quietly loading one tier at the other's
          expense.
        </p>
        <p>
          <strong>What to look at:</strong>
        </p>
        <ul className="ml-4 list-disc space-y-0.5">
          <li>
            <strong>Gini</strong> — 0 = perfectly equal, 1 = one
            person did everything. Under 0.05 is very even; over 0.25
            is a smell.
          </li>
          <li>
            <strong>CV</strong> (σ / μ) — the same idea in the
            statistic most NRP papers use. Under 0.1 is tight; over
            0.3 is high variance.
          </li>
          <li>
            <strong>Range</strong> — max − min of normalised
            workload. The most intuitive "how bad is the tail?"
            number.
          </li>
          <li>
            <strong>Per-individual Δ</strong> — each doctor's score
            minus their tier median. Over-loaded people float to the
            top, under-loaded to the bottom.
          </li>
        </ul>
      </CardContent>
    </Card>
  );
}

function IndividualWorkloadChart({
  rows,
  tierLabels,
}: {
  rows: PerDoctorFairness[];
  tierLabels: { junior: string; senior: string; consultant: string };
}) {
  // Per-tier median, for the reference lines + delta colouring.
  const medianByTier: Record<string, number> = useMemo(() => {
    const out: Record<string, number> = {};
    for (const tier of ["junior", "senior", "consultant"]) {
      const values = rows
        .filter((r) => r.tier === tier)
        .map((r) => r.fte_normalised)
        .sort((a, b) => a - b);
      if (values.length === 0) continue;
      const mid = values.length >> 1;
      out[tier] =
        values.length % 2 === 0
          ? (values[mid - 1] + values[mid]) / 2
          : values[mid];
    }
    return out;
  }, [rows]);

  // Sort: tier order then Δ (descending), so outliers cluster visually.
  const tierOrder = ["junior", "senior", "consultant"];
  const data = useMemo(() => {
    return [...rows]
      .sort((a, b) => {
        const ta = tierOrder.indexOf(a.tier);
        const tb = tierOrder.indexOf(b.tier);
        if (ta !== tb) return ta - tb;
        return b.delta_from_median - a.delta_from_median;
      })
      .map((r) => ({
        ...r,
        label: r.fte !== 1 ? `${r.doctor} (${r.fte} FTE)` : r.doctor,
      }));
  }, [rows]);

  if (data.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle>Per-individual FTE-normalised workload</CardTitle>
        <CardDescription>
          One bar per doctor, coloured by tier. Dashed lines mark the
          per-tier median. Bars above the line are over-worked relative
          to their tier median; bars below are under-worked. The taller
          the gap, the bigger the Δ.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="mb-2 flex flex-wrap gap-3 text-[11px]">
          {tierOrder.map((t) => (
            <span key={t} className="inline-flex items-center gap-1.5">
              <span
                className="h-3 w-3 rounded-sm"
                style={{ backgroundColor: TIER_COLORS[t] }}
              />
              {tierLabels[t as keyof typeof tierLabels] ?? t}
              {medianByTier[t] != null && (
                <span className="text-slate-500">
                  (median {medianByTier[t].toFixed(0)})
                </span>
              )}
            </span>
          ))}
        </div>
        <div className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data}
              margin={{ top: 8, right: 12, bottom: 40, left: 8 }}
            >
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10 }}
                angle={-45}
                textAnchor="end"
                interval={0}
                height={50}
              />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{ fontSize: 11 }}
                formatter={(v, _n, payload) => {
                  const r = payload?.payload as PerDoctorFairness | undefined;
                  if (!r) return [Number(v).toFixed(1), "workload"];
                  return [
                    `${Number(v).toFixed(1)} (Δ ${r.delta_from_median >= 0 ? "+" : ""}${r.delta_from_median.toFixed(1)})`,
                    "FTE-norm workload",
                  ];
                }}
              />
              {tierOrder.map((t) =>
                medianByTier[t] != null ? (
                  <ReferenceLine
                    key={t}
                    y={medianByTier[t]}
                    stroke={TIER_COLORS[t]}
                    strokeDasharray="4 4"
                    strokeOpacity={0.6}
                  />
                ) : null,
              )}
              <Bar dataKey="fte_normalised" radius={[3, 3, 0, 0]}>
                {data.map((d, i) => (
                  <Cell key={i} fill={TIER_COLORS[d.tier] ?? "#94a3b8"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function CoveragePanel({ detail }: { detail: SingleRunDetail }) {
  const { coverage } = detail;
  const gaps = coverage.station_gaps ?? [];
  return (
    <Card>
      <CardHeader>
        <CardTitle>Coverage audit</CardTitle>
        <CardDescription>
          Shortfall + over-coverage per <code>docs/RESEARCH_METRICS.md §5.1b</code>.
          CP-SAT should land at zero; heuristic baselines often leave gaps.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-xs">
        <div className="flex gap-4">
          <Metric label="Shortfall (total)" value={String(coverage.shortfall_total)} alert={coverage.shortfall_total > 0} />
          <Metric label="Over (total)" value={String(coverage.over_total)} alert={coverage.over_total > 0} />
        </div>
        {gaps.length > 0 && (
          <div>
            <p className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Top {Math.min(10, gaps.length)} gap
              {gaps.length === 1 ? "" : "s"}
            </p>
            <table className="w-full text-[11px]">
              <thead>
                <tr className="text-left text-slate-500 dark:text-slate-400">
                  <th className="py-1">Date</th>
                  <th className="py-1">Station/Sess</th>
                  <th className="py-1 text-right">Required</th>
                  <th className="py-1 text-right">Assigned</th>
                  <th className="py-1 text-right">Shortfall</th>
                </tr>
              </thead>
              <tbody>
                {gaps.slice(0, 10).map((g, i) => (
                  <tr key={i}>
                    <td className="py-0.5 font-mono">{g.date}</td>
                    <td className="py-0.5">{g.station}/{g.session}</td>
                    <td className="py-0.5 text-right">{g.required}</td>
                    <td className="py-0.5 text-right">{g.assigned}</td>
                    <td className="py-0.5 text-right text-amber-700 dark:text-amber-300">
                      {g.shortfall}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function Metric({
  label,
  value,
  alert,
}: {
  label: string;
  value: string;
  alert: boolean;
}) {
  return (
    <div className={"rounded-md border p-2 " + (alert ? "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40" : "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40")}>
      <p className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">{label}</p>
      <p className="mt-0.5 text-lg font-mono font-semibold">{value}</p>
    </div>
  );
}
