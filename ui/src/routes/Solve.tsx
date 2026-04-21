import { Pause, Play, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { useAutoSavePatch } from "@/api/autosave";
import { useSessionState } from "@/api/hooks";
import { startSolve, stopSolve } from "@/api/solveWs";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useSolveStore } from "@/store/solve";

export function Solve() {
  const { data: state } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const solve = useSolveStore();

  const solver = state?.solver ?? { time_limit: 60, num_workers: 8, feasibility_only: false };

  const [elapsed, setElapsed] = useState(0);
  useEffect(() => {
    if (solve.status !== "running" || solve.startedAt == null) {
      setElapsed(0);
      return;
    }
    const t = setInterval(() => setElapsed((Date.now() - (solve.startedAt ?? 0)) / 1000), 200);
    return () => clearInterval(t);
  }, [solve.status, solve.startedAt]);

  const kickoff = () => {
    if (!state?.horizon?.start_date) {
      toast.error("Set a horizon start date in Setup → When first.");
      return;
    }
    if (!state.doctors?.length || !state.stations?.length) {
      toast.error("Configure doctors and stations first.");
      return;
    }
    startSolve({ snapshotAssignments: true });
  };

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight">Solve</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Stream improving solutions over WebSocket. Press Stop to accept the
          current best.
        </p>
      </header>

      <div className="grid gap-4 lg:grid-cols-[20rem_1fr]">
        <Card>
          <CardHeader>
            <CardTitle>Solver settings</CardTitle>
            <CardDescription>Saved between runs.</CardDescription>
          </CardHeader>
          <CardContent className="grid gap-3 text-sm">
            <label className="flex items-center justify-between gap-3">
              <span>Time limit (s)</span>
              <Input
                type="number"
                min={5}
                max={3600}
                className="h-8 w-24 text-right"
                value={solver.time_limit ?? 60}
                onChange={(e) =>
                  save({
                    solver: { ...solver, time_limit: Math.max(5, Number(e.target.value) || 60) },
                  })
                }
              />
            </label>
            <label className="flex items-center justify-between gap-3">
              <span>CPU workers</span>
              <Input
                type="number"
                min={1}
                max={16}
                className="h-8 w-24 text-right"
                value={solver.num_workers ?? 8}
                onChange={(e) =>
                  save({
                    solver: {
                      ...solver,
                      num_workers: Math.max(1, Math.min(16, Number(e.target.value) || 8)),
                    },
                  })
                }
              />
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={!!solver.feasibility_only}
                onChange={(e) =>
                  save({ solver: { ...solver, feasibility_only: e.target.checked } })
                }
              />
              Feasibility only (skip fairness objective)
            </label>

            <div className="mt-2 flex flex-col gap-2">
              {solve.status === "running" ? (
                <Button variant="destructive" onClick={stopSolve}>
                  <Pause className="h-4 w-4" />
                  Stop (accept best)
                </Button>
              ) : (
                <Button onClick={kickoff}>
                  <Play className="h-4 w-4" />
                  Solve
                </Button>
              )}
              {solve.status !== "idle" && solve.status !== "running" && (
                <Button variant="secondary" onClick={solve.reset}>
                  <RefreshCw className="h-4 w-4" />
                  Clear
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4">
          <VerdictBanner elapsed={elapsed} />
          <ConvergenceCard />
          <IntermediateTable />
        </div>
      </div>
    </div>
  );
}

function VerdictBanner({ elapsed }: { elapsed: number }) {
  const { status, events, result, errorMessage } = useSolveStore();
  if (status === "idle") {
    return (
      <Card>
        <CardContent className="py-6 text-sm text-slate-500 dark:text-slate-400">
          Press <strong className="text-slate-700 dark:text-slate-200">Solve</strong> to
          start. Intermediate solutions will stream in below.
        </CardContent>
      </Card>
    );
  }

  if (status === "error") {
    return (
      <Card className="border-red-300 bg-red-50 dark:border-red-800 dark:bg-red-950/60">
        <CardContent className="py-4 text-sm text-red-900 dark:text-red-200">
          Solve failed: {errorMessage ?? "unknown error"}
        </CardContent>
      </Card>
    );
  }

  if (status === "running") {
    const obj = events.length ? events[events.length - 1].objective : null;
    return (
      <Card className="border-indigo-300 bg-indigo-50 dark:border-indigo-800 dark:bg-indigo-950/60">
        <CardContent className="flex items-center gap-4 py-4 text-sm text-indigo-900 dark:text-indigo-100">
          <span className="relative flex h-3 w-3 flex-shrink-0">
            <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-indigo-400 opacity-75" />
            <span className="relative inline-flex h-3 w-3 rounded-full bg-indigo-600" />
          </span>
          <div>
            <p className="font-medium">Solving…</p>
            <p className="text-xs">
              {elapsed.toFixed(1)}s · {events.length} solution{events.length === 1 ? "" : "s"} found
              {obj != null ? ` · objective ${obj.toFixed(0)}` : ""}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (status === "done" && result) {
    const gap =
      result.objective != null && result.best_bound != null && result.objective > 0
        ? Math.max(0, (result.objective - result.best_bound) / result.objective) * 100
        : null;
    const good =
      result.status === "OPTIMAL" || (result.status === "FEASIBLE" && (gap ?? 100) < 5);
    return (
      <Card
        className={
          good
            ? "border-emerald-300 bg-emerald-50 dark:border-emerald-800 dark:bg-emerald-950/60"
            : "border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/60"
        }
      >
        <CardContent className="flex items-start justify-between gap-4 py-4 text-sm">
          <div>
            <p className="font-medium">
              {result.status === "OPTIMAL"
                ? "Optimal roster found"
                : result.status === "FEASIBLE"
                  ? gap != null
                    ? `Feasible roster (gap ${gap.toFixed(1)}%)`
                    : "Feasible roster"
                  : `Status: ${result.status}`}
            </p>
            <p className="text-xs text-slate-600 dark:text-slate-300">
              {result.wall_time_s.toFixed(1)}s · {result.assignments?.length ?? 0} assignments
              {result.first_feasible_s != null
                ? ` · first feasible at ${result.first_feasible_s.toFixed(1)}s`
                : ""}
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return null;
}

function ConvergenceCard() {
  const events = useSolveStore((s) => s.events);
  if (events.length === 0) return null;
  const chartData = events.map((e, i) => ({
    t: Number(e.wall_s.toFixed(2)),
    objective: e.objective ?? null,
    bound: e.best_bound ?? null,
    i,
  }));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Convergence</CardTitle>
        <CardDescription>Objective (lower = better) and best bound vs. wall time.</CardDescription>
      </CardHeader>
      <CardContent className="h-60">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={chartData} margin={{ top: 8, right: 12, bottom: 16, left: 8 }}>
            <CartesianGrid stroke="#e2e8f0" strokeDasharray="2 4" />
            <XAxis dataKey="t" tick={{ fontSize: 11 }} label={{ value: "seconds", position: "insideBottom", offset: -4, style: { fontSize: 11 } }} />
            <YAxis tick={{ fontSize: 11 }} />
            <Tooltip contentStyle={{ fontSize: 12 }} />
            <Line type="monotone" dataKey="objective" stroke="#4f46e5" strokeWidth={2} dot={false} />
            <Line type="monotone" dataKey="bound" stroke="#94a3b8" strokeWidth={1.5} strokeDasharray="4 4" dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

function IntermediateTable() {
  const events = useSolveStore((s) => s.events);
  if (events.length === 0) return null;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Intermediate solutions</CardTitle>
        <CardDescription>{events.length} improving solution{events.length === 1 ? "" : "s"} captured so far.</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="max-h-64 overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
          <table className="min-w-full divide-y divide-slate-200 text-xs dark:divide-slate-800">
            <thead className="bg-slate-50 text-left font-semibold text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              <tr>
                <th className="px-2 py-1.5">#</th>
                <th className="px-2 py-1.5">t (s)</th>
                <th className="px-2 py-1.5">Objective</th>
                <th className="px-2 py-1.5">Bound</th>
                <th className="px-2 py-1.5">Assignments</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
              {events.map((e, i) => (
                <tr key={i}>
                  <td className="px-2 py-1">{i}</td>
                  <td className="px-2 py-1">{e.wall_s.toFixed(2)}</td>
                  <td className="px-2 py-1">{e.objective?.toFixed(0) ?? "—"}</td>
                  <td className="px-2 py-1">{e.best_bound?.toFixed(0) ?? "—"}</td>
                  <td className="px-2 py-1">{e.assignments?.length ?? 0}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
