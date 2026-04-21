"""/api/solve WebSocket + /api/overrides/fill-from-snapshot REST.

The WebSocket streams CP-SAT's improving solutions as they're found. CP-SAT
is blocking, so the solve runs in a thread; its solution callback drops
events onto an asyncio.Queue via `loop.call_soon_threadsafe`.
"""

from __future__ import annotations

import asyncio
import threading
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect

from api.models.events import (
    AssignmentRow,
    FillFromSnapshotRequest,
    SolveDone,
    SolveEvent,
    SolveErrorMessage,
    SolveResultPayload,
)
from api.models.session import OverrideEntry
from api.sessions import (
    ServerSession,
    SESSION_COOKIE,
    assignments_to_rows,
    get_or_create_session_by_id,
    get_session,
    session_to_instance,
    session_to_solver_configs,
    solve_result_to_payload,
)
from scheduler.model import solve as scheduler_solve
from scheduler.ui_state import BuildError

router = APIRouter(tags=["solve"])


@router.websocket("/api/solve")
async def solve_ws(websocket: WebSocket) -> None:
    sid = websocket.cookies.get(SESSION_COOKIE)
    session = get_or_create_session_by_id(sid)
    await websocket.accept()

    # Wait for the opening "start" message.
    try:
        first = await websocket.receive_json()
    except WebSocketDisconnect:
        return
    if not isinstance(first, dict) or first.get("action") != "start":
        await websocket.send_json(SolveErrorMessage(
            message="First message must be {action: 'start'}").model_dump())
        await websocket.close()
        return
    snapshot = bool(first.get("snapshot_assignments", True))

    # Build the Instance up front so invalid config fails fast.
    try:
        inst = session_to_instance(session.state)
    except BuildError as e:
        await websocket.send_json(SolveErrorMessage(message=str(e)).model_dump())
        await websocket.close()
        return
    except ValueError as e:
        await websocket.send_json(SolveErrorMessage(message=str(e)).model_dump())
        await websocket.close()
        return

    weights, wl_weights, cfg = session_to_solver_configs(session.state)

    loop = asyncio.get_running_loop()
    event_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    stop_event = threading.Event()

    def _on_intermediate(ev: dict[str, Any]) -> None:
        loop.call_soon_threadsafe(event_queue.put_nowait, {"type": "event", **ev})

    intermediate_payloads: list[SolveEvent] = []

    def _run_solver() -> None:
        try:
            result = scheduler_solve(
                inst,
                time_limit_s=float(session.state.solver.time_limit),
                weights=weights,
                workload_weights=wl_weights,
                constraints=cfg,
                num_workers=session.state.solver.num_workers,
                feasibility_only=session.state.solver.feasibility_only,
                on_intermediate=_on_intermediate,
                snapshot_assignments=snapshot,
                stop_event=stop_event,
            )
            loop.call_soon_threadsafe(event_queue.put_nowait,
                                      {"type": "done", "_result": result})
        except Exception as e:  # pragma: no cover — solver rarely raises
            loop.call_soon_threadsafe(event_queue.put_nowait,
                                      {"type": "error", "message": str(e)})

    solver_thread = threading.Thread(target=_run_solver, daemon=True)
    solver_thread.start()

    async def _client_listener() -> None:
        """Watch for a 'stop' message from the client while solving."""
        try:
            while True:
                msg = await websocket.receive_json()
                if isinstance(msg, dict) and msg.get("action") == "stop":
                    stop_event.set()
                    return
        except WebSocketDisconnect:
            stop_event.set()

    listener = asyncio.create_task(_client_listener())

    try:
        while True:
            item = await event_queue.get()
            itype = item.get("type")
            if itype == "event":
                assignments_payload = None
                raw_snap = item.get("assignments")
                if raw_snap:
                    assignments_payload = _snapshot_to_rows(session.state, raw_snap)
                ev = SolveEvent(
                    wall_s=float(item.get("wall_s", 0.0)),
                    objective=item.get("objective"),
                    best_bound=item.get("best_bound"),
                    components={k: int(v) for k, v in
                                (item.get("components") or {}).items()},
                    assignments=assignments_payload,
                )
                intermediate_payloads.append(ev)
                await websocket.send_json(ev.model_dump(mode="json"))
            elif itype == "done":
                result = item["_result"]
                payload = solve_result_to_payload(session.state, result)
                payload.intermediate = intermediate_payloads
                session.last_solve = payload
                await websocket.send_json(
                    SolveDone(result=payload).model_dump(mode="json"))
                break
            elif itype == "error":
                await websocket.send_json(SolveErrorMessage(
                    message=str(item.get("message", "unknown error"))
                ).model_dump())
                break
    except WebSocketDisconnect:
        stop_event.set()
    finally:
        listener.cancel()
        try:
            await websocket.close()
        except Exception:  # already closed
            pass


def _snapshot_to_rows(state, snapshot: dict) -> list[AssignmentRow]:
    """Convert a callback's `assignments` snapshot into API rows.

    The callback uses the same tuple-keyed dict shape as SolveResult.
    """
    return assignments_to_rows(state, snapshot)


# --------------------------------------------------------------- overrides

overrides_router = APIRouter(prefix="/api/overrides", tags=["solve"])


@overrides_router.post("/fill-from-snapshot", response_model=list[OverrideEntry])
def fill_from_snapshot(
    req: FillFromSnapshotRequest,
    session: ServerSession = Depends(get_session),
) -> list[OverrideEntry]:
    """Copy assignments from a completed solve into the overrides list.

    `snapshot_id` is "final" for the last result, or the 0-based index
    (as a string) of an intermediate event from the same solve.
    """
    if session.last_solve is None:
        raise HTTPException(
            status_code=400,
            detail="No solve result in this session yet. Run /api/solve first.",
        )
    rows: list[AssignmentRow]
    if req.snapshot_id == "final":
        rows = session.last_solve.assignments
    else:
        try:
            idx = int(req.snapshot_id)
        except ValueError:
            raise HTTPException(status_code=400,
                                detail=f"Invalid snapshot_id '{req.snapshot_id}'")
        if idx < 0 or idx >= len(session.last_solve.intermediate):
            raise HTTPException(status_code=400,
                                detail=f"snapshot_id {idx} out of range")
        snap = session.last_solve.intermediate[idx].assignments
        if snap is None:
            raise HTTPException(
                status_code=400,
                detail="That intermediate event has no snapshot "
                       "(solve was run with snapshot_assignments=false).",
            )
        rows = snap

    overrides = [
        OverrideEntry(doctor=r.doctor, date=r.date, role=r.role)
        for r in rows
    ]
    session.state = session.state.model_copy(update={"overrides": overrides})
    return session.state.overrides
