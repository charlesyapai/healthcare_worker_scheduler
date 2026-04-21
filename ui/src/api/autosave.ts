/**
 * Debounced auto-save hook. Schedules a PATCH against /api/state after
 * `delayMs` of no further edits, and coalesces multiple edits during that
 * window into a single request. The TanStack Query cache is updated
 * optimistically so the UI reflects the change immediately.
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

  const flush = useCallback(() => {
    if (timerRef.current) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    const payload = pendingRef.current;
    pendingRef.current = {};
    if (Object.keys(payload).length > 0) patch.mutate(payload);
  }, [patch]);

  const schedule = useCallback(
    (p: Partial<SessionState>, delayMs = 500) => {
      qc.setQueryData(queryKeys.sessionState, (old: SessionState | undefined) =>
        old ? ({ ...old, ...p } as SessionState) : old,
      );
      pendingRef.current = { ...pendingRef.current, ...p };
      if (timerRef.current) clearTimeout(timerRef.current);
      timerRef.current = setTimeout(flush, delayMs);
    },
    [qc, flush],
  );

  useEffect(
    () => () => {
      // Flush on unmount so a quick tab-switch doesn't lose edits.
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        const payload = pendingRef.current;
        pendingRef.current = {};
        if (Object.keys(payload).length > 0) patch.mutate(payload);
      }
    },
    [patch],
  );

  return { schedule, flush, pending: patch.isPending };
}
