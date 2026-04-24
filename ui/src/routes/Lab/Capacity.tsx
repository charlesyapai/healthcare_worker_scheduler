/**
 * /lab/capacity — manpower analysis.
 *
 * Answers one question a coordinator actually asks: "Do I have the
 * right number of people for this workload?". Two concrete modes:
 *
 *  - **Hours vs target** — one solve, then compare each doctor's
 *    weekly hours (actual) to an FTE-scaled target. Shows who's
 *    under- or over-loaded at a glance.
 *  - **Team reduction** — iteratively drops the lowest-loaded doctor
 *    and re-solves. Reports the minimum viable team size before
 *    coverage or rule compliance breaks.
 */

import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  BookOpen,
  CheckCircle2,
  Minus,
  Play,
  Target,
  Users,
} from "lucide-react";
import { useMemo, useState } from "react";
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
import { cn } from "@/lib/utils";

type CapacityMode = "hours_vs_target" | "team_reduction";

interface HoursPerDoctor {
  doctor_id: number;
  doctor_name: string;
  tier: string;
  fte: number;
  actual_hours: number;
  target_hours: number;
  delta: number;
  status: "under" | "on_target" | "over";
  sessions: number;
  oncalls: number;
  weekend_duties: number;
}

interface TierWorkload {
  tier: string;
  headcount: number;
  total_fte: number;
  total_hours: number;
  mean_weekly_hours: number;
  share_of_total_hours: number;
  share_of_fte: number;
  sessions: number;
  oncalls: number;
  weekend_duties: number;
}

interface ReductionCell {
  step: number;
  team_size: number;
  removed: string[];
  status: string;
  wall_time_s: number;
  objective: number | null;
  coverage_shortfall: number;
  coverage_over: number;
  self_check_ok: boolean | null;
  violation_count: number | null;
}

interface CapacityResponse {
  batch_id: string;
  created_at: string;
  mode: CapacityMode;
  time_limit_s: number;
  per_doctor: HoursPerDoctor[];
  per_tier: TierWorkload[];
  target_hours_per_week: number | null;
  reduction: ReductionCell[];
  min_viable_team_size: number | null;
}

