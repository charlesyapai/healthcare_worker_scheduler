/**
 * Global keyboard shortcuts. Vim-style `g <letter>` chord for navigation;
 * Ctrl/Cmd combos for save/solve.
 */

import { useEffect } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";

import { startSolve, stopSolve } from "@/api/solveWs";
import { useSolveStore } from "@/store/solve";

const NAV_MAP: Record<string, string> = {
  d: "/",
  s: "/setup",
  p: "/solve",
  o: "/roster",
  l: "/solve/lab/benchmark",
};

export function useGlobalShortcuts() {
  const navigate = useNavigate();

  useEffect(() => {
    let gPending = false;
    let gTimer: ReturnType<typeof setTimeout> | null = null;

    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      const isTyping =
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.tagName === "SELECT" ||
          target.isContentEditable);

      // Save YAML: Ctrl/Cmd+S
      if ((e.ctrlKey || e.metaKey) && e.key === "s") {
        e.preventDefault();
        const btn = document.querySelector<HTMLButtonElement>('button[aria-label="Save YAML"]');
        btn?.click();
        return;
      }

      // Ctrl/Cmd+Enter → Solve
      if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
        e.preventDefault();
        const status = useSolveStore.getState().status;
        if (status === "running") {
          stopSolve();
          toast("Sent stop signal");
        } else {
          startSolve({ snapshotAssignments: true });
        }
        return;
      }

      if (isTyping) return;

      // g-then-letter chord
      if (e.key === "g" && !e.ctrlKey && !e.metaKey && !e.altKey) {
        gPending = true;
        if (gTimer) clearTimeout(gTimer);
        gTimer = setTimeout(() => (gPending = false), 1200);
        return;
      }
      if (gPending && NAV_MAP[e.key]) {
        const to = NAV_MAP[e.key];
        gPending = false;
        if (gTimer) clearTimeout(gTimer);
        navigate(to);
      }
    };

    window.addEventListener("keydown", handler);
    return () => {
      window.removeEventListener("keydown", handler);
      if (gTimer) clearTimeout(gTimer);
    };
  }, [navigate]);
}
