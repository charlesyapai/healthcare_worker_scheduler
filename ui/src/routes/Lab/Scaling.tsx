/**
 * /lab/scaling — solve-time vs problem size.
 *
 * Drives POST /api/lab/scaling/run against a grid of synthetic
 * instances (doctors × days × seeds), renders a log-log scatter with
 * the server-side power-law fit overlaid, and lets the user plug a
 * hypothetical (n_doctors × n_days) into the fit to project solve
 * time. See `docs/LAB_TAB_SPEC.md §5`.
 *
 * Synthetic instances via `scheduler.instance.make_synthetic` — the
 * tab does NOT touch the current session state. That's intentional:
 * scaling is about solver behaviour on a controlled instance family,
 * not about any particular hospital's roster.
 */

import { AlertCircle, BookOpen, Play } from "lucide-react";
import { useMemo, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  ComposedChart,
  ResponsiveContainer,
  Scatter,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { toast } from "sonner";

import { ApiError, apiFetch } from "@/api/client";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { NumberInput } from "@/components/ui/numberInput";

interface ScalingCell {
  n_doctors: number;
  n_days: number;
  seed: number;
  status: string;
  wall_time_s: number;
  first_feasible_s: number | null;
  objective: number | null;
  n_assignments: number;
  size: number;
}

interface ScalingFit {
  exponent: number | null;
  coefficient: number | null;
  r_squared: number | null;
  n_points: number;
}

interface ScalingResponse {
  batch_id: string;
  created_at: string;
  time_limit_s: number;
  num_workers: number;
  leave_rate: number;
  cells: ScalingCell[];
  fit: ScalingFit;
}

function parseNumbers(s: string): number[] {
  return s
    .split(/[\s,]+/)
    .map((t) => t.trim())
    .filter(Boolean)
    .map(Number)
    .filter((n) => Number.isFinite(n) && n > 0);
}

export function LabScaling() {
  const [doctorsText, setDoctorsText] = useState("10, 15, 20, 30");
  const [daysText, setDaysText] = useState("7, 14");
  const [seedsText, setSeedsText] = useState("0, 1");
  const [timeLimit, setTimeLimit] = useState(10);
  const [numWorkers, setNumWorkers] = useState(1);
  const [leaveRate, setLeaveRate] = useState(0.03);
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [resp, setResp] = useState<ScalingResponse | null>(null);
  const [predictN, setPredictN] = useState(1000);

  const doctors = useMemo(() => parseNumbers(doctorsText), [doctorsText]);
  const days = useMemo(() => parseNumbers(daysText), [daysText]);
  const seeds = useMemo(() => parseNumbers(seedsText), [seedsText]);
  const totalCells = doctors.length * days.length * seeds.length;

  const kickoff = async () => {
    if (doctors.length === 0 || days.length === 0 || seeds.length === 0) {
      toast.error("Need at least one doctor count, one day count, and one seed.");
      return;
    }
    if (totalCells > 40) {
      toast.error(`Grid has ${totalCells} cells (max 40 per run).`);
      return;
    }
    const sizes: Array<{ n_doctors: number; n_days: number }> = [];
    for (const d of doctors) {
      for (const n of days) {
        sizes.push({ n_doctors: d, n_days: n });
      }
    }
    setResp(null);
    setRunning(true);
    setProgress({ done: 0, total: totalCells });
    try {
      const r = await apiFetch<ScalingResponse>("/api/lab/scaling/run", {
        method: "POST",
        body: {
          sizes,
          seeds,
          time_limit_s: timeLimit,
          num_workers: numWorkers,
          leave_rate: leaveRate,
        },
      });
      setResp(r);
      setProgress({ done: r.cells.length, total: r.cells.length });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Scaling run failed.");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>Scaling config</CardTitle>
          <CardDescription>
            Grid of <code>(doctors × days)</code> synthetic instances.
            CP-SAT solves each cell; the tab fits T = a·N^b in log-log
            space where N = doctors × days. See{" "}
            <code>docs/LAB_TAB_SPEC.md §5</code>.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-xs">
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              Doctor counts (comma / space separated)
            </span>
            <Input
              className="mt-1 h-8 text-xs"
              value={doctorsText}
              onChange={(e) => setDoctorsText(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              Day counts
            </span>
            <Input
              className="mt-1 h-8 text-xs"
              value={daysText}
              onChange={(e) => setDaysText(e.target.value)}
            />
          </label>
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              Seeds per size
            </span>
            <Input
              className="mt-1 h-8 text-xs"
              value={seedsText}
              onChange={(e) => setSeedsText(e.target.value)}
            />
          </label>
          <div className="grid grid-cols-3 gap-2">
            <label className="block">
              <span className="text-[10px] uppercase tracking-wide text-slate-500">
                Time (s)
              </span>
              <NumberInput
                min={1}
                max={120}
                className="mt-1 h-8 text-right text-xs"
                value={timeLimit}
                onChange={setTimeLimit}
              />
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wide text-slate-500">
                Workers
              </span>
              <NumberInput
                min={1}
                max={8}
                className="mt-1 h-8 text-right text-xs"
                value={numWorkers}
                onChange={setNumWorkers}
              />
            </label>
            <label className="block">
              <span className="text-[10px] uppercase tracking-wide text-slate-500">
                Leave%
              </span>
              <NumberInput
                integer={false}
                step={0.01}
                min={0}
                max={0.25}
                className="mt-1 h-8 text-right text-xs"
                value={leaveRate}
                onChange={setLeaveRate}
              />
            </label>
          </div>
          <p className="rounded-md border border-indigo-200 bg-indigo-50 p-2 text-[11px] dark:border-indigo-900 dark:bg-indigo-950/40">
            <strong>{totalCells}</strong> cell{totalCells === 1 ? "" : "s"}
            {" · budget ≤ "}
            <strong>{totalCells * timeLimit}s</strong>. Single-worker keeps
            timings reproducible.
          </p>
          <Button
            className="w-full"
            onClick={kickoff}
            disabled={running || totalCells === 0 || totalCells > 40}
          >
            <Play className="h-4 w-4" />
            {running ? `Running ${progress.done}/${progress.total}…` : "Run scaling sweep"}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <ScalingIntro />
        {resp ? (
          <ScalingResults resp={resp} predictN={predictN} setPredictN={setPredictN} />
        ) : running ? (
          <Card>
            <CardContent className="flex items-center gap-3 py-6 text-sm text-slate-500 dark:text-slate-400">
              <AlertCircle className="h-4 w-4 text-amber-500" />
              Running {progress.total} cells. Don't close the tab.
            </CardContent>
          </Card>
        ) : (
          <Card>
            <CardContent className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
              Pick a (doctors × days) grid and press <strong>Run scaling
              sweep</strong>. The page fits a power law to the solve
              times and lets you project solve time for any hypothetical
              instance.
            </CardContent>
          </Card>
        )}
      </div>
    </div>
  );
}

function ScalingIntro() {
  return (
    <Card className="border-indigo-200 bg-indigo-50/50 dark:border-indigo-900 dark:bg-indigo-950/30">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <CardTitle className="text-sm">
            How to answer "will this still work at N times the size?"
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
        <p>
          We generate a grid of synthetic instances at the sizes you
          pick, solve each one, and fit a curve through the wall
          times. The result tells you how solve time grows as your
          department / horizon gets bigger — so you can size a pilot
          before committing to it.
        </p>
        <p>
          <strong>When this is useful:</strong> a single hospital
          wants to know "if we double our team size, does this still
          run in under a minute?", or you're deciding whether to
          roster a whole month vs a fortnight at a time.
        </p>
        <p>
          <strong>What the fit tells you:</strong>
        </p>
        <ul className="ml-4 list-disc space-y-0.5">
          <li>
            <strong>Exponent b</strong> — how fast solve time grows
            with size (N = doctors × days). b ≈ 1 is linear; b &gt; 2
            is super-quadratic and signals scaling trouble.
          </li>
          <li>
            <strong>R²</strong> — how well a single power law fits
            the curve. Below ~0.6 usually means CP-SAT hit a phase
            transition — one size range solves instantly, another
            saturates the time budget.
          </li>
          <li>
            <strong>Prediction tool</strong> — plug in a hypothetical
            (doctors × days) and read the projected wall time.
          </li>
        </ul>
        <p className="text-[11px] text-slate-500 dark:text-slate-400">
          Cells that hit the time budget report the budget itself as
          the wall time, which flattens the tail of the curve and
          biases the fit downward. Raise the time limit if you see
          runs piling up at the cap.
        </p>
      </CardContent>
    </Card>
  );
}

function ScalingResults({
  resp,
  predictN,
  setPredictN,
}: {
  resp: ScalingResponse;
  predictN: number;
  setPredictN: (n: number) => void;
}) {
  const { cells, fit, time_limit_s } = resp;

  const scatter = cells
    .filter((c) => c.wall_time_s > 0 && c.size > 0)
    .map((c) => ({
      size: c.size,
      log_size: Math.log10(c.size),
      wall: c.wall_time_s,
      log_wall: Math.log10(c.wall_time_s),
      status: c.status,
      seed: c.seed,
      n_doctors: c.n_doctors,
      n_days: c.n_days,
    }));

  // Build a smooth fit line (if we have a fit) in the log-log domain.
  const fitLine: Array<{ log_size: number; log_wall: number }> = [];
  if (fit.exponent != null && fit.coefficient != null && scatter.length > 1) {
    const sizes = scatter.map((s) => s.size);
    const minN = Math.min(...sizes);
    const maxN = Math.max(...sizes);
    const steps = 20;
    const logMin = Math.log10(minN);
    const logMax = Math.log10(maxN);
    for (let i = 0; i <= steps; i++) {
      const logS = logMin + ((logMax - logMin) * i) / steps;
      const s = 10 ** logS;
      const t = fit.coefficient * s ** fit.exponent;
      fitLine.push({ log_size: logS, log_wall: Math.log10(Math.max(t, 1e-6)) });
    }
  }

  const predictedT =
    fit.exponent != null && fit.coefficient != null && predictN > 0
      ? fit.coefficient * predictN ** fit.exponent
      : null;

  const capHits = cells.filter((c) => c.wall_time_s >= time_limit_s * 0.99).length;

  return (
    <>
      <Card>
        <CardHeader>
          <CardTitle>Fit summary</CardTitle>
          <CardDescription>
            {fit.exponent != null && fit.coefficient != null ? (
              <>
                T ≈ <strong>{fit.coefficient.toPrecision(3)}</strong> · N
                <sup>{fit.exponent.toFixed(3)}</sup>
                {fit.r_squared != null && (
                  <>
                    {" · "}
                    R² = <strong>{fit.r_squared.toFixed(3)}</strong>
                  </>
                )}
                {" · "}n = {fit.n_points}
              </>
            ) : (
              <>
                Not enough feasible cells for a fit (need ≥ 2 OPTIMAL/FEASIBLE
                points at ≥ 2 distinct sizes). n = {fit.n_points}.
              </>
            )}
            {capHits > 0 && (
              <span className="ml-2 text-amber-600 dark:text-amber-400">
                · {capHits} cell{capHits === 1 ? "" : "s"} hit the time
                cap — fit exponent is a lower bound.
              </span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent className="h-72">
          <ResponsiveContainer width="100%" height="100%">
            <ComposedChart margin={{ top: 10, right: 20, bottom: 40, left: 8 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
              <XAxis
                dataKey="log_size"
                type="number"
                domain={["dataMin - 0.1", "dataMax + 0.1"]}
                tick={{ fontSize: 10 }}
                label={{
                  value: "log₁₀ (doctors × days)",
                  position: "insideBottom",
                  offset: -20,
                  style: { fontSize: 11, fill: "#64748b" },
                }}
              />
              <YAxis
                dataKey="log_wall"
                type="number"
                tick={{ fontSize: 10 }}
                label={{
                  value: "log₁₀ wall time (s)",
                  angle: -90,
                  position: "insideLeft",
                  style: { fontSize: 11, fill: "#64748b" },
                }}
              />
              <Tooltip
                contentStyle={{ fontSize: 11 }}
                formatter={(v, name) => {
                  const n = typeof v === "number" ? v : Number(v);
                  if (name === "log_wall")
                    return [`log₁₀ T = ${n.toFixed(2)}`, "wall"];
                  if (name === "log_size")
                    return [`log₁₀ N = ${n.toFixed(2)}`, "size"];
                  return [v, name];
                }}
                labelFormatter={() => ""}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Scatter
                name="runs"
                data={scatter}
                fill="#4f46e5"
                line={false}
                shape="circle"
              />
              {fitLine.length > 1 && (
                <Line
                  name="fit"
                  data={fitLine}
                  dataKey="log_wall"
                  stroke="#10b981"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  dot={false}
                  isAnimationActive={false}
                  type="linear"
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Predict from this data</CardTitle>
          <CardDescription>
            Plug a hypothetical instance size and read the projected
            solve time from the fitted power law. Extrapolating far past
            your grid's largest point is unreliable — flag anything past
            ~2× the largest cell.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap items-end gap-4 text-xs">
          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              N = doctors × days
            </span>
            <Input
              type="number"
              min={1}
              className="mt-1 h-8 w-32 text-right text-xs"
              value={predictN}
              onChange={(e) => setPredictN(Math.max(1, Number(e.target.value) || 1))}
            />
          </label>
          <div className="text-sm">
            Projected T ={" "}
            <span className="font-mono font-semibold">
              {predictedT == null ? "—" : `${predictedT.toFixed(2)}s`}
            </span>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Cells</CardTitle>
          <CardDescription>
            One row per (doctors × days × seed). Sorted by size ascending.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 dark:text-slate-400">
                <th className="py-1">Doctors</th>
                <th className="py-1">Days</th>
                <th className="py-1 text-right">N</th>
                <th className="py-1 text-right">Seed</th>
                <th className="py-1">Status</th>
                <th className="py-1 text-right">Wall (s)</th>
                <th className="py-1 text-right">First feas. (s)</th>
                <th className="py-1 text-right">Objective</th>
              </tr>
            </thead>
            <tbody>
              {[...cells]
                .sort((a, b) => a.size - b.size || a.seed - b.seed)
                .map((c, i) => (
                  <tr key={i}>
                    <td className="py-1">{c.n_doctors}</td>
                    <td className="py-1">{c.n_days}</td>
                    <td className="py-1 text-right font-mono">{c.size}</td>
                    <td className="py-1 text-right font-mono">{c.seed}</td>
                    <td className="py-1 font-mono text-[11px]">{c.status}</td>
                    <td className="py-1 text-right font-mono">
                      {c.wall_time_s.toFixed(2)}
                    </td>
                    <td className="py-1 text-right font-mono">
                      {c.first_feasible_s == null
                        ? "—"
                        : c.first_feasible_s.toFixed(2)}
                    </td>
                    <td className="py-1 text-right font-mono">
                      {c.objective == null ? "—" : Math.round(c.objective)}
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </>
  );
}
