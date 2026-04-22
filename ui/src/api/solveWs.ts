/**
 * Solve driver. Primary path is a WebSocket for live progress updates;
 * falls back to a blocking POST /api/solve/run if the WebSocket drops
 * before completion. Session id rides along as a ?session_id= query
 * param on the WS because JS can't set custom WebSocket headers; the
 * REST fallback uses the normal X-Session-Id header path.
 */

import { toast } from "sonner";

import { ApiError, apiFetch, wsUrl } from "@/api/client";
import {
  type SolveEvent,
  type SolveResultPayload,
  useSolveStore,
} from "@/store/solve";

type Incoming =
  | (SolveEvent & { type: "event" })
  | { type: "done"; result: SolveResultPayload }
  | { type: "error"; message: string }
  | { type: "heartbeat" };

let current: WebSocket | null = null;
let pendingRestFallback: Promise<void> | null = null;

export function startSolve(options: { snapshotAssignments: boolean }) {
  if (current) return;
  const store = useSolveStore.getState();
  store.begin();

  const url = wsUrl("/api/solve");
  let ws: WebSocket;
  try {
    ws = new WebSocket(url);
  } catch (e) {
    console.warn("[solve] failed to open WS", e);
    void runRestFallback(options);
    return;
  }
  current = ws;

  let lastServerError: string | null = null;
  let everGotTraffic = false;

  ws.onopen = () => {
    ws.send(
      JSON.stringify({
        action: "start",
        snapshot_assignments: options.snapshotAssignments,
      }),
    );
  };

  ws.onmessage = (ev) => {
    everGotTraffic = true;
    let msg: Incoming;
    try {
      msg = JSON.parse(ev.data) as Incoming;
    } catch {
      return;
    }
    const s = useSolveStore.getState();
    if (msg.type === "event") {
      s.pushEvent(msg);
    } else if (msg.type === "done") {
      s.finish(msg.result);
      cleanup();
    } else if (msg.type === "error") {
      lastServerError = msg.message ?? "solver error";
      s.fail(lastServerError);
      toast.error(`Solver: ${lastServerError}`);
      cleanup();
    }
    // heartbeat: ignore, connection stays open.
  };

  ws.onerror = () => {
    console.warn("[solve] websocket onerror", { url });
  };

  ws.onclose = (ev) => {
    const s = useSolveStore.getState();
    if (s.status === "done" || s.status === "error") {
      cleanup();
      return;
    }
    if (s.status === "running") {
      console.warn("[solve] websocket closed unexpectedly", {
        code: ev.code,
        reason: ev.reason,
        wasClean: ev.wasClean,
        everGotTraffic,
        url,
      });
      // Fall back to the blocking REST endpoint. If the solver already
      // sent an explicit error, respect it; otherwise show a gentler
      // "retrying via REST" notice and attempt the fallback.
      if (lastServerError) {
        cleanup();
        return;
      }
      toast.message("WebSocket dropped — retrying via blocking REST call…");
      void runRestFallback(options);
    }
    cleanup();
  };
}

export function stopSolve() {
  if (!current || current.readyState !== WebSocket.OPEN) return;
  try {
    current.send(JSON.stringify({ action: "stop" }));
  } catch {
    /* ignore */
  }
}

async function runRestFallback(options: { snapshotAssignments: boolean }) {
  if (pendingRestFallback) return;
  const s = useSolveStore.getState();
  pendingRestFallback = (async () => {
    try {
      const result = await apiFetch<SolveResultPayload>("/api/solve/run", {
        method: "POST",
        body: { snapshot_assignments: options.snapshotAssignments },
      });
      useSolveStore.getState().finish(result);
      toast.success(`Solved (${result.status.toLowerCase()}) via REST fallback`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "REST fallback failed";
      useSolveStore.getState().fail(msg);
      toast.error(`Solve failed: ${msg}`);
    } finally {
      pendingRestFallback = null;
    }
  })();
  // ensure UI knows we're running
  if (s.status !== "running") {
    useSolveStore.getState().begin();
  }
}

function cleanup() {
  current = null;
}
