/**
 * /lab/sweep — parameter sweep over one CP-SAT parameter.
 *
 * Client-side: compose one POST /api/lab/run per parameter value, each
 * with the full seed list. Collect the objective per (value × seed),
 * render a box-style view and a line chart. Per `docs/LAB_TAB_SPEC.md §3`.
 *
 * This tab is the ΔZ_θ / ΔT_θ sensitivity metric from
 * `docs/RESEARCH_METRICS.md §6.2` — how much does the objective (or
 * wall time) move when you perturb one CP-SAT lever.
 */

import { AlertCircle, BookOpen, Play } from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ErrorBar,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";

import { ApiError, apiFetch } from "@/api/client";
import {
  type BatchSummary,
  type RunConfig,
  type SearchBranching,
} from "@/api/hooks";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

type SweepParam =
  | "search_branching"
  | "linearization_level"
  | "random_seed"
  | "num_workers"
  | "time_limit_s";

interface SweepCell {
  paramValue: string;
  seed: number;
  objective: number | null;
  wall_time_s: number;
  status: string;
  self_check_ok: boolean | null;
  coverage_shortfall: number;
}

const PARAM_DEFAULTS: Record<SweepParam, string> = {
  search_branching: "AUTOMATIC, FIXED_SEARCH, PORTFOLIO_SEARCH, LP_SEARCH",
  linearization_level: "0, 1, 2",
  random_seed: "0, 1, 2, 3, 4",
  num_workers: "1, 2, 4",
  time_limit_s: "5, 10, 30",
};

function coerceValue(param: SweepParam, raw: string): string | number {
  if (
    param === "linearization_level" ||
    param === "random_seed" ||
    param === "num_workers"
  ) {
    return Number(raw);
  }
  if (param === "time_limit_s") return Number(raw);
  return raw;
}

function buildRunConfig(
  base: RunConfig,
  param: SweepParam,
  value: string | number,
): RunConfig {
  const next: RunConfig = { ...base };
  if (param === "search_branching") {
    next.search_branching = value as SearchBranching;
  } else if (param === "linearization_level") {
    next.linearization_level = Number(value);
  } else if (param === "random_seed") {
    next.random_seed = Number(value);
  } else if (param === "num_workers") {
    next.num_workers = Number(value);
  } else if (param === "time_limit_s") {
    next.time_limit_s = Number(value);
  }
  return next;
}

const DEFAULT_BASE: RunConfig = {
  time_limit_s: 15,
  num_workers: 1,
  random_seed: 0,
  feasibility_only: false,
  search_branching: "AUTOMATIC",
  linearization_level: 1,
  cp_model_presolve: true,
  optimize_with_core: false,
  use_lns_only: false,
};

