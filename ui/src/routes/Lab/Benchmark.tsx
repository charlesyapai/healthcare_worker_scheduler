/**
 * /lab/benchmark — the payoff surface for Phase 2.
 *
 * Drives POST /api/lab/run over the current session state with a
 * selected list of solvers + seeds, then renders the industry
 * reliability metrics the VALIDATION_PLAN calls out: feasibility rate,
 * mean objective, mean coverage shortfall, CP-SAT quality ratio vs
 * each baseline.
 *
 * Intentionally MVP — the "bundle export" + sweep / scaling / fairness
 * deep-dive subtabs land in Phase 3 / 4.
 */

import {
  AlertTriangle,
  BookOpen,
  CheckCircle2,
  Download,
  Play,
  Settings,
} from "lucide-react";
import { useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
  ZAxis,
} from "recharts";
import { toast } from "sonner";

import {
  type BatchSummary,
  type SearchBranching,
  type SingleRun,
  type SolverKey,
  useBatchHistory,
  useRunBatch,
} from "@/api/hooks";
import { ApiError } from "@/api/client";
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

const SOLVER_COLORS: Record<SolverKey, string> = {
  cpsat: "#4f46e5",         // indigo-600 — main CP-SAT colour
  greedy: "#14b8a6",        // teal-500 — baseline
  random_repair: "#f59e0b", // amber-500 — weaker baseline
};

const SOLVER_LABELS: Record<SolverKey, string> = {
  cpsat: "CP-SAT (ours)",
  greedy: "Greedy (baseline)",
  random_repair: "Random + repair (baseline)",
};

const SOLVER_HINTS: Record<SolverKey, string> = {
  cpsat: "Full optimisation solver — our production path.",
  greedy: "Sanity-floor baseline. No look-ahead; respects eligibility only.",
  random_repair: "Weak baseline. Randomises then repairs H1/H3/H10 gaps.",
};

