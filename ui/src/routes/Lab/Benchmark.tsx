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

import { AlertTriangle, CheckCircle2, Play } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import {
  type BatchSummary,
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
        {run.data ? (
          <>
            <ReliabilityBanner summary={run.data} />
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
