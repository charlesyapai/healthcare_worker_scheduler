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
}

export type SolveStatus = "idle" | "running" | "done" | "error";

interface SolveState {
  status: SolveStatus;
  startedAt: number | null;
  events: SolveEvent[];
  result: SolveResultPayload | null;
  errorMessage: string | null;
  selectedSnapshot: "final" | number;

  begin: () => void;
  pushEvent: (e: SolveEvent) => void;
  finish: (r: SolveResultPayload) => void;
  fail: (message: string) => void;
  reset: () => void;
  selectSnapshot: (snap: "final" | number) => void;
}

export const useSolveStore = create<SolveState>((set) => ({
  status: "idle",
  startedAt: null,
  events: [],
  result: null,
  errorMessage: null,
  selectedSnapshot: "final",

  begin: () =>
    set({
      status: "running",
      startedAt: Date.now(),
      events: [],
      result: null,
      errorMessage: null,
      selectedSnapshot: "final",
    }),
  pushEvent: (e) => set((s) => ({ events: [...s.events, e] })),
  finish: (r) => set({ status: "done", result: r, selectedSnapshot: "final" }),
  fail: (message) => set({ status: "error", errorMessage: message }),
  reset: () =>
    set({
      status: "idle",
      startedAt: null,
      events: [],
      result: null,
      errorMessage: null,
      selectedSnapshot: "final",
    }),
  selectSnapshot: (snap) => set({ selectedSnapshot: snap }),
}));
