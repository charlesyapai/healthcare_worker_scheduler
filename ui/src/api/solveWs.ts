/**
 * Solve driver. Prefers the /api/solve WebSocket (live events) but falls
 * back to POST /api/solve/run if the proxy drops the connection. After
 * two consecutive WS failures the driver remembers that and skips the
 * WS entirely until the next tab session, so unreliable networks don't
 * repeatedly pay the fallback penalty.
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

const WS_FAIL_KEY = "hws-ws-fails";
const WS_FAIL_CAP = 2; // after N consecutive failures, stop trying WS

let current: WebSocket | null = null;
let pendingRestFallback: Promise<void> | null = null;

function getWsFailCount(): number {
  try {
    return Number(sessionStorage.getItem(WS_FAIL_KEY) ?? "0") || 0;
  } catch {
    return 0;
  }
}

function bumpWsFails(): void {
  try {
    sessionStorage.setItem(WS_FAIL_KEY, String(getWsFailCount() + 1));
  } catch {
    /* ignore */
  }
}

function resetWsFails(): void {
  try {
    sessionStorage.removeItem(WS_FAIL_KEY);
  } catch {
    /* ignore */
  }
}

export function startSolve(options: { snapshotAssignments: boolean }) {
  if (current || pendingRestFallback) return;

  // Skip WS if it's repeatedly failed this tab-session.
  if (getWsFailCount() >= WS_FAIL_CAP) {
    useSolveStore.getState().begin();
    void runRestFallback(options, { silent: true });
    return;
  }

  const store = useSolveStore.getState();
  store.begin();

  const url = wsUrl("/api/solve");
  let ws: WebSocket;
  try {
    ws = new WebSocket(url);
  } catch (e) {
    console.warn("[solve] failed to open WS", e);
    bumpWsFails();
    void runRestFallback(options, { silent: true });
    return;
  }
  current = ws;

  let lastServerError: string | null = null;
  let receivedDone = false;

  ws.onopen = () => {
    ws.send(
      JSON.stringify({
        action: "start",
        snapshot_assignments: options.snapshotAssignments,
      }),
    );
  };

  ws.onmessage = (ev) => {
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
      receivedDone = true;
      resetWsFails(); // WS worked end-to-end — forgive earlier failures
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
        receivedDone,
      });
      if (lastServerError) {
        cleanup();
        return;
      }
      bumpWsFails();
      // Silent fallback — the user doesn't need to know how their solve was
      // carried out, just that it worked. The console log above is enough
      // for diagnosis.
      void runRestFallback(options, { silent: true });
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

async function runRestFallback(
  options: { snapshotAssignments: boolean },
  { silent = false }: { silent?: boolean } = {},
) {
  if (pendingRestFallback) return;
  const store = useSolveStore.getState();
  pendingRestFallback = (async () => {
    try {
      if (store.status !== "running") store.begin();
      const result = await apiFetch<SolveResultPayload>("/api/solve/run", {
        method: "POST",
        body: { snapshot_assignments: options.snapshotAssignments },
      });
      useSolveStore.getState().finish(result);
      if (!silent) toast.success(`Solved (${result.status.toLowerCase()})`);
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : "Solve failed";
      useSolveStore.getState().fail(msg);
      toast.error(`Solve failed: ${msg}`);
    } finally {
      pendingRestFallback = null;
    }
  })();
}

function cleanup() {
  current = null;
}
