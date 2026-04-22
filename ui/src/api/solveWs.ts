/**
 * Thin wrapper around the /api/solve WebSocket. Drives the solve store.
 * Session id rides along as a ?session_id= query param because WebSockets
 * can't set custom headers from JS.
 */

import { toast } from "sonner";

import { wsUrl } from "@/api/client";
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

export function startSolve(options: { snapshotAssignments: boolean }) {
  if (current) return;
  const store = useSolveStore.getState();
  store.begin();

  const url = wsUrl("/api/solve");
  const ws = new WebSocket(url);
  current = ws;

  // Remember the last server-sent error so a follow-up onclose doesn't
  // clobber it with a generic "connection closed" message.
  let lastServerError: string | null = null;

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
      lastServerError = msg.message ?? "solver error";
      s.fail(lastServerError);
      toast.error(`Solver: ${lastServerError}`);
      cleanup();
    }
    // heartbeat: ignore, connection stays open.
  };

  ws.onerror = () => {
    // Browsers don't expose error detail here for security reasons; the
    // specific reason usually arrives via the close event's code/reason.
    console.warn("[solve] websocket onerror", { url });
  };

  ws.onclose = (ev) => {
    const s = useSolveStore.getState();
    // If the server already told us why, leave that message alone.
    if (s.status === "error") {
      cleanup();
      return;
    }
    if (s.status === "running") {
      const detail = ev.reason
        ? `code ${ev.code}: ${ev.reason}`
        : `code ${ev.code}${ev.code === 1006 ? " (handshake/network failure — WebSocket proxy may be blocked)" : ""}`;
      const msg = lastServerError ?? `Connection closed before solve completed (${detail}).`;
      s.fail(msg);
      toast.error(msg);
      console.warn("[solve] websocket closed unexpectedly", {
        code: ev.code,
        reason: ev.reason,
        wasClean: ev.wasClean,
        url,
      });
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
