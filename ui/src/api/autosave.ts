/**
 * Debounced auto-save hook. Schedules a PATCH against /api/state after
 * `delayMs` of no further edits, and coalesces multiple edits during that
 * window into a single request. The TanStack Query cache is updated
 * optimistically so the UI reflects the change immediately.
 *
 * The cleanup effect flushes pending edits on true unmount (empty deps)
 * via a ref — not on every render, which would otherwise fire extra
 * PATCHes every time any upstream hook recomputes its identity.
 */

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef } from "react";

import { queryKeys } from "@/api/client";
import { type SessionState, usePatchState } from "@/api/hooks";

interface AutoSave {
  schedule: (patch: Partial<SessionState>, delayMs?: number) => void;
  flush: () => void;
  pending: boolean;
}

export function useAutoSavePatch(): AutoSave {
  const qc = useQueryClient();
  const patch = usePatchState();
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pendingRef = useRef<Partial<SessionState>>({});
  const flushRef = useRef<() => void>(() => {});

  flushRef.current = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const payload = pendingRef.current;
    pendingRef.current = {};
    if (Object.keys(payload).length > 0) patch.mutate(payload);
  };

  const flush = useCallback(() => flushRef.current(), []);

  const schedule = useCallback(
    (p: Partial<SessionState>, delayMs = 500) => {
      qc.setQueryData(queryKeys.sessionState, (old: SessionState | undefined) =>
        old ? ({ ...old, ...p } as SessionState) : old,
      );
      pendingRef.current = { ...pendingRef.current, ...p };
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(() => flushRef.current(), delayMs);
    },
    [qc],
  );

  useEffect(
    () => () => {
      // True unmount only — flush any pending edits so they don't get lost.
      flushRef.current();
    },
    [],
  );

  return { schedule, flush, pending: patch.isPending };
}