export function LabCapacity() {
  const [mode, setMode] = useState<CapacityMode>("hours_vs_target");
  const [target, setTarget] = useState(40);
  const [maxDrop, setMaxDrop] = useState(3);
  const [timeLimit, setTimeLimit] = useState(15);
  const [running, setRunning] = useState(false);
  const [resp, setResp] = useState<CapacityResponse | null>(null);

  const kickoff = async () => {
    setRunning(true);
    setResp(null);
    try {
      const body =
        mode === "hours_vs_target"
          ? {
              mode,
              target_hours_per_week: target,
              time_limit_s: timeLimit,
              num_workers: 2,
              max_drop: 1,
            }
          : {
              mode,
              max_drop: maxDrop,
              time_limit_s: timeLimit,
              num_workers: 2,
              target_hours_per_week: target,
            };
      const r = await apiFetch<CapacityResponse>("/api/lab/capacity/run", {
        method: "POST",
        body,
      });
      setResp(r);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Capacity run failed.");
    } finally {
      setRunning(false);
    }
  };

  const estimatedWallS =
    mode === "hours_vs_target"
      ? timeLimit
      : (maxDrop + 1) * timeLimit;

  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_1fr]">
      <Card>
        <CardHeader>
          <CardTitle>Capacity config</CardTitle>
          <CardDescription>
            Pick the question you want answered. This tab runs on the{" "}
            <strong>currently-loaded session state</strong> (whatever's
            in Setup) — load a template first if you don't have one.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-xs">
          <div
            role="radiogroup"
            aria-label="Capacity mode"
            className="space-y-1.5"
          >
            <ModeOption
              active={mode === "hours_vs_target"}
              onSelect={() => setMode("hours_vs_target")}
              icon={Target}
              label="Hours vs target"
              body="Solve once, then check each doctor's weekly hours against a target. Who's under-loaded? Who's over?"
              runtime="~1 solve"
            />
            <ModeOption
              active={mode === "team_reduction"}
              onSelect={() => setMode("team_reduction")}
              icon={Users}
              label="Team reduction"
              body="Drop the lowest-loaded doctor, re-solve. Repeat. Surfaces the minimum viable team size."
              runtime={`~${maxDrop + 1} solves`}
            />
          </div>

          {mode === "hours_vs_target" ? (
            <label className="block">
              <span className="text-[10px] uppercase tracking-wide text-slate-500">
                Target hours / week (scaled by FTE)
              </span>
              <Input
                type="number"
                min={1}
                max={80}
                step={0.5}
                className="mt-1 h-8 text-right text-xs"
                value={target}
                onChange={(e) =>
                  setTarget(Math.max(1, Math.min(80, Number(e.target.value) || 40)))
                }
              />
            </label>
          ) : (
            <label className="block">
              <span className="text-[10px] uppercase tracking-wide text-slate-500">
                Maximum doctors to drop
              </span>
              <Input
                type="number"
                min={1}
                max={10}
                className="mt-1 h-8 text-right text-xs"
                value={maxDrop}
                onChange={(e) =>
                  setMaxDrop(Math.max(1, Math.min(10, Number(e.target.value) || 3)))
                }
              />
            </label>
          )}

          <label className="block">
            <span className="text-[10px] uppercase tracking-wide text-slate-500">
              Time per solve (s)
            </span>
            <Input
              type="number"
              min={5}
              max={60}
              className="mt-1 h-8 text-right text-xs"
              value={timeLimit}
              onChange={(e) =>
                setTimeLimit(Math.max(5, Math.min(60, Number(e.target.value) || 15)))
              }
            />
          </label>

          <p className="rounded-md border border-indigo-200 bg-indigo-50 p-2 text-[11px] dark:border-indigo-900 dark:bg-indigo-950/40">
            Wall-time budget ≤ <strong>{estimatedWallS}s</strong>
            {mode === "team_reduction" &&
              ` (${maxDrop + 1} solves at ${timeLimit}s each)`}
            .
          </p>
          <Button className="w-full" onClick={kickoff} disabled={running}>
            <Play className="h-4 w-4" />
            {running ? "Running…" : "Run analysis"}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-4">
        <CapacityIntro mode={mode} />
        {resp == null ? (
          running ? (
            <Card>
              <CardContent className="flex items-center gap-3 py-6 text-sm text-slate-500 dark:text-slate-400">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                Running capacity analysis. Budget ≤ {estimatedWallS}s. Don't close the tab.
              </CardContent>
            </Card>
          ) : (
            <Card>
              <CardContent className="py-10 text-center text-sm text-slate-500 dark:text-slate-400">
                Pick a mode on the left and press <strong>Run analysis</strong>.
              </CardContent>
            </Card>
          )
        ) : resp.mode === "hours_vs_target" ? (
          <HoursVsTargetResults resp={resp} />
        ) : (
          <TeamReductionResults resp={resp} />
        )}
      </div>
    </div>
  );
}

function ModeOption({
  active,
  onSelect,
  icon: Icon,
  label,
  body,
  runtime,
}: {
  active: boolean;
  onSelect: () => void;
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  body: string;
  runtime: string;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={active}
      onClick={onSelect}
      className={cn(
        "flex w-full items-start gap-2 rounded-md border p-2 text-left transition-colors",
        active
          ? "border-indigo-500 bg-indigo-50 ring-1 ring-indigo-200 dark:border-indigo-400 dark:bg-indigo-950 dark:ring-indigo-900"
          : "border-slate-200 bg-white hover:border-slate-400 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-900 dark:hover:border-slate-500 dark:hover:bg-slate-800",
      )}
    >
      <Icon
        className={cn(
          "mt-0.5 h-3.5 w-3.5 flex-shrink-0",
          active
            ? "text-indigo-600 dark:text-indigo-300"
            : "text-slate-500 dark:text-slate-400",
        )}
      />
      <div className="min-w-0 flex-1">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold">{label}</span>
          <span className="text-[10px] text-slate-500 dark:text-slate-400">
            {runtime}
          </span>
        </div>
        <p className="mt-0.5 text-[11px] text-slate-600 dark:text-slate-400">
          {body}
        </p>
      </div>
    </button>
  );
}

