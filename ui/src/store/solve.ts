/**
 * Solve-session store. Holds the streamed events, final result, and the
 * currently-selected snapshot index. Populated by the Solve page's
 * WebSocket driver; consumed by the Roster page.
 */

import { create } from "zustand";

// WebSocket payloads are NOT in the OpenAPI schema (FastAPI only exposes REST
// types there), so these mirror api/models/events.py by hand.
export interface AssignmentRow {
  doctor: string;
  date: string; // ISO date
  role: string;
}

export interface SolveEvent {
  type: "event";
  wall_s: number;
  objective: number | null;
  best_bound: number | null;
  components: Record<string, number>;
  assignments: AssignmentRow[] | null;
}

export interface SelfCheckViolation {
  rule: string;
  severity: string;
  location: string;
  message: string;
}

export interface SolverSelfCheck {
  ok: boolean;
  violation_count: number;
  rules_passed: string[];
  rules_failed: string[];
  violations: SelfCheckViolation[];
}

export interface SolveResultPayload {
  status: string;
  wall_time_s: number;
  objective: number | null;
  best_bound: number | null;
  n_vars: number;
  n_constraints: number;
  first_feasible_s: number | null;
  penalty_components: Record<string, number>;
  assignments: AssignmentRow[];
  intermediate: SolveEvent[];
  self_check?: SolverSelfCheck | null;
}

export type SolveStatus = "idle" | "running" | "done" | "error";
export type SolveMode = "ws" | "rest";

interface SolveState {
  status: SolveStatus;
  mode: SolveMode;
  startedAt: number | null;
  events: SolveEvent[];
  result: SolveResultPayload | null;
  errorMessage: string | null;
  selectedSnapshot: "final" | number;
  /** Set by `beginContinue` — held through the new run so `finish` can
   * decide whether to keep the incoming result or roll back if the new
   * run found nothing better. */
  previousBest: SolveResultPayload | null;

  begin: (mode?: SolveMode) => void;
  beginContinue: (mode?: SolveMode) => void;
  pushEvent: (e: SolveEvent) => void;
  finish: (r: SolveResultPayload) => {
    kept: "new" | "previous";
    previous: SolveResultPayload | null;
  };
  fail: (message: string) => void;
  reset: () => void;
  selectSnapshot: (snap: "final" | number) => void;
}

export const useSolveStore = create<SolveState>((set, get) => ({
  status: "idle",
  mode: "ws",
  startedAt: null,
  events: [],
  result: null,
  errorMessage: null,
  selectedSnapshot: "final",
  previousBest: null,

  begin: (mode = "ws") =>
    set({
      status: "running",
      mode,
      startedAt: Date.now(),
      events: [],
      result: null,
      errorMessage: null,
      selectedSnapshot: "final",
      previousBest: null,
    }),
  beginContinue: (mode = "ws") => {
    const prev = get().result;
    set({
      status: "running",
      mode,
      startedAt: Date.now(),
      events: [],
      result: null,
      errorMessage: null,
      selectedSnapshot: "final",
      previousBest: prev,
    });
  },
  pushEvent: (e) => set((s) => ({ events: [...s.events, e] })),
  finish: (r) => {
    const prev = get().previousBest;
    const incoming = r.objective ?? Infinity;
    const previous = prev?.objective ?? Infinity;
    if (prev != null && incoming > previous) {
      // New run didn't improve — roll back to the previous best so the
      // user never loses ground by clicking Continue.
      set({
        status: "done",
        result: prev,
        previousBest: null,
        selectedSnapshot: "final",
      });
      return { kept: "previous", previous: prev };
    }
    set({
      status: "done",
      result: r,
      previousBest: null,
      selectedSnapshot: "final",
    });
    return { kept: "new", previous: prev };
  },
  fail: (message) => set({ status: "error", errorMessage: message, previousBest: null }),
  reset: () =>
    set({
      status: "idle",
      mode: "ws",
      startedAt: null,
      events: [],
      result: null,
      errorMessage: null,
      selectedSnapshot: "final",
      previousBest: null,
    }),
  selectSnapshot: (snap) => set({ selectedSnapshot: snap }),
}));