export function LabBenchmark() {
  const run = useRunBatch();
  const history = useBatchHistory();

  const [solvers, setSolvers] = useState<Record<SolverKey, boolean>>({
    cpsat: true,
    greedy: true,
    random_repair: false,
  });
  const [seedsText, setSeedsText] = useState("0");
  const [timeLimit, setTimeLimit] = useState(30);
  const [workers, setWorkers] = useState(1);
  const [feasibilityOnly, setFeasibilityOnly] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [branching, setBranching] = useState<SearchBranching>("AUTOMATIC");
  const [linearization, setLinearization] = useState(1);
  const [presolve, setPresolve] = useState(true);
  const [optCore, setOptCore] = useState(false);
  const [lnsOnly, setLnsOnly] = useState(false);

  const chosen: SolverKey[] = useMemo(
    () => (Object.keys(solvers) as SolverKey[]).filter((k) => solvers[k]),
    [solvers],
  );

  const seeds = useMemo(() => {
    return seedsText
      .split(/[\s,]+/)
      .map((s) => Number(s))
      .filter((n) => Number.isFinite(n) && Number.isInteger(n));
  }, [seedsText]);

  const nRuns = chosen.length * seeds.length;
  const estSec = nRuns * timeLimit;

  const kickoff = async () => {
    if (chosen.length === 0) {
      toast.error("Pick at least one solver.");
      return;
    }
    if (seeds.length === 0) {
      toast.error("Provide at least one integer seed.");
      return;
    }
    try {
      await run.mutateAsync({
        solvers: chosen,
        seeds,
        run_config: {
          time_limit_s: timeLimit,
          num_workers: workers,
          random_seed: seeds[0] ?? 0,
          feasibility_only: feasibilityOnly,
          search_branching: branching,
          linearization_level: linearization,
          cp_model_presolve: presolve,
          optimize_with_core: optCore,
          use_lns_only: lnsOnly,
        },
      });
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Batch failed");
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>Batch config</CardTitle>
          <CardDescription>
            Runs on the current session state (from Setup). To benchmark a
            different instance, load a scenario on the Dashboard first.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          <div>
            <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
              Solvers
            </p>
            <div className="mt-1 flex flex-col gap-1.5">
              {(["cpsat", "greedy", "random_repair"] as SolverKey[]).map((s) => (
                <label
                  key={s}
                  className="flex cursor-pointer items-start gap-2 rounded-md border border-slate-200 px-2 py-1.5 dark:border-slate-800"
                >
                  <input
                    type="checkbox"
                    className="mt-0.5"
                    checked={!!solvers[s]}
                    onChange={(e) =>
                      setSolvers((prev) => ({ ...prev, [s]: e.target.checked }))
                    }
                  />
                  <div>
                    <p className="text-xs font-medium">{SOLVER_LABELS[s]}</p>
                    <p className="text-[10px] text-slate-500 dark:text-slate-400">
                      {SOLVER_HINTS[s]}
                    </p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          <label className="block">
            <span className="text-xs text-slate-500 dark:text-slate-400">
              Seeds (comma / space separated)
            </span>
            <Input
              className="mt-1 h-8 text-xs"
              value={seedsText}
              onChange={(e) => setSeedsText(e.target.value)}
              placeholder="0, 1, 2, 3, 4"
            />
          </label>

          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="text-xs text-slate-500 dark:text-slate-400">
                Time limit (s)
              </span>
              <Input
                type="number"
                min={5}
                max={300}
                className="mt-1 h-8 text-right text-xs"
                value={timeLimit}
                onChange={(e) =>
                  setTimeLimit(Math.max(5, Math.min(300, Number(e.target.value) || 30)))
                }
              />
            </label>
            <label className="block">
              <span className="text-xs text-slate-500 dark:text-slate-400">
                Workers
              </span>
              <Input
                type="number"
                min={1}
                max={16}
                className="mt-1 h-8 text-right text-xs"
                value={workers}
                onChange={(e) =>
                  setWorkers(Math.max(1, Math.min(16, Number(e.target.value) || 1)))
                }
              />
            </label>
          </div>

          <label className="flex items-center gap-2 text-xs">
            <input
              type="checkbox"
              checked={feasibilityOnly}
              onChange={(e) => setFeasibilityOnly(e.target.checked)}
            />
            Feasibility-only (skip the fairness objective — CP-SAT only)
          </label>

          <details open={showAdvanced} onToggle={(e) => setShowAdvanced((e.target as HTMLDetailsElement).open)} className="rounded-md border border-slate-200 p-2 text-xs dark:border-slate-800">
            <summary className="flex cursor-pointer items-center gap-1.5 font-medium text-slate-700 dark:text-slate-200">
              <Settings className="h-3.5 w-3.5" />
              Advanced CP-SAT knobs
            </summary>
            <div className="mt-2 space-y-2">
              <label className="block">
                <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Search branching
                </span>
                <select
                  className="mt-1 h-8 w-full rounded-md border border-slate-300 bg-white px-2 text-xs dark:border-slate-700 dark:bg-slate-900"
                  value={branching}
                  onChange={(e) => setBranching(e.target.value as SearchBranching)}
                >
                  <option value="AUTOMATIC">AUTOMATIC (default)</option>
                  <option value="FIXED_SEARCH">FIXED_SEARCH</option>
                  <option value="PORTFOLIO_SEARCH">PORTFOLIO_SEARCH</option>
                  <option value="LP_SEARCH">LP_SEARCH</option>
                  <option value="PSEUDO_COST_SEARCH">PSEUDO_COST_SEARCH</option>
                  <option value="PORTFOLIO_WITH_QUICK_RESTART_SEARCH">
                    PORTFOLIO_WITH_QUICK_RESTART_SEARCH
                  </option>
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400">
                  Linearization level (0–2)
                </span>
                <Input
                  type="number"
                  min={0}
                  max={2}
                  className="mt-1 h-8 text-right text-xs"
                  value={linearization}
                  onChange={(e) =>
                    setLinearization(Math.max(0, Math.min(2, Number(e.target.value) || 1)))
                  }
                />
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={presolve}
                  onChange={(e) => setPresolve(e.target.checked)}
                />
                cp_model_presolve
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={optCore}
                  onChange={(e) => setOptCore(e.target.checked)}
                />
                optimize_with_core
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={lnsOnly}
                  onChange={(e) => setLnsOnly(e.target.checked)}
                />
                use_lns_only
              </label>
              <p className="text-[10px] text-slate-500 dark:text-slate-400">
                These map straight to CP-SAT's SatParameters fields. See{" "}
                <code>docs/RESEARCH_METRICS.md §6</code>.
              </p>
            </div>
          </details>

          <div className="rounded-md border border-indigo-200 bg-indigo-50 p-2 text-xs dark:border-indigo-900 dark:bg-indigo-950/40">
            <p>
              <strong>{nRuns}</strong> run{nRuns === 1 ? "" : "s"} · budget ≤{" "}
              <strong>{estSec}s</strong>. Batch is synchronous — don't close
              the tab while it's running.
            </p>
            {workers > 1 && (
              <p className="mt-1 text-[10px] text-amber-700 dark:text-amber-300">
                <AlertTriangle className="mr-1 inline h-3 w-3" />
                Multi-worker CP-SAT is non-deterministic. For reproducibility,
                use workers = 1.
              </p>
            )}
          </div>

          <Button
            className="w-full"
            disabled={run.isPending || nRuns === 0}
            onClick={kickoff}
          >
            <Play className="h-4 w-4" />
            {run.isPending ? "Running…" : `Run benchmark`}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <BenchmarkIntro />
        {run.data ? (
          <>
            <ReliabilityBanner summary={run.data} />
            <SolverComparisonChart summary={run.data} />
            <RunScatter summary={run.data} />
            <BundleDownload batchId={run.data.batch_id} />
            <ResultsTable summary={run.data} />
          </>
        ) : (
          <Card>
            <CardContent className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
              Press <strong>Run benchmark</strong> to compare CP-SAT against
              the selected baselines. Results will stream in here.
            </CardContent>
          </Card>
        )}
        <HistoryCard history={history.data ?? []} />
      </div>
    </div>
  );
}

// ---------------------------------------------------- intro / reading guide

function BenchmarkIntro() {
  return (
    <Card className="border-indigo-200 bg-indigo-50/50 dark:border-indigo-900 dark:bg-indigo-950/30">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <CardTitle className="text-sm">What this tab does</CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
        <p>
          Runs the selected solvers over a cross-product of seeds on the
          <strong> currently loaded scenario</strong>, then compares them on
          the NRP-literature reliability metrics. A batch of 3 solvers × 3
          seeds = 9 runs in ~a minute.
        </p>
        <p className="mt-1">
          <strong>What to watch:</strong>
        </p>
        <ul className="ml-4 list-disc space-y-0.5">
          <li>
            <strong>Feasibility rate</strong> — % of runs with zero hard-
            constraint violations. Our CP-SAT should sit at 100%. Greedy
            usually green on clean scenarios, red on tight ones.
            Random-repair ≈ always red (it skips H4/H5/H8 by design).
          </li>
          <li>
            <strong>Coverage shortfall</strong> — unfilled station-slots.
            Zero = every required slot staffed.
          </li>
          <li>
            <strong>Objective</strong> — weighted soft-penalty sum. Lower
            is better; different orders of magnitude across solvers are
            normal (baselines don't optimise).
          </li>
          <li>
            <strong>Quality ratio Q</strong> — Z<sub>baseline</sub> /
            Z<sub>ours</sub>. Only appears when both methods report an
            objective; currently only CP-SAT does, so Q lights up once a
            MILP baseline ships.
          </li>
        </ul>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------- comparison chart

function SolverComparisonChart({ summary }: { summary: BatchSummary }) {
  const solvers = Array.from(new Set(summary.runs.map((r) => r.solver)));
  if (solvers.length === 0) return null;

  // One row per solver. Objectives + shortfalls are on different scales,
  // so render three small charts side-by-side rather than a single chart
  // with dual Y-axes (easier to read, no misleading axis tricks).
  const feasData = solvers.map((s) => ({
    solver: SOLVER_LABELS[s as SolverKey] ?? s,
    value: (summary.feasibility_rate[s] ?? 0) * 100,
    raw: s as SolverKey,
  }));
  const objData = solvers.map((s) => ({
    solver: SOLVER_LABELS[s as SolverKey] ?? s,
    value: summary.mean_objective[s] ?? null,
    raw: s as SolverKey,
  }));
  const shortData = solvers.map((s) => ({
    solver: SOLVER_LABELS[s as SolverKey] ?? s,
    value: summary.mean_shortfall[s] ?? 0,
    raw: s as SolverKey,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Solver comparison</CardTitle>
        <CardDescription>
          Side-by-side on three independent metrics. Bars are coloured by
          solver so you can follow one across charts. A method that's
          green on all three panels is "production-ready" on this instance.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-4 md:grid-cols-3">
          <MiniBarChart
            title="Feasibility rate"
            subtitle="higher better · 100% = every run satisfied H1–H15"
            data={feasData}
            suffix="%"
            yDomain={[0, 100]}
          />
          <MiniBarChart
            title="Mean objective"
            subtitle="lower better · — if solver doesn't optimise"
            data={objData}
          />
          <MiniBarChart
            title="Mean shortfall"
            subtitle="lower better · 0 = no unfilled slots"
            data={shortData}
          />
        </div>
      </CardContent>
    </Card>
  );
}

function MiniBarChart({
  title,
  subtitle,
  data,
  suffix = "",
  yDomain,
}: {
  title: string;
  subtitle: string;
  data: Array<{ solver: string; value: number | null; raw: SolverKey }>;
  suffix?: string;
  yDomain?: [number, number];
}) {
  const nonNull = data.every((d) => d.value == null);
  return (
    <div className="flex flex-col">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
        {title}
      </p>
      <p className="mb-2 text-[10px] text-slate-500 dark:text-slate-400">
        {subtitle}
      </p>
      <div className="h-44 rounded-md border border-slate-200 dark:border-slate-800">
        {nonNull ? (
          <div className="flex h-full items-center justify-center text-[11px] text-slate-400">
            no data
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data.map((d) => ({ ...d, value: d.value ?? 0 }))}
              margin={{ top: 8, right: 8, bottom: 4, left: 0 }}
            >
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
              <XAxis dataKey="solver" tick={{ fontSize: 10 }} interval={0} />
              <YAxis tick={{ fontSize: 10 }} domain={yDomain} />
              <Tooltip
                contentStyle={{ fontSize: 11 }}
                formatter={(v) => `${Number(v).toFixed(1)}${suffix}`}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {data.map((d, i) => (
                  <Cell key={i} fill={SOLVER_COLORS[d.raw] ?? "#94a3b8"} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------- per-run scatter

function RunScatter({ summary }: { summary: BatchSummary }) {
  const solvers = Array.from(new Set(summary.runs.map((r) => r.solver))) as SolverKey[];
  if (summary.runs.length === 0) return null;
  // Group runs by solver so recharts can render one Scatter series per
  // solver with its own colour + legend entry. Using wall time on X and
  // objective on Y; each dot is one (seed) run.
  const series = solvers.map((s) => ({
    name: SOLVER_LABELS[s] ?? s,
    solver: s,
    data: summary.runs
      .filter((r) => r.solver === s)
      .map((r) => ({
        x: r.wall_time_s,
        y: r.objective ?? null,
        seed: r.seed,
        status: r.status,
        selfCheck: r.self_check_ok,
        shortfall: r.coverage_shortfall,
      })),
  }));

  const allY = series.flatMap((s) => s.data.map((d) => d.y).filter((y): y is number => y != null));
  const hasObjective = allY.length > 0;

  return (
    <Card>
      <CardHeader>
        <CardTitle>
          {hasObjective ? "Objective vs wall time" : "Wall time per run"}
        </CardTitle>
        <CardDescription>
          One dot per (solver × seed) run. Tight cluster = stable (low
          seed sensitivity). Big spread = reconsider the seed count
          before publishing a mean. Baselines without an objective sit
          on the X-axis.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            <ScatterChart margin={{ top: 8, right: 12, bottom: 20, left: 8 }}>
              <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
              <XAxis
                dataKey="x"
                type="number"
                name="wall time"
                tick={{ fontSize: 11 }}
                label={{
                  value: "wall time (s)",
                  position: "insideBottom",
                  offset: -10,
                  style: { fontSize: 11, fill: "#64748b" },
                }}
              />
              <YAxis
                dataKey="y"
                type="number"
                name="objective"
                tick={{ fontSize: 11 }}
                label={{
                  value: "objective",
                  angle: -90,
                  position: "insideLeft",
                  style: { fontSize: 11, fill: "#64748b" },
                }}
              />
              <ZAxis range={[60, 60]} />
              <Tooltip
                contentStyle={{ fontSize: 11 }}
                cursor={{ strokeDasharray: "3 3" }}
                formatter={(v, key) => {
                  if (key === "x") return [`${Number(v).toFixed(2)}s`, "wall time"];
                  if (key === "y") return [Number(v).toFixed(0), "objective"];
                  return [v, key];
                }}
              />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              {series.map((s) => (
                <Scatter
                  key={s.solver}
                  name={s.name}
                  data={s.data}
                  fill={SOLVER_COLORS[s.solver] ?? "#94a3b8"}
                />
              ))}
            </ScatterChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}

function ReliabilityBanner({ summary }: { summary: BatchSummary }) {
  const rows = summary.runs;
  const solvers = Array.from(new Set(rows.map((r) => r.solver)));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Industry reliability metrics</CardTitle>
        <CardDescription>
          Cross-comparable with NRP literature. Feasibility rate per method
          (§7.3), mean coverage shortfall (§5.1b), quality ratio Q =
          Z<sub>baseline</sub> / Z<sub>ours</sub> (§7.1). Formulae in{" "}
          <code>docs/RESEARCH_METRICS.md</code>.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {solvers.map((s) => {
            const feas = summary.feasibility_rate[s] ?? 0;
            const mean = summary.mean_objective[s];
            const meanShort = summary.mean_shortfall[s] ?? 0;
            const green = feas === 1.0 && meanShort === 0;
            return (
              <div
                key={s}
                className={cn(
                  "rounded-md border p-3 text-xs",
                  green
                    ? "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/40"
                    : "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40",
                )}
              >
                <p className="flex items-center justify-between gap-2">
                  <span className="font-semibold">
                    {SOLVER_LABELS[s as SolverKey] ?? s}
                  </span>
                  {green && (
                    <CheckCircle2 className="h-4 w-4 text-emerald-600 dark:text-emerald-400" />
                  )}
                </p>
                <MetricRow label="Feasibility rate" value={`${(feas * 100).toFixed(0)}%`} />
                <MetricRow label="Mean objective" value={mean == null ? "—" : mean.toFixed(0)} />
                <MetricRow
                  label="Mean shortfall"
                  value={meanShort.toFixed(1)}
                  muted={meanShort === 0}
                />
              </div>
            );
          })}
        </div>
        {Object.keys(summary.quality_ratios).length > 0 && (
          <div className="mt-4 rounded-md border border-slate-200 p-3 text-xs dark:border-slate-800">
            <p className="mb-1 font-semibold">Quality ratio (baseline / CP-SAT)</p>
            <div className="flex flex-wrap gap-2">
              {Object.entries(summary.quality_ratios).map(([k, v]) => (
                <span
                  key={k}
                  className="rounded-full bg-indigo-100 px-2 py-0.5 font-mono dark:bg-indigo-900/60"
                  title="Q > 1 means our CP-SAT beats the baseline by that factor."
                >
                  {k.replace("cpsat_vs_", "vs ")}: Q={v.toFixed(2)}
                </span>
              ))}
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function MetricRow({
  label,
  value,
  muted,
}: {
  label: string;
  value: string;
  muted?: boolean;
}) {
  return (
    <div className="mt-1 flex items-baseline justify-between gap-2">
      <span className="text-slate-500 dark:text-slate-400">{label}</span>
      <span
        className={cn(
          "font-mono font-medium",
          muted ? "text-slate-500" : "text-slate-800 dark:text-slate-100",
        )}
      >
        {value}
      </span>
    </div>
  );
}

function ResultsTable({ summary }: { summary: BatchSummary }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Per-run results</CardTitle>
        <CardDescription>
          One row per (solver × seed). <code>self-check ✓</code> = every
          hard constraint satisfied (validator re-checked post-solve).
          <code> shortfall</code> = unfilled station-slots.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="max-h-96 overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
          <table className="min-w-full divide-y divide-slate-200 text-xs dark:divide-slate-800">
            <thead className="sticky top-0 bg-slate-50 text-left font-semibold text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              <tr>
                <th className="px-2 py-1.5">Solver</th>
                <th className="px-2 py-1.5">Seed</th>
                <th className="px-2 py-1.5">Status</th>
                <th className="px-2 py-1.5 text-right">Objective</th>
                <th className="px-2 py-1.5 text-right">Headroom</th>
                <th className="px-2 py-1.5 text-right">Time (s)</th>
                <th className="px-2 py-1.5 text-center">Self-check</th>
                <th className="px-2 py-1.5 text-right">Shortfall</th>
                <th className="px-2 py-1.5 text-right">Over</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {summary.runs.map((r) => (
                <RunRow key={r.run_id} row={r} />
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}

function RunRow({ row }: { row: SingleRun }) {
  const statusCls =
    row.status === "OPTIMAL"
      ? "text-emerald-700 dark:text-emerald-300"
      : row.status === "FEASIBLE"
        ? "text-indigo-700 dark:text-indigo-300"
        : row.status === "HEURISTIC"
          ? "text-slate-600 dark:text-slate-300"
          : "text-rose-700 dark:text-rose-300";
  return (
    <tr>
      <td className="px-2 py-1 font-medium">{SOLVER_LABELS[row.solver] ?? row.solver}</td>
      <td className="px-2 py-1 font-mono">{row.seed}</td>
      <td className={cn("px-2 py-1 font-semibold", statusCls)}>{row.status}</td>
      <td className="px-2 py-1 text-right font-mono">
        {row.objective == null ? "—" : row.objective.toFixed(0)}
      </td>
      <td className="px-2 py-1 text-right font-mono">
        {row.headroom == null ? "—" : row.headroom.toFixed(0)}
      </td>
      <td className="px-2 py-1 text-right font-mono">{row.wall_time_s.toFixed(1)}</td>
      <td className="px-2 py-1 text-center">
        {row.self_check_ok == null ? (
          "—"
        ) : row.self_check_ok ? (
          <span className="text-emerald-600">✓</span>
        ) : (
          <span
            className="text-rose-600"
            title={`${row.violation_count ?? 0} violation${row.violation_count === 1 ? "" : "s"}`}
          >
            ✗ ({row.violation_count ?? "?"})
          </span>
        )}
      </td>
      <td
        className={cn(
          "px-2 py-1 text-right font-mono",
          row.coverage_shortfall === 0 ? "text-slate-500" : "text-amber-700 dark:text-amber-300",
        )}
      >
        {row.coverage_shortfall}
      </td>
      <td
        className={cn(
          "px-2 py-1 text-right font-mono",
          row.coverage_over === 0 ? "text-slate-500" : "text-amber-700 dark:text-amber-300",
        )}
      >
        {row.coverage_over}
      </td>
    </tr>
  );
}

function BundleDownload({ batchId }: { batchId: string }) {
  const href = `/api/lab/runs/${batchId}/bundle.zip`;
  return (
    <Card className="border-indigo-200 bg-indigo-50 dark:border-indigo-900 dark:bg-indigo-950/40">
      <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3 text-xs">
        <div>
          <p className="font-semibold">Reproducibility bundle ready</p>
          <p className="text-slate-600 dark:text-slate-300">
            state.yaml · run_config.json · results.json · git_sha.txt ·
            requirements.txt · README.md — everything a reviewer needs to
            replay this run. See <code>docs/HOW_TO_REPRODUCE.md</code>.
          </p>
        </div>
        <a
          href={href}
          className="inline-flex items-center gap-1.5 rounded-md bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-indigo-700"
        >
          <Download className="h-3.5 w-3.5" />
          Download bundle
        </a>
      </CardContent>
    </Card>
  );
}

function HistoryCard({ history }: { history: Array<{ batch_id: string; created_at: string; instance_label: string; n_runs: number; solvers: string[]; n_seeds: number }> }) {
  if (history.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recent batches</CardTitle>
        <CardDescription>
          In-memory, LRU-capped at 50. Reset on server restart. Bundle export
          arrives in Phase 3.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <ul className="divide-y divide-slate-100 text-xs dark:divide-slate-800">
          {history.slice(0, 10).map((h) => (
            <li key={h.batch_id} className="flex items-center justify-between py-1.5">
              <div>
                <p className="font-medium">{h.instance_label}</p>
                <p className="text-[10px] text-slate-500 dark:text-slate-400">
                  {h.n_runs} run{h.n_runs === 1 ? "" : "s"} · {h.solvers.join(", ")} ·{" "}
                  {h.n_seeds} seed{h.n_seeds === 1 ? "" : "s"}
                </p>
              </div>
              <span className="font-mono text-[10px] text-slate-400">
                {new Date(h.created_at).toLocaleTimeString()}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
