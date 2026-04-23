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

import { AlertCircle, Play } from "lucide-react";
import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
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
    return { v, mean, mn, mx, meanTime, n: objs.length };
  });

  const objRange = (() => {
    const all = cells.map((c) => c.objective).filter((o): o is number => o != null);
    if (all.length === 0) return null;
    return Math.max(...all) - Math.min(...all);
  })();
  const timeRange = (() => {
    const all = cells.map((c) => c.wall_time_s);
    return Math.max(...all) - Math.min(...all);
  })();

  const chartData = cells.map((c) => ({
    param: c.paramValue,
    objective: c.objective,
    wall_time: c.wall_time_s,
    seed: c.seed,
  }));

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Sensitivity to <code>{param}</code></CardTitle>
          <CardDescription>
            ΔZ = <strong>{objRange == null ? "—" : objRange.toFixed(0)}</strong> ·
            ΔT = <strong>{timeRange.toFixed(1)}s</strong>. Big deltas mean
            CP-SAT is sensitive to this parameter on this instance; the
            paper should discuss why.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 dark:text-slate-400">
                <th className="py-1">{param}</th>
                <th className="py-1 text-right">n</th>
                <th className="py-1 text-right">Mean objective</th>
                <th className="py-1 text-right">Min</th>
                <th className="py-1 text-right">Max</th>
                <th className="py-1 text-right">Mean time (s)</th>
              </tr>
            </thead>
            <tbody>
              {valueRows.map((r) => (
                <tr key={r.v}>
                  <td className="py-1 font-mono">{r.v}</td>
                  <td className="py-1 text-right">{r.n}</td>
                  <td className="py-1 text-right font-mono">{r.mean?.toFixed(1) ?? "—"}</td>
                  <td className="py-1 text-right font-mono">{r.mn?.toFixed(0) ?? "—"}</td>
                  <td className="py-1 text-right font-mono">{r.mx?.toFixed(0) ?? "—"}</td>
                  <td className="py-1 text-right font-mono">{r.meanTime.toFixed(1)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Objective by parameter value</CardTitle>
          <CardDescription>
            Each dot is one (value × seed) run.
          </CardDescription>
        </CardHeader>
        <CardContent className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 16, left: 8 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
              <XAxis dataKey="param" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} />
              <Tooltip contentStyle={{ fontSize: 12 }} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Line
                type="monotone"
                dataKey="objective"
                stroke="#4f46e5"
                strokeWidth={2}
                dot={{ r: 3 }}
                name="objective"
              />
            </LineChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>
    </>
  );
}
