import { Copy, Diff, Download, Lock } from "lucide-react";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { ApiError, apiFetch } from "@/api/client";
import { useSessionState } from "@/api/hooks";
import { RosterHeatmap } from "@/components/RosterHeatmap";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { WorkloadTable } from "@/components/WorkloadTable";
import { computeWorkload, type Horizon } from "@/lib/roster";
import { cn } from "@/lib/utils";
import { type AssignmentRow, useSolveStore } from "@/store/solve";

type ViewMode = "heatmap" | "station";

export function Roster() {
  const { data } = useSessionState();
  const solve = useSolveStore();
  const [mode, setMode] = useState<ViewMode>("heatmap");
  const [diffAgainst, setDiffAgainst] = useState<"final" | number | null>(null);

  const events = solve.events;
  const result = solve.result;
  const selected = solve.selectedSnapshot;

  const selectedAssignments: AssignmentRow[] = useMemo(() => {
    if (!result) return [];
    if (selected === "final") return result.assignments ?? [];
    return events[selected]?.assignments ?? result.assignments ?? [];
  }, [result, events, selected]);

  const compareAssignments: AssignmentRow[] | null = useMemo(() => {
    if (diffAgainst == null || !result) return null;
    if (diffAgainst === "final") return result.assignments ?? [];
    return events[diffAgainst]?.assignments ?? null;
  }, [diffAgainst, result, events]);

  const diffKeys = useMemo(() => {
    if (!compareAssignments) return new Set<string>();
    const keyOf = (r: AssignmentRow) => `${r.doctor}|${r.date}|${r.role}`;
    const baseline = new Set(compareAssignments.map(keyOf));
    const current = new Set(selectedAssignments.map(keyOf));
    const changed = new Set<string>();
    for (const k of current) if (!baseline.has(k)) changed.add(cellKey(k));
    for (const k of baseline) if (!current.has(k)) changed.add(cellKey(k));
    return changed;
  }, [selectedAssignments, compareAssignments]);

  const doctors = data?.doctors ?? [];
  const horizon: Horizon = {
    start_date: data?.horizon?.start_date ?? null,
    n_days: data?.horizon?.n_days ?? 0,
    public_holidays: data?.horizon?.public_holidays ?? [],
  };
  const blocks = (data?.blocks ?? []) as Array<{
    doctor: string;
    date: string;
    end_date?: string | null;
    type: string;
  }>;

  const workload = useMemo(() => {
    if (!data) return [];
    return computeWorkload({
      doctors: doctors.map((d) => ({
        name: d.name,
        tier: d.tier,
        subspec: d.subspec,
        prev_workload: d.prev_workload,
      })),
      assignments: selectedAssignments,
      blocks,
      horizon,
      weights: {
        weekday_session: data.workload_weights?.weekday_session ?? 10,
        weekend_session: data.workload_weights?.weekend_session ?? 15,
        weekday_oncall: data.workload_weights?.weekday_oncall ?? 20,
        weekend_oncall: data.workload_weights?.weekend_oncall ?? 35,
        weekend_ext: data.workload_weights?.weekend_ext ?? 20,
        weekend_consult: data.workload_weights?.weekend_consult ?? 25,
      },
      hours: {
        weekday_am: data.hours?.weekday_am ?? 4,
        weekday_pm: data.hours?.weekday_pm ?? 4,
        weekend_am: data.hours?.weekend_am ?? 4,
        weekend_pm: data.hours?.weekend_pm ?? 4,
        weekday_oncall: data.hours?.weekday_oncall ?? 12,
        weekend_oncall: data.hours?.weekend_oncall ?? 16,
        weekend_ext: data.hours?.weekend_ext ?? 12,
        weekend_consult: data.hours?.weekend_consult ?? 8,
      },
    });
  }, [data, doctors, selectedAssignments, blocks, horizon]);

  const hasResult = !!result && selectedAssignments.length > 0;

  const lockToOverrides = async () => {
    try {
      const id = selected === "final" ? "final" : String(selected);
      const overrides = await apiFetch<unknown[]>("/api/overrides/fill-from-snapshot", {
        method: "POST",
        body: { snapshot_id: id },
      });
      toast.success(`Locked ${overrides.length} assignments to overrides.`);
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : "Failed to copy to overrides");
    }
  };

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Roster</h1>
          <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
            Review, edit, and re-solve.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ModeToggle mode={mode} setMode={setMode} />
          {hasResult && (
            <>
              <Button size="sm" variant="secondary" onClick={lockToOverrides}>
                <Lock className="h-4 w-4" />
                Lock to overrides
              </Button>
              <Button
                size="sm"
                variant="ghost"
                onClick={() =>
                  setDiffAgainst(diffAgainst == null ? (selected === "final" ? 0 : "final") : null)
                }
              >
                <Diff className="h-4 w-4" />
                {diffAgainst == null ? "Diff vs…" : "Hide diff"}
              </Button>
              <Button size="sm" variant="ghost" onClick={() => downloadAssignmentsCsv(selectedAssignments)}>
                <Download className="h-4 w-4" />
                CSV
              </Button>
            </>
          )}
        </div>
      </header>

      {!hasResult ? (
        <Card>
          <CardContent className="flex flex-col items-center gap-3 py-10 text-center text-sm text-slate-500 dark:text-slate-400">
            <Copy className="h-8 w-8 opacity-40" />
            No roster yet. Head to <strong className="text-slate-700 dark:text-slate-200">Solve</strong> and press Solve; the result
            will appear here.
          </CardContent>
        </Card>
      ) : (
        <>
          <SnapshotPicker />
          {diffAgainst != null && (
            <DiffBar
              against={diffAgainst}
              onPick={setDiffAgainst}
              total={events.length}
              diffCount={diffKeys.size}
            />
          )}
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
            <div className="min-w-0 space-y-4">
              {mode === "heatmap" && (
                <RosterHeatmap
                  doctors={doctors}
                  assignments={selectedAssignments}
                  blocks={blocks}
                  horizon={horizon}
                  highlightKeys={diffKeys}
                />
              )}
              {mode === "station" && (
                <StationByDate
                  assignments={selectedAssignments}
                  horizon={horizon}
                  stationNames={(data?.stations ?? []).map((s) => s.name)}
                />
              )}
              <Legend />
            </div>
            <div>
              <Card>
                <CardHeader>
                  <CardTitle>Workload</CardTitle>
                  <CardDescription>Per-doctor score, Δ vs tier median, hours/week.</CardDescription>
                </CardHeader>
                <CardContent>
                  <WorkloadTable
                    rows={workload}
                    tierLabels={
                      data?.tier_labels ?? {
                        junior: "Junior",
                        senior: "Senior",
                        consultant: "Consultant",
                      }
                    }
                  />
                </CardContent>
              </Card>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

function cellKey(fullKey: string) {
  // AssignmentRow key format: `${doctor}|${date}|${role}` → drop role for cell highlight.
  const [doctor, date] = fullKey.split("|");
  return `${doctor}|${date}`;
}

function ModeToggle({ mode, setMode }: { mode: ViewMode; setMode: (m: ViewMode) => void }) {
  const opts: Array<{ value: ViewMode; label: string }> = [
    { value: "heatmap", label: "Heatmap" },
    { value: "station", label: "Station × date" },
  ];
  return (
    <div className="inline-flex overflow-hidden rounded-md border border-slate-200 dark:border-slate-800">
      {opts.map((o) => (
        <button
          key={o.value}
          type="button"
          onClick={() => setMode(o.value)}
          className={cn(
            "px-3 py-1 text-xs font-medium transition-colors",
            mode === o.value
              ? "bg-indigo-600 text-white"
              : "bg-white text-slate-700 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function SnapshotPicker() {
  const events = useSolveStore((s) => s.events);
  const selected = useSolveStore((s) => s.selectedSnapshot);
  const select = useSolveStore((s) => s.selectSnapshot);
  if (events.length === 0) return null;
  const value = selected === "final" ? events.length : (selected as number);
  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-3 py-3">
        <label className="flex-1">
          <div className="mb-1 flex items-center justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>Snapshot</span>
            <span>
              {selected === "final"
                ? `Final (of ${events.length + 1})`
                : `Intermediate ${selected + 1} of ${events.length + 1}`}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={events.length}
            step={1}
            value={value}
            onChange={(e) => {
              const v = Number(e.target.value);
              select(v >= events.length ? "final" : v);
            }}
            className="w-full"
          />
        </label>
        <Button size="sm" variant="ghost" onClick={() => select("final")}>
          Final
        </Button>
      </CardContent>
    </Card>
  );
}

function DiffBar({
  against,
  onPick,
  total,
  diffCount,
}: {
  against: "final" | number;
  onPick: (a: "final" | number | null) => void;
  total: number;
  diffCount: number;
}) {
  return (
    <Card className="border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/40">
      <CardContent className="flex flex-wrap items-center gap-3 py-3 text-sm">
        <span className="font-medium">Diff against</span>
        <select
          className="h-8 rounded-md border border-slate-300 bg-white px-2 text-xs dark:border-slate-700 dark:bg-slate-900"
          value={against === "final" ? "final" : String(against)}
          onChange={(e) =>
            onPick(e.target.value === "final" ? "final" : Number(e.target.value))
          }
        >
          <option value="final">Final</option>
          {Array.from({ length: total }, (_, i) => (
            <option key={i} value={i}>
              Intermediate {i + 1}
            </option>
          ))}
        </select>
        <span className="text-xs text-amber-900 dark:text-amber-200">
          {diffCount} cell{diffCount === 1 ? "" : "s"} differ
        </span>
        <Button size="sm" variant="ghost" onClick={() => onPick(null)}>
          Close
        </Button>
      </CardContent>
    </Card>
  );
}

function Legend() {
  const items: Array<[string, string]> = [
    ["Station (AM+PM)", "bg-emerald-200"],
    ["Station (one session)", "bg-emerald-100"],
    ["On-call", "bg-purple-200"],
    ["Weekend EXT/WC", "bg-teal-200"],
    ["Leave", "bg-slate-200"],
    ["Idle weekday", "bg-amber-200"],
  ];
  return (
    <div className="flex flex-wrap items-center gap-3 text-xs text-slate-600 dark:text-slate-400">
      {items.map(([label, cls]) => (
        <span key={label} className="inline-flex items-center gap-1.5">
          <span className={cn("h-3 w-3 rounded-sm border border-slate-300 dark:border-slate-700", cls)} />
          {label}
        </span>
      ))}
    </div>
  );
}

function StationByDate({
  assignments,
  horizon,
  stationNames,
}: {
  assignments: AssignmentRow[];
  horizon: Horizon;
  stationNames: string[];
}) {
  const rows: Array<{ role: string; byDate: Map<string, string[]> }> = [];
  const byRole = new Map<string, Map<string, string[]>>();

  const push = (role: string, date: string, doctor: string) => {
    if (!byRole.has(role)) byRole.set(role, new Map());
    const m = byRole.get(role)!;
    const list = m.get(date) ?? [];
    list.push(doctor);
    m.set(date, list);
  };

  for (const a of assignments) push(a.role, a.date, a.doctor);

  const dates = Array.from({ length: horizon.n_days }, (_, i) => {
    if (!horizon.start_date) return "";
    const d = new Date(horizon.start_date);
    d.setDate(d.getDate() + i);
    return d.toISOString().slice(0, 10);
  }).filter(Boolean);

  const ordered: string[] = [];
  for (const s of stationNames) {
    ordered.push(`STATION_${s}_AM`, `STATION_${s}_PM`);
  }
  ordered.push("ONCALL", "WEEKEND_EXT", "WEEKEND_CONSULT");

  for (const role of ordered) {
    const m = byRole.get(role);
    if (!m) continue;
    rows.push({ role, byDate: m });
  }

  if (rows.length === 0) return null;
  return (
    <div className="overflow-auto rounded-md border border-slate-200 dark:border-slate-800">
      <table className="min-w-full text-[11px]">
        <thead className="sticky top-0 bg-slate-50 dark:bg-slate-900">
          <tr>
            <th className="sticky left-0 z-10 min-w-[12rem] border-b border-r border-slate-200 bg-slate-50 px-2 py-1.5 text-left font-semibold dark:border-slate-800 dark:bg-slate-900">
              Role
            </th>
            {dates.map((d) => (
              <th
                key={d}
                className="border-b border-r border-slate-200 px-1.5 py-1 text-center font-medium dark:border-slate-800"
              >
                {d.slice(5)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ role, byDate }) => (
            <tr key={role}>
              <td className="sticky left-0 z-10 min-w-[12rem] border-b border-r border-slate-200 bg-white px-2 py-1 font-medium dark:border-slate-800 dark:bg-slate-950">
                {role}
              </td>
              {dates.map((d) => (
                <td
                  key={d}
                  className="border-b border-r border-slate-200 px-1 py-1 text-center align-middle dark:border-slate-800"
                >
                  {(byDate.get(d) ?? []).join(", ") || <span className="text-slate-300 dark:text-slate-600">·</span>}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function downloadAssignmentsCsv(rows: AssignmentRow[]) {
  const header = "doctor,date,role\n";
  const body = rows.map((r) => `${r.doctor},${r.date},${r.role}`).join("\n");
  const blob = new Blob([header + body], { type: "text/csv" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `roster_${new Date().toISOString().slice(0, 10)}.csv`;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(a.href);
}
