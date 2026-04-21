/**
 * Thin wrapper around the /api/solve WebSocket. Drives the solve store.
 * Same-origin cookies are automatically included by the browser.
 */

import { wsUrl } from "@/api/client";
import {
  type SolveEvent,
  type SolveResultPayload,
  useSolveStore,
} from "@/store/solve";

type Incoming =
  | (SolveEvent & { type: "event" })
  | { type: "done"; result: SolveResultPayload }
  | { type: "error"; message: string };

let current: WebSocket | null = null;

export function startSolve(options: { snapshotAssignments: boolean }) {
  if (current) return;
  const store = useSolveStore.getState();
  store.begin();

  const ws = new WebSocket(wsUrl("/api/solve"));
  current = ws;

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
      s.finish(msg.result);
      cleanup();
    } else if (msg.type === "error") {
      s.fail(msg.message ?? "solver error");
      cleanup();
    }
  };

  ws.onerror = () => {
    const s = useSolveStore.getState();
    if (s.status === "running") s.fail("WebSocket error");
    cleanup();
  };

  ws.onclose = () => {
    const s = useSolveStore.getState();
    if (s.status === "running") {
      s.fail("Connection closed before solve completed.");
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

function cleanup() {
  current = null;
}
