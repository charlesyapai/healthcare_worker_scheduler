import { Pause, Play, PlusCircle, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { useAutoSavePatch } from "@/api/autosave";
import { useSessionState } from "@/api/hooks";
import { startSolve, stopSolve } from "@/api/solveWs";
import { ObjectiveBreakdown } from "@/components/ObjectiveBreakdown";
import { SelfCheckBadge } from "@/components/SelfCheckBadge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { NumberInput } from "@/components/ui/numberInput";
import { type SolveResultPayload, useSolveStore } from "@/store/solve";

function fmt(n: number | null): string {
  if (n == null || !Number.isFinite(n)) return "—";
  return Number.isInteger(n) ? n.toLocaleString() : n.toFixed(1);
}

export function Solve() {
  const { data: state } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const solve = useSolveStore();

  const solver = state?.solver ?? { time_limit: 60, num_workers: 8, feasibility_only: false };
  const timeLimit = solver.time_limit ?? 30;

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
    const nDocs = state.doctors?.length ?? 0;
    const nStations = state.stations?.length ?? 0;
    if (nDocs === 0 || nStations === 0) {
      toast.error(
        `Can't solve: ${nDocs} doctor${nDocs === 1 ? "" : "s"} and ${nStations} station${
          nStations === 1 ? "" : "s"
        } configured. Need at least one of each.`,
      );
      return;
    }
    const stationNames = new Set(state.stations?.map((s) => s.name) ?? []);
    const broken = (state.doctors ?? []).find((d) => {
      const el = d.eligible_stations ?? [];
      if (el.length === 0) return true;
      return !el.some((s) => stationNames.has(s));
    });
    if (broken) {
      toast.error(
        `${broken.name} has no eligible stations in your station list. Fix on Setup → People.`,
      );
      return;
    }
    startSolve({ snapshotAssignments: true });
  };

  const continueSolving = () => {
    if (!state?.horizon?.start_date) {
      toast.error("Set a horizon start date in Setup → When first.");
      return;
    }
    toast.message(
      `Running another ${timeLimit}s search. If it doesn't improve, your previous best is kept.`,
    );
    startSolve({ snapshotAssignments: true, mode: "continue" });
  };

  const canContinue = solve.status === "done" && !isOptimal(solve.result);

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
              <NumberInput
                min={5}
                max={3600}
                className="h-8 w-24 text-right"
                value={solver.time_limit ?? 60}
                onChange={(v) =>
                  save({
                    solver: { ...solver, time_limit: Math.max(5, v) },
                  })
                }
              />
            </label>
            <label className="flex items-center justify-between gap-3">
              <span>CPU workers</span>
              <NumberInput
                min={1}
                max={16}
                className="h-8 w-24 text-right"
                value={solver.num_workers ?? 8}
                onChange={(v) =>
                  save({
                    solver: { ...solver, num_workers: v },
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

            <StaffingMode />

            <div className="mt-2 flex flex-col gap-2 border-t border-slate-200 pt-3 dark:border-slate-800">
              {solve.status === "running" ? (
                <Button variant="destructive" onClick={stopSolve}>
                  <Pause className="h-4 w-4" />
                  Stop (accept best)
                </Button>
              ) : (
                <Button onClick={kickoff}>
                  <Play className="h-4 w-4" />
                  {solve.status === "done" ? "Solve again" : "Solve"}
                </Button>
              )}
              {canContinue && (
                <Button
                  variant="secondary"
                  onClick={continueSolving}
                  title="Re-run the solver with the current time budget. A new search may find a lower objective."
                >
                  <PlusCircle className="h-4 w-4" />
                  Continue solving (+{timeLimit}s)
                </Button>
              )}
              {solve.status !== "idle" && solve.status !== "running" && (
                <Button variant="ghost" onClick={solve.reset}>
                  <RefreshCw className="h-4 w-4" />
                  Clear
                </Button>
              )}
            </div>
          </CardContent>
        </Card>

        <div className="grid gap-4">
          <VerdictBanner elapsed={elapsed} />
          {solve.status === "done" && solve.result && (
            <SelfCheckBadge selfCheck={solve.result.self_check} />
          )}
          <ConvergenceCard />
          {solve.status === "done" && solve.result && (
            <ObjectiveBreakdown
              objective={solve.result.objective}
              bestBound={solve.result.best_bound}
              components={solve.result.penalty_components}
              assignmentCount={solve.result.assignments?.length ?? 0}
              weights={
                state?.soft_weights ?? {
                  workload: 40,
                  sessions: 5,
                  oncall: 10,
                  weekend: 10,
                  reporting: 5,
                  idle_weekday: 100,
                  preference: 5,
                }
              }
              tierLabels={state?.tier_labels ?? undefined}
            />
          )}
          <IntermediateTable />
        </div>
      </div>
    </div>
  );
}

function StaffingMode() {
  const { data } = useSessionState();
  const { schedule: save } = useAutoSavePatch();
  const h11 = !!data?.constraints?.h11_enabled;
  const idleWeight = data?.soft_weights?.idle_weekday ?? 100;
  const current: "balanced" | "minimal" = h11 && idleWeight > 0 ? "balanced" : "minimal";

  const setMode = (mode: "balanced" | "minimal") => {
    if (mode === "minimal") {
      save({
        constraints: { ...(data?.constraints ?? {}), h11_enabled: false } as never,
        soft_weights: { ...(data?.soft_weights ?? {}), idle_weekday: 0 } as never,
      });
    } else {
      save({
        constraints: { ...(data?.constraints ?? {}), h11_enabled: true } as never,
        soft_weights: {
          ...(data?.soft_weights ?? {}),
          idle_weekday: Math.max(idleWeight, 100),
        } as never,
      });
    }
  };

  return (
    <div className="border-t border-slate-200 pt-3 dark:border-slate-800">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
        Staffing mode
      </p>
      <div className="mt-1.5 flex flex-col gap-1.5">
        <ModeOption
          active={current === "balanced"}
          onClick={() => setMode("balanced")}
          title="Balanced (default)"
          body="Every person must have a duty every weekday unless excused. Good for full utilisation."
        />
        <ModeOption
          active={current === "minimal"}
          onClick={() => setMode("minimal")}
          title="Minimal staffing"
          body="Only fill what hard constraints require. People without a strictly-needed duty get the day off — useful to see who's actually essential."
        />
      </div>
      <p className="mt-1.5 text-[10px] text-slate-500 dark:text-slate-400">
        Toggles H11 (mandatory-weekday rule) and the idle-weekday penalty
        under the hood.
      </p>
    </div>
  );
}

function ModeOption({
  active,
  onClick,
  title,
  body,
}: {
  active: boolean;
  onClick: () => void;
  title: string;
  body: string;
}) {
  return (
    <label
      className={
        "flex cursor-pointer gap-2 rounded-md border px-2.5 py-1.5 text-xs " +
        (active
          ? "border-indigo-300 bg-indigo-50 dark:border-indigo-800 dark:bg-indigo-950/40"
          : "border-slate-200 hover:bg-slate-50 dark:border-slate-800 dark:hover:bg-slate-900/50")
      }
    >
      <input
        type="radio"
        name="staffing-mode"
        checked={active}
        onChange={onClick}
        className="mt-0.5"
      />
      <div>
        <p className="font-medium">{title}</p>
        <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
          {body}
        </p>
      </div>
    </label>
  );
}

function isOptimal(result: SolveResultPayload | null | undefined): boolean {
  if (!result) return false;
  if (result.status === "OPTIMAL") return true;
  if (
    result.objective != null &&
    result.best_bound != null &&
    result.objective <= result.best_bound + 0.5
  ) {
    return true;
  }
  return false;
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
    const mode = useSolveStore.getState().mode;
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
            {mode === "rest" ? (
              <p className="text-xs">
                {elapsed.toFixed(1)}s · live updates unavailable on this connection,
                waiting for the solver's final result.
              </p>
            ) : (
              <p className="text-xs">
                {elapsed.toFixed(1)}s · {events.length} improving solution{events.length === 1 ? "" : "s"} found
                {obj != null ? ` · objective ${obj.toFixed(0)}` : ""}
              </p>
            )}
          </div>
        </CardContent>
      </Card>
    );
  }

  if (status === "done" && result) {
    const headroom =
      result.objective != null && result.best_bound != null
        ? Math.max(0, result.objective - result.best_bound)
        : null;
    const good = result.status === "OPTIMAL" || headroom === 0;
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
                  ? headroom === 0
                    ? "Feasible & provably optimal"
                    : headroom != null
                      ? `Feasible roster (${fmt(headroom)} headroom to theoretical minimum)`
                      : "Feasible roster"
                  : `Status: ${result.status}`}
            </p>
            <p className="text-xs text-slate-600 dark:text-slate-300">
              {result.wall_time_s.toFixed(1)}s · {result.assignments?.length ?? 0} assignments
              {result.first_feasible_s != null
                ? ` · first feasible at ${result.first_feasible_s.toFixed(1)}s`
                : ""}
            </p>
            {!good && (
              <p className="mt-1 text-xs text-amber-900 dark:text-amber-200">
                The solver didn't prove optimality before the time limit.
                Try <strong>Continue solving</strong> to give it more time.
                If the score doesn't improve after another run, this is
                probably the practical optimum — CP-SAT's lower bound is
                often loose in roster problems.
              </p>
            )}
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
        <CardDescription>
          {events.length} improving solution{events.length === 1 ? "" : "s"} captured so far.
          The solver tries to drive{" "}
          <strong title="Sum of weighted soft penalties — lower is better">objective</strong> down toward{" "}
          <strong title="Lowest achievable objective the solver has proved">bound</strong>; when they meet, the result is optimal.
          The <strong title="Filled (doctor, date, role) cells">Assignments</strong> column counts
          how many roster cells were filled in that snapshot.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="max-h-64 overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
          <table className="min-w-full divide-y divide-slate-200 text-xs dark:divide-slate-800">
            <thead className="bg-slate-50 text-left font-semibold text-slate-600 dark:bg-slate-900 dark:text-slate-300">
              <tr>
                <th className="px-2 py-1.5">#</th>
                <th className="px-2 py-1.5">t (s)</th>
                <th className="px-2 py-1.5" title="Current weighted-penalty total">Objective</th>
                <th className="px-2 py-1.5" title="Best lower bound the solver has proved">Bound</th>
                <th className="px-2 py-1.5" title="Filled (doctor, date, role) cells in this snapshot">Assignments</th>
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
