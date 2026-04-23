/**
 * Persistent state for the /lab/benchmark run in progress.
 *
 * The previous implementation stored the result in a `useMutation`
 * return, which is component-local — switching tabs lost everything.
 * This Zustand store lives at module scope so the Lab pages can
 * re-read state after a tab switch, and so per-cell progress updates
 * land on the same object the renderer is already reading.
 *
 * We also changed the batch execution model: instead of one big POST
 * that blocks the UI for a minute, the client fires one POST per
 * (solver × seed) cell and updates the store after each. The user
 * sees table rows light up one at a time plus a live elapsed/ETA
 * banner.
 */

import { create } from "zustand";

import type {
  RunConfig,
  SingleRun,
  SolverKey,
} from "@/api/hooks";

export interface PlannedCell {
  solver: SolverKey;
  seed: number;
}

export interface CellBatchRef {
  batchId: string;
  solver: SolverKey;
  seed: number;
}

export interface Aggregates {
  feasibility_rate: Record<string, number>;
  mean_objective: Record<string, number | null>;
  mean_shortfall: Record<string, number>;
  quality_ratios: Record<string, number>;
}

export interface LabBatchState {
  status: "idle" | "running" | "done" | "error";
  planned: PlannedCell[];
  runConfig: RunConfig | null;
  /** Per-cell SolveResult-summary rows, in completion order. */
  runs: SingleRun[];
  /** Per-cell batch-id pointers so the bundle button can fetch the
   *  latest bundle. Older cells stay in memory for now; later we may
   *  add a compound-bundle endpoint. */
  batchRefs: CellBatchRef[];
  /** Snapshot of the first cell's instance metadata — used for labels. */
  instanceLabel: string | null;
  nDoctors: number | null;
  nDays: number | null;
  /** ms epoch when the batch started; null when idle. */
  startedAt: number | null;
  completedAt: number | null;
  /** The currently-executing cell, if any. */
  currentCell:
    | { solver: SolverKey; seed: number; index: number; startedAt: number }
    | null;
  lastError: string | null;
  /** Re-computed on every cell completion so the reliability-banner
   *  + comparison charts always read the latest numbers. */
  aggregates: Aggregates;

  /** Begin a new batch: reset everything, record the plan. */
  begin(planned: PlannedCell[], runConfig: RunConfig): void;
  /** Mark a specific cell as in-flight so the progress banner can show
   *  the per-cell timer. */
  startCell(index: number): void;
  /** One cell finished — append the run + re-compute aggregates. */
  completeCell(run: SingleRun, ref: CellBatchRef, meta?: {
    instanceLabel?: string;
    nDoctors?: number;
    nDays?: number;
  }): void;
  fail(message: string): void;
  finish(): void;
  reset(): void;
}

function emptyAggregates(): Aggregates {
  return {
    feasibility_rate: {},
    mean_objective: {},
    mean_shortfall: {},
    quality_ratios: {},
  };
}

/** Recompute feasibility_rate / mean_objective / mean_shortfall /
 *  quality_ratios from the runs-so-far list. Keeps the aggregates in
 *  step with what the user sees after each cell completes. */
function recomputeAggregates(runs: SingleRun[]): Aggregates {
  const bySolver: Record<string, SingleRun[]> = {};
  for (const r of runs) {
    (bySolver[r.solver] ??= []).push(r);
  }
  const out = emptyAggregates();
  for (const [solver, group] of Object.entries(bySolver)) {
    const feas = group.filter((g) => g.self_check_ok).length;
    out.feasibility_rate[solver] = group.length
      ? round(feas / group.length, 3)
      : 0;
    const objs = group
      .map((g) => g.objective)
      .filter((o): o is number => o != null);
    out.mean_objective[solver] = objs.length
      ? round(objs.reduce((s, v) => s + v, 0) / objs.length, 2)
      : null;
    const shorts = group.map((g) => g.coverage_shortfall);
    out.mean_shortfall[solver] = shorts.length
      ? round(shorts.reduce((s, v) => s + v, 0) / shorts.length, 2)
      : 0;
  }
  const ours = out.mean_objective["cpsat"];
  if (ours != null && ours > 0) {
    for (const [s, m] of Object.entries(out.mean_objective)) {
      if (s === "cpsat" || m == null || m <= 0) continue;
      out.quality_ratios[`cpsat_vs_${s}`] = round(m / ours, 3);
    }
  }
  return out;
}

function round(n: number, digits: number): number {
  const f = 10 ** digits;
  return Math.round(n * f) / f;
}

export const useLabBatchStore = create<LabBatchState>((set) => ({
  status: "idle",
  planned: [],
  runConfig: null,
  runs: [],
  batchRefs: [],
  instanceLabel: null,
  nDoctors: null,
  nDays: null,
  startedAt: null,
  completedAt: null,
  currentCell: null,
  lastError: null,
  aggregates: emptyAggregates(),

  begin: (planned, runConfig) =>
    set({
      status: "running",
      planned,
      runConfig,
      runs: [],
      batchRefs: [],
      instanceLabel: null,
      nDoctors: null,
      nDays: null,
      startedAt: Date.now(),
      completedAt: null,
      currentCell: null,
      lastError: null,
      aggregates: emptyAggregates(),
    }),

  startCell: (index) =>
    set((s) => {
      const cell = s.planned[index];
      if (!cell) return s;
      return {
        currentCell: {
          solver: cell.solver,
          seed: cell.seed,
          index,
          startedAt: Date.now(),
        },
      };
    }),

  completeCell: (run, ref, meta) =>
    set((s) => {
      const runs = [...s.runs, run];
      return {
        runs,
        batchRefs: [...s.batchRefs, ref],
        currentCell: null,
        aggregates: recomputeAggregates(runs),
        instanceLabel: s.instanceLabel ?? meta?.instanceLabel ?? null,
        nDoctors: s.nDoctors ?? meta?.nDoctors ?? null,
        nDays: s.nDays ?? meta?.nDays ?? null,
      };
    }),

  fail: (message) =>
    set((s) => ({
      status: "error",
      lastError: message,
      currentCell: null,
      completedAt: s.completedAt ?? Date.now(),
    })),

  finish: () =>
    set({
      status: "done",
      currentCell: null,
      completedAt: Date.now(),
    }),

  reset: () =>
    set({
      status: "idle",
      planned: [],
      runConfig: null,
      runs: [],
      batchRefs: [],
      instanceLabel: null,
      nDoctors: null,
      nDays: null,
      startedAt: null,
      completedAt: null,
      currentCell: null,
      lastError: null,
      aggregates: emptyAggregates(),
    }),
}));