function CapacityIntro({ mode }: { mode: CapacityMode }) {
  return (
    <Card className="border-indigo-200 bg-indigo-50/50 dark:border-indigo-900 dark:bg-indigo-950/30">
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          <BookOpen className="h-4 w-4 text-indigo-600 dark:text-indigo-300" />
          <CardTitle className="text-sm">
            {mode === "hours_vs_target"
              ? "Does everyone hit their hours target?"
              : "How small can the team be?"}
          </CardTitle>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 text-xs text-slate-700 dark:text-slate-300">
        {mode === "hours_vs_target" ? (
          <>
            <p>
              Solve the current scenario once, then compute each doctor's
              total worked hours (from the session's Hours config) and
              express as a weekly rate. Compare against{" "}
              <strong>target_hours × fte</strong>.
            </p>
            <p>
              <strong>Use this to find:</strong> under-loaded people you
              could give additional sessions to, over-loaded people who
              need their fte revisited, or a whole-team mismatch that
              suggests your target is set wrong.
            </p>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              "On target" means within <strong>max(2h, 10%)</strong> of
              the target — tighter than that is statistical noise.
            </p>
          </>
        ) : (
          <>
            <p>
              Solve with the full team to get a baseline. Then remove
              the doctor with the fewest assignments and re-solve.
              Repeat up to <strong>max_drop</strong> times or until the
              roster stops filling.
            </p>
            <p>
              <strong>Use this to answer:</strong> "If my department
              loses 2 people next quarter, can we still cover?" or "Am I
              paying for heads I don't need?".
            </p>
            <p className="text-[11px] text-slate-500 dark:text-slate-400">
              The drop-order heuristic is load-based, not clinical —
              treat the minimum viable size as a ceiling, not a
              recommendation. A bigger solve budget will push that
              ceiling up.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function HoursVsTargetResults({ resp }: { resp: CapacityResponse }) {
  const total = resp.per_doctor.length;
  const under = resp.per_doctor.filter((p) => p.status === "under").length;
  const onTarget = resp.per_doctor.filter((p) => p.status === "on_target").length;
  const over = resp.per_doctor.filter((p) => p.status === "over").length;

  const maxAbsDelta = useMemo(
    () =>
      Math.max(
        1,
        ...resp.per_doctor.map((p) => Math.abs(p.delta)),
      ),
    [resp.per_doctor],
  );

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Summary</CardTitle>
          <CardDescription>
            Target: <strong>{resp.target_hours_per_week ?? "—"}h/week</strong>{" "}
            × FTE. Results from one solve at{" "}
            <strong>{resp.time_limit_s}s</strong> budget.
          </CardDescription>
        </CardHeader>
        <CardContent className="grid gap-2 sm:grid-cols-3">
          <StatCard
            tint="rose"
            icon={ArrowDown}
            label="Under-loaded"
            value={`${under}/${total}`}
          />
          <StatCard
            tint="emerald"
            icon={CheckCircle2}
            label="On target"
            value={`${onTarget}/${total}`}
          />
          <StatCard
            tint="amber"
            icon={ArrowUp}
            label="Over-loaded"
            value={`${over}/${total}`}
          />
        </CardContent>
      </Card>

      {resp.per_tier.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle>By tier</CardTitle>
            <CardDescription>
              How the total workload is divided among juniors, seniors,
              and consultants. A tier whose share of hours is far
              bigger than its share of FTE is carrying the team; a
              tier whose share is far smaller is under-used.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-slate-500 dark:text-slate-400">
                  <th className="py-1">Tier</th>
                  <th className="py-1 text-right">Head</th>
                  <th className="py-1 text-right">FTE</th>
                  <th className="py-1 text-right">Mean h/wk</th>
                  <th className="py-1 text-right">Sessions</th>
                  <th className="py-1 text-right">On-calls</th>
                  <th className="py-1 text-right">Weekend</th>
                  <th className="py-1">Load vs FTE share</th>
                </tr>
              </thead>
              <tbody>
                {resp.per_tier.map((t) => (
                  <TierRow key={t.tier} t={t} />
                ))}
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader className="pb-2">
          <CardTitle>Per-doctor</CardTitle>
          <CardDescription>
            Sorted by delta (under → over). Bars show actual vs target.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-0.5">
            {resp.per_doctor.map((p) => (
              <HoursBar key={p.doctor_name} p={p} maxAbs={maxAbsDelta} />
            ))}
          </div>
        </CardContent>
      </Card>
    </>
  );
}

function TierRow({ t }: { t: TierWorkload }) {
  const hoursPct = Math.round(t.share_of_total_hours * 100);
  const ftePct = Math.round(t.share_of_fte * 100);
  // Positive means carrying more than FTE share; negative means under-used.
  const skew = hoursPct - ftePct;
  const skewCls =
    skew > 5
      ? "text-amber-700 dark:text-amber-300"
      : skew < -5
        ? "text-sky-700 dark:text-sky-300"
        : "text-emerald-700 dark:text-emerald-300";
  return (
    <tr>
      <td className="py-1 font-medium capitalize">{t.tier}</td>
      <td className="py-1 text-right font-mono">{t.headcount}</td>
      <td className="py-1 text-right font-mono">{t.total_fte.toFixed(1)}</td>
      <td className="py-1 text-right font-mono">
        {t.mean_weekly_hours.toFixed(1)}
      </td>
      <td className="py-1 text-right font-mono">{t.sessions}</td>
      <td className="py-1 text-right font-mono">{t.oncalls}</td>
      <td className="py-1 text-right font-mono">{t.weekend_duties}</td>
      <td className="py-1">
        <div className="flex items-center gap-2">
          <div className="relative h-4 w-32 overflow-hidden rounded bg-slate-100 dark:bg-slate-800">
            <div
              className="absolute left-0 top-0 h-full bg-slate-400 dark:bg-slate-500"
              style={{ width: `${ftePct}%` }}
              title={`FTE share: ${ftePct}%`}
            />
            <div
              className="absolute left-0 top-0 h-full border-r-2 border-indigo-600 dark:border-indigo-400"
              style={{ width: `${hoursPct}%` }}
              title={`Hours share: ${hoursPct}%`}
            />
          </div>
          <span className={cn("whitespace-nowrap font-mono text-[10px]", skewCls)}>
            {skew >= 0 ? "+" : ""}
            {skew}pp
          </span>
        </div>
      </td>
    </tr>
  );
}

function HoursBar({ p, maxAbs }: { p: HoursPerDoctor; maxAbs: number }) {
  const pct = Math.min(100, (Math.abs(p.delta) / maxAbs) * 100);
  const isUnder = p.status === "under";
  const isOver = p.status === "over";
  return (
    <div className="grid grid-cols-[10rem_1fr_auto] items-center gap-2 py-1 text-[11px]">
      <div className="flex items-center gap-1 font-medium">
        <span className="truncate">{p.doctor_name}</span>
        {p.fte !== 1 && (
          <span className="rounded bg-slate-100 px-1 text-[9px] text-slate-600 dark:bg-slate-800 dark:text-slate-300">
            {p.fte.toFixed(2)}fte
          </span>
        )}
      </div>
      <div className="relative h-4 rounded bg-slate-100 dark:bg-slate-800">
        <div className="absolute left-1/2 top-0 h-full w-px bg-slate-400 dark:bg-slate-500" />
        <div
          className={cn(
            "absolute top-0 h-full rounded",
            isUnder && "bg-rose-400 dark:bg-rose-600",
            isOver && "bg-amber-400 dark:bg-amber-600",
            !isUnder && !isOver && "bg-emerald-400 dark:bg-emerald-600",
          )}
          style={{
            width: `${pct / 2}%`,
            left: isOver ? "50%" : `${50 - pct / 2}%`,
          }}
        />
      </div>
      <div className="flex items-center gap-1 whitespace-nowrap font-mono text-[10px]">
        <span>{p.actual_hours}h</span>
        <span className="text-slate-400">·</span>
        <span
          className={cn(
            "font-semibold",
            isUnder && "text-rose-700 dark:text-rose-300",
            isOver && "text-amber-700 dark:text-amber-300",
            !isUnder && !isOver && "text-emerald-700 dark:text-emerald-300",
          )}
        >
          {p.delta >= 0 ? "+" : ""}
          {p.delta.toFixed(1)}
        </span>
      </div>
    </div>
  );
}

function StatCard({
  tint,
  icon: Icon,
  label,
  value,
}: {
  tint: "rose" | "emerald" | "amber";
  icon: React.ComponentType<{ className?: string }>;
  label: string;
  value: string;
}) {
  const cls =
    tint === "rose"
      ? "border-rose-300 bg-rose-50 text-rose-800 dark:border-rose-800 dark:bg-rose-950 dark:text-rose-200"
      : tint === "amber"
        ? "border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        : "border-emerald-300 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950 dark:text-emerald-200";
  return (
    <div className={cn("rounded-md border p-2", cls)}>
      <div className="flex items-center gap-1 text-[10px] uppercase tracking-wide">
        <Icon className="h-3 w-3" />
        {label}
      </div>
      <div className="mt-1 font-mono text-lg font-semibold">{value}</div>
    </div>
  );
}

function TeamReductionResults({ resp }: { resp: CapacityResponse }) {
  const baseline = resp.reduction.find((c) => c.step === 0);
  const minViable = resp.min_viable_team_size;

  return (
    <>
      <Card>
        <CardHeader className="pb-3">
          <CardTitle>Summary</CardTitle>
          <CardDescription>
            Started at <strong>{baseline?.team_size ?? "?"}</strong>{" "}
            doctors. Minimum team that still held the roster:{" "}
            <strong>{minViable ?? "—"}</strong>.{" "}
            {minViable != null && baseline != null && (
              <span>
                That's{" "}
                <strong>{baseline.team_size - minViable}</strong>{" "}
                {baseline.team_size - minViable === 1 ? "head" : "heads"}{" "}
                of potential slack.
              </span>
            )}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <table className="w-full text-xs">
            <thead>
              <tr className="text-left text-slate-500 dark:text-slate-400">
                <th className="py-1">Step</th>
                <th className="py-1">Team size</th>
                <th className="py-1">Dropped</th>
                <th className="py-1">Status</th>
                <th className="py-1 text-right">Objective</th>
                <th className="py-1 text-right">Shortfall</th>
                <th className="py-1 text-right">Violations</th>
                <th className="py-1 text-right">Wall</th>
              </tr>
            </thead>
            <tbody>
              {resp.reduction.map((c) => {
                const viable =
                  c.status in { OPTIMAL: 1, FEASIBLE: 1 } &&
                  c.coverage_shortfall === 0 &&
                  c.self_check_ok !== false;
                return (
                  <tr
                    key={c.step}
                    className={cn(
                      viable
                        ? ""
                        : "bg-rose-50/50 dark:bg-rose-950/20",
                    )}
                  >
                    <td className="py-1 font-mono">{c.step}</td>
                    <td className="py-1 font-mono">{c.team_size}</td>
                    <td className="py-1 text-[11px] text-slate-600 dark:text-slate-400">
                      {c.removed.length === 0 ? (
                        <span className="italic">— full team</span>
                      ) : (
                        c.removed.map((n) => (
                          <span
                            key={n}
                            className="mr-1 inline-flex items-center gap-0.5"
                          >
                            <Minus className="h-3 w-3" />
                            {n}
                          </span>
                        ))
                      )}
                    </td>
                    <td className="py-1 font-mono text-[11px]">
                      {c.status}
                    </td>
                    <td className="py-1 text-right font-mono">
                      {c.objective == null ? "—" : c.objective.toFixed(0)}
                    </td>
                    <td
                      className={cn(
                        "py-1 text-right font-mono",
                        c.coverage_shortfall > 0
                          ? "text-rose-700 dark:text-rose-300"
                          : "",
                      )}
                    >
                      {c.coverage_shortfall}
                    </td>
                    <td
                      className={cn(
                        "py-1 text-right font-mono",
                        (c.violation_count ?? 0) > 0
                          ? "text-rose-700 dark:text-rose-300"
                          : "",
                      )}
                    >
                      {c.violation_count ?? "—"}
                    </td>
                    <td className="py-1 text-right font-mono text-[11px]">
                      {c.wall_time_s.toFixed(1)}s
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </>
  );
}
