/**
 * Draft-roster store. Holds a user-editable copy of the currently-selected
 * solve snapshot so they can make manual changes ("new version") and see
 * which hard constraints the edits break without re-running the solver.
 */

import { create } from "zustand";

import type { AssignmentRow } from "@/store/solve";

export interface Violation {
  rule: string;
  severity: string;
  location: string;
  message: string;
}

export interface ValidationResult {
  ok: boolean;
  violation_count: number;
  violations: Violation[];
  rules_passed: string[];
  rules_failed: string[];
}

interface DraftState {
  active: boolean;
  assignments: AssignmentRow[];
  /** Snapshot of the assignments at the moment edit mode was turned on,
   *  so we can report a diff count and reset cleanly. */
  base: AssignmentRow[];
  validation: ValidationResult | null;
  validating: boolean;

  enable: (initial: AssignmentRow[]) => void;
  disable: () => void;
  replaceCell: (doctor: string, date: string, newRows: AssignmentRow[]) => void;
  setValidation: (v: ValidationResult | null) => void;
  setValidating: (v: boolean) => void;
  resetDraft: () => void;
}

export const useDraftStore = create<DraftState>((set, get) => ({
  active: false,
  assignments: [],
  base: [],
  validation: null,
  validating: false,

  enable: (initial) =>
    set({
      active: true,
      assignments: [...initial],
      base: [...initial],
      validation: null,
      validating: false,
    }),
  disable: () =>
    set({ active: false, assignments: [], base: [], validation: null, validating: false }),
  replaceCell: (doctor, date, newRows) => {
    const kept = get().assignments.filter(
      (a) => !(a.doctor === doctor && a.date === date),
    );
    set({ assignments: [...kept, ...newRows] });
  },
  setValidation: (v) => set({ validation: v }),
  setValidating: (v) => set({ validating: v }),
  resetDraft: () => {
    const base = get().base;
    set({ assignments: [...base], validation: null });
  },
}));

export function draftChangeCount(): number {
  const { assignments, base } = useDraftStore.getState();
  if (!useDraftStore.getState().active) return 0;
  const serialize = (r: AssignmentRow) => `${r.doctor}|${r.date}|${r.role}`;
  const before = new Set(base.map(serialize));
  const after = new Set(assignments.map(serialize));
  let count = 0;
  for (const k of after) if (!before.has(k)) count++;
  for (const k of before) if (!after.has(k)) count++;
  return count;
}
