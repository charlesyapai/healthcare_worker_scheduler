/**
 * /lab/fairness — deep-dive bias audit for one recorded run.
 *
 * Reuses FairnessView over a SingleRunDetail's stored fairness payload,
 * so no extra backend call is needed beyond fetching the batch detail.
 * Per `docs/LAB_TAB_SPEC.md §4`.
 */

import { useMemo, useState } from "react";

import {
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