export function LabSweep() {
  const [param, setParam] = useState<SweepParam>("search_branching");
  const [valuesText, setValuesText] = useState(PARAM_DEFAULTS["search_branching"]);
  const [seedsText, setSeedsText] = useState("0, 1, 2");
  const [baseTimeLimit, setBaseTimeLimit] = useState(15);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [cells, setCells] = useState<SweepCell[] | null>(null);

  const values = useMemo(
    () =>
      valuesText
        .split(/[\s,]+/)
        .map((s) => s.trim())
        .filter(Boolean),
    [valuesText],
  );
  const seeds = useMemo(() => {
    return seedsText
      .split(/[\s,]+/)
      .map((s) => Number(s))
      .filter((n) => Number.isFinite(n));
  }, [seedsText]);

  const kickoff = async () => {
    if (values.length === 0 || seeds.length === 0) {
      toast.error("Need at least one value and one seed.");
      return;
    }
    setCells(null);
    setRunning(true);
    setProgress({ done: 0, total: values.length });
    const collected: SweepCell[] = [];
    const base: RunConfig = { ...DEFAULT_BASE, time_limit_s: baseTimeLimit };
    try {
      for (const raw of values) {
        const rc = buildRunConfig(base, param, coerceValue(param, raw));
        const body = {
          solvers: ["cpsat"] as const,
          seeds,
          run_config: rc,
        };
        const summary = await apiFetch<BatchSummary>("/api/lab/run", {
          method: "POST",
          body,
        });
        for (const r of summary.runs) {
          collected.push({
            paramValue: String(raw),
            seed: r.seed,
            objective: r.objective,
            wall_time_s: r.wall_time_s,
            status: r.status,
            self_check_ok: r.self_check_ok,
            coverage_shortfall: r.coverage_shortfall,
          });
        }
        setProgress((p) => ({ ...p, done: p.done + 1 }));
      }
      setCells(collected);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Sweep failed");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>Sweep config</CardTitle>
          <CardDescription>
            Varies one CP-SAT parameter across a list of values. CP-SAT only
            (no baselines — sweeps are internal tuning). See{" "}
            <code>docs/RESEARCH_METRICS.md §6.2</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-xs">
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              Parameter
            </span>
            <select
              className="mt-1 h-8 w-full rounded-md border border-slate-300 bg-white px-2 dark:border-slate-700 dark:bg-slate-900"
              value={param}
              onChange={(e) => {
                const p = e.target.value as SweepParam;
                setParam(p);
                setValuesText(PARAM_DEFAULTS[p]);
              }}
            >
              <option value="search_branching">search_branching</option>
              <option value="linearization_level">linearization_level</option>
              <option value="random_seed">random_seed</option>
              <option value="num_workers">num_workers</option>
              <option value="time_limit_s">time_limit_s</option>
            </select>
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              Values (comma / space separated)
            </span>
            <textarea
              className="mt-1 block min-h-[64px] w-full rounded-md border border-slate-300 bg-white p-2 font-mono text-[11px] dark:border-slate-700 dark:bg-slate-900"
              value={valuesText}
              onChange={(e) => setValuesText(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              Seeds per value
            </span>
            <Input
              className="mt-1 h-8 text-xs"
              value={seedsText}
              onChange={(e) => setSeedsText(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              Time limit per run (s)
            </span>
            <Input
              type="number"
              min={5}
              max={120}
              className="mt-1 h-8 text-right text-xs"
              value={baseTimeLimit}
              onChange={(e) =>
                setBaseTimeLimit(Math.max(5, Math.min(120, Number(e.target.value) || 15)))
              }
            />
          </label>
          <p className="rounded-md border border-indigo-200 bg-indigo-50 p-2 text-[11px] dark:border-indigo-900 dark:bg-indigo-950/40">
            <strong>{values.length * seeds.length}</strong> run
            {values.length * seeds.length === 1 ? "" : "s"} · budget ≤{" "}
            <strong>{values.length * seeds.length * baseTimeLimit}s</strong>.
          </p>
          <Button
            className="w-full"
            onClick={kickoff}
            disabled={running || values.length === 0 || seeds.length === 0}
          >
            <Play className="h-4 w-4" />
            {running ? `Sweeping ${progress.done}/${progress.total}…` : "Run sweep"}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <SweepIntro />
        {cells ? (
          <SweepResults cells={cells} param={param} />
        ) : running ? (
          <Card>
            <CardContent className="flex items-center gap-3 py-6 text-sm text-slate-500 dark:text-slate-400">
              <AlertCircle className="h-4 w-4 text-amber-500" />
              Running batch {progress.done + 1} of {progress.total}. Don't
              close the tab.
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
              Pick a parameter + value list and press <strong>Run sweep</strong> —
              the page will fire one batch per value and aggregate the
              objectives.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function SweepIntro() {
  return (
    <Card className="border-indigo-200 bg-indigo-50/50 dark:border-indigo-900 dark:bg-indigo-950/30">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <CardTitle className="text-sm">How to read a parameter sweep</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
        <p>
          A sweep holds the scenario + every other CP-SAT knob fixed and
          varies <strong>one parameter</strong> across the value list you
          pick. For each value we run a batch of seeds, then compare
          objective + wall-time distributions.
        </p>
        <p>
          <strong>What the charts show:</strong>
        </p>
        <ul className="ml-4 list-disc space-y-0.5">
          <li>
            <strong>Objective bar</strong> — mean objective per parameter
            value. Whiskers span <em>min → max</em> across seeds. A value
            with a low mean AND a short whisker is robustly better.
          </li>
          <li>
            <strong>Time bar</strong> — mean wall time per value. A
            parameter that slashes time without raising objective is a
            free win.
          </li>
          <li>
            <strong>All-runs scatter</strong> — one dot per (value × seed)
            cell. Useful for spotting bimodal behaviour the summary
            table hides.
          </li>
        </ul>
        <p>
          <strong>Headline metrics</strong> at the top of the next card:
          ΔZ_θ (max − min across means) and ΔT_θ (wall-time range). See{" "}
          <code>docs/RESEARCH_METRICS.md §6.2</code>.
        </p>
      </CardContent>
    </Card>
  );
}

function SweepResults({ cells, param }: { cells: SweepCell[]; param: SweepParam }) {
  // Group: parameter value → list of objectives + times.
  const byValue: Record<string, { objectives: number[]; times: number[] }> = {};
  for (const c of cells) {
    const bucket = (byValue[c.paramValue] ??= { objectives: [], times: [] });
    if (c.objective != null) bucket.objectives.push(c.objective);
    bucket.times.push(c.wall_time_s);
  }

  const valueRows = Object.entries(byValue).map(([v, b]) => {
    const objs = b.objectives;
    const mean = objs.length ? objs.reduce((s, x) => s + x, 0) / objs.length : null;
    const mn = objs.length ? Math.min(...objs) : null;
    const mx = objs.length ? Math.max(...objs) : null;
    const meanTime = b.times.length ? b.times.reduce((s, x) => s + x, 0) / b.times.length : 0;
    const timeMin = b.times.length ? Math.min(...b.times) : 0;
    const timeMax = b.times.length ? Math.max(...b.times) : 0;
    return { v, mean, mn, mx, meanTime, timeMin, timeMax, n: objs.length };
  });

  // ΔZ_θ and ΔT_θ from RESEARCH_METRICS §6.2 — the headline sensitivity
  // numbers. ΔZ uses max/min of *means* (per-value) so one outlier seed
  // doesn't inflate the signal; ΔT uses max/min of individual runs
  // since tail-latency matters on CI.
  const means = valueRows.map((r) => r.mean).filter((m): m is number => m != null);
  const deltaZ = means.length >= 2 ? Math.max(...means) - Math.min(...means) : null;
  const allTimes = cells.map((c) => c.wall_time_s);
  const deltaT = allTimes.length >= 2 ? Math.max(...allTimes) - Math.min(...allTimes) : 0;

  // Best value for each metric (lowest mean obj, lowest mean time).
  const bestObjRow = means.length
    ? valueRows.filter((r) => r.mean != null).sort((a, b) => (a.mean! - b.mean!))[0]
    : null;
  const bestTimeRow = valueRows.length
    ? [...valueRows].sort((a, b) => a.meanTime - b.meanTime)[0]
    : null;

  // Bar data: mean objective per value. `errorBar` wants `[down, up]`
  // expressed as distances from the mean.
  const objBarData = valueRows
    .filter((r) => r.mean != null)
    .map((r) => ({
      value: r.v,
      mean: r.mean as number,
      errorDown: (r.mean as number) - (r.mn as number),
      errorUp: (r.mx as number) - (r.mean as number),
    }));
  const timeBarData = valueRows.map((r) => ({
    value: r.v,
    meanTime: r.meanTime,
    errorDown: r.meanTime - r.timeMin,
    errorUp: r.timeMax - r.meanTime,
  }));

  // Scatter: one point per run so the user sees individual seeds.
  const scatterData = cells.map((c) => ({
    value: c.paramValue,
    objective: c.objective,
    wall_time: c.wall_time_s,
    seed: c.seed,
  }));

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>
            Sensitivity to <code>{param}</code>
          </CardTitle>
          <CardDescription>
            <strong>ΔZ_θ</strong>{" "}
            = {deltaZ == null ? "—" : deltaZ.toFixed(0)} ·{" "}
            <strong>ΔT_θ</strong> = {deltaT.toFixed(1)}s. Big ΔZ means
            CP-SAT reacts strongly to this parameter on this instance —
            worth discussing in the paper. Near-zero ΔZ means the
            parameter doesn't matter for this problem shape.
            {bestObjRow?.mean != null && (
              <>
                {" "}Best objective: <strong>{bestObjRow.v}</strong>{" "}
                (mean {bestObjRow.mean.toFixed(0)}).
              </>
            )}
            {bestTimeRow && (
              <>
                {" "}Fastest: <strong>{bestTimeRow.v}</strong>{" "}
                (mean {bestTimeRow.meanTime.toFixed(1)}s).
              </>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 dark:text-slate-400">
                <th className="py-1">{param}</th>
                <th className="py-1 text-right">n</th>
                <th className="py-1 text-right">Mean obj</th>
                <th className="py-1 text-right">Min</th>
                <th className="py-1 text-right">Max</th>
                <th className="py-1 text-right">Mean time</th>
              </tr>
            </thead>
            <tbody>
              {valueRows.map((r) => {
                const isBestObj = bestObjRow?.v === r.v && r.mean != null;
                const isBestTime = bestTimeRow?.v === r.v;
                return (
                  <tr key={r.v}>
                    <td className="py-1 font-mono">{r.v}</td>
                    <td className="py-1 text-right">{r.n}</td>
                    <td
                      className={cn(
                        "py-1 text-right font-mono",
                        isBestObj && "font-semibold text-emerald-700 dark:text-emerald-300",
                      )}
                    >
                      {r.mean?.toFixed(1) ?? "—"}
                    </td>
                    <td className="py-1 text-right font-mono">{r.mn?.toFixed(0) ?? "—"}</td>
                    <td className="py-1 text-right font-mono">{r.mx?.toFixed(0) ?? "—"}</td>
                    <td
                      className={cn(
                        "py-1 text-right font-mono",
                        isBestTime && "font-semibold text-emerald-700 dark:text-emerald-300",
                      )}
                    >
                      {r.meanTime.toFixed(1)}s
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>

      {objBarData.length > 0 && (
        <Card>
          <CardHeader>
            <CardTitle>Mean objective per value</CardTitle>
            <CardDescription>
              Whiskers = min → max across the seeds per value. A value
              with the lowest bar AND a short whisker is robustly better
              than the others. Highlighted green bar = current winner.
            </CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={objBarData} margin={{ top: 8, right: 12, bottom: 16, left: 8 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
                <XAxis dataKey="value" tick={{ fontSize: 11 }} interval={0} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip
                  contentStyle={{ fontSize: 11 }}
                  formatter={(v) => Number(v).toFixed(1)}
                />
                {bestObjRow?.mean != null && (
                  <ReferenceLine
                    y={bestObjRow.mean}
                    stroke="#10b981"
                    strokeDasharray="4 4"
                    label={{
                      value: "best",
                      position: "right",
                      style: { fontSize: 10, fill: "#10b981" },
                    }}
                  />
                )}
                <Bar dataKey="mean" radius={[4, 4, 0, 0]}>
                  {objBarData.map((d, i) => (
                    <Cell
                      key={i}
                      fill={d.value === bestObjRow?.v ? "#10b981" : "#4f46e5"}
                    />
                  ))}
                  <ErrorBar
                    dataKey="errorUp"
                    width={4}
                    strokeWidth={1.5}
                    stroke="#64748b"
                    direction="y"
                  />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Mean wall time per value</CardTitle>
          <CardDescription>
            Whiskers = min → max across seeds. A parameter change that
            cuts wall time without raising the objective is a free win.
          </CardDescription>
        </CardHeader>
        <CardContent className="h-56">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={timeBarData} margin={{ top: 8, right: 12, bottom: 16, left: 8 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
              <XAxis dataKey="value" tick={{ fontSize: 11 }} interval={0} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip
                contentStyle={{ fontSize: 11 }}
                formatter={(v) => `${Number(v).toFixed(1)}s`}
              />
              <Bar dataKey="meanTime" radius={[4, 4, 0, 0]}>
                {timeBarData.map((d, i) => (
                  <Cell
                    key={i}
                    fill={d.value === bestTimeRow?.v ? "#10b981" : "#0ea5e9"}
                  />
                ))}
                <ErrorBar
                  dataKey="errorUp"
                  width={4}
                  strokeWidth={1.5}
                  stroke="#64748b"
                  direction="y"
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      {scatterData.some((d) => d.objective != null) && (
        <Card>
          <CardHeader>
            <CardTitle>All runs</CardTitle>
            <CardDescription>
              One dot per (value × seed) — shows individual seed spread
              the summary table hides. A tall column = high seed
              sensitivity; a tight column = robust.
            </CardDescription>
          </CardHeader>
          <CardContent className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <ScatterChart margin={{ top: 8, right: 12, bottom: 16, left: 8 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
                <XAxis
                  dataKey="value"
                  type="category"
                  allowDuplicatedCategory={false}
                  tick={{ fontSize: 11 }}
                />
                <YAxis
                  dataKey="objective"
                  type="number"
                  tick={{ fontSize: 11 }}
                  label={{
                    value: "objective",
                    angle: -90,
                    position: "insideLeft",
                    style: { fontSize: 11, fill: "#64748b" },
                  }}
                />
                <Tooltip contentStyle={{ fontSize: 11 }} />
                <Scatter data={scatterData} fill="#4f46e5" />
              </ScatterChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}
    </>
  );
}
