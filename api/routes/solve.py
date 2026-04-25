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
from pydantic import BaseModel

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
    rows_to_assignments_dict,
    session_to_instance,
    session_to_solver_configs,
    solve_result_to_payload,
)
from scheduler.model import solve as scheduler_solve
from scheduler.ui_state import BuildError

router = APIRouter(tags=["solve"])


@router.websocket("/api/solve")
async def solve_ws(websocket: WebSocket) -> None:
    # WebSockets can't set arbitrary headers from JS; accept the session id
    # via query param first, fall back to cookie for browsers that still
    # send it, else mint a new one.
    sid = (
        websocket.query_params.get("session_id")
        or websocket.cookies.get(SESSION_COOKIE)
    )
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
    mode = str(first.get("mode") or "new")

    warm_start: dict[str, dict] | None = None
    if mode == "continue" and session.last_solve is not None:
        try:
            warm_start = rows_to_assignments_dict(
                session.state, session.last_solve.assignments
            )
        except Exception:
            warm_start = None

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
                warm_start=warm_start,
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

    # Heartbeat: emit a no-op every 8 s so long solves on proxied deployments
    # (HF Spaces, Cloudflare, etc.) don't trip idle-timeout WebSocket drops.
    # 8 s is well under typical proxy thresholds (15–60 s) without being
    # wasteful.
    HEARTBEAT_INTERVAL_S = 8.0

    # Send an initial heartbeat so the client sees server traffic within a
    # round-trip of the start command — reassures the app that the socket
    # really is live before the solver produces its first solution.
    try:
        await websocket.send_json({"type": "heartbeat"})
    except Exception:
        pass

    try:
        while True:
            try:
                item = await asyncio.wait_for(event_queue.get(), HEARTBEAT_INTERVAL_S)
            except asyncio.TimeoutError:
                try:
                    await websocket.send_json({"type": "heartbeat"})
                except Exception:
                    break
                continue
            itype = item.get("type")
            if itype == "event":
                try:
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
                except Exception as e:
                    # Don't let a bad callback event kill the whole solve.
                    import logging
                    logging.getLogger("api.solve").exception(
                        "Failed to process solver event", extra={"err": str(e)}
                    )
            elif itype == "done":
                try:
                    result = item["_result"]
                    payload = solve_result_to_payload(session.state, result)
                    payload.intermediate = intermediate_payloads
                    session.last_solve = payload
                    await websocket.send_json(
                        SolveDone(result=payload).model_dump(mode="json"))
                except Exception as e:
                    try:
                        await websocket.send_json(SolveErrorMessage(
                            message=f"Failed to finalise solve: {e}"
                        ).model_dump())
                    except Exception:
                        pass
                break
            elif itype == "error":
                await websocket.send_json(SolveErrorMessage(
                    message=str(item.get("message", "unknown error"))
                ).model_dump())
                break
    except WebSocketDisconnect:
        stop_event.set()
    except Exception as e:
        # Anything else that bubbles up becomes a proper error message to
        # the client, not an abrupt 1006 close.
        import logging
        logging.getLogger("api.solve").exception("Solve handler crashed")
        try:
            await websocket.send_json(SolveErrorMessage(
                message=f"Server error during solve: {type(e).__name__}: {e}"
            ).model_dump())
        except Exception:
            pass
    finally:
        stop_event.set()
        listener.cancel()
        try:
            await websocket.close()
        except Exception:  # already closed
            pass


def _snapshot_to_rows(state, snapshot: dict) -> list[AssignmentRow]:
    """Convert a callback's `assignments` snapshot into API rows.

    Phase B: the snapshot from `_IntermediateLogger` flattens per-OnCallType
    var maps into keys of the form `oncall_by_type::<type_key>`. Re-nest
    those into the canonical `oncall_by_type` dict before handing off.
    """
    flat = snapshot or {}
    canonical: dict = {"stations": flat.get("stations") or {}}
    obt: dict[str, dict] = {}
    for key, vmap in flat.items():
        if key.startswith("oncall_by_type::"):
            type_key = key[len("oncall_by_type::"):]
            obt[type_key] = vmap
    if obt:
        canonical["oncall_by_type"] = obt
    return assignments_to_rows(state, canonical)


# --------------------------------------------------------------- REST fallback


class RestSolveRequest(BaseModel):
    snapshot_assignments: bool = False
    mode: str = "new"  # "new" or "continue"


@router.post("/api/solve/run", response_model=SolveResultPayload)
def solve_sync(
    req: RestSolveRequest = RestSolveRequest(),
    session: ServerSession = Depends(get_session),
) -> SolveResultPayload:
    """Blocking REST solve. Used as a fallback when the /api/solve WebSocket
    can't stay open through a proxy (HF Spaces sometimes drops WS mid-solve
    with code 1006). No intermediate events — just the final result.

    FastAPI runs sync routes on a thread pool, so the CP-SAT work here
    doesn't block other requests."""
    try:
        inst = session_to_instance(session.state)
    except BuildError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    weights, wl_weights, cfg = session_to_solver_configs(session.state)
    warm_start: dict[str, dict] | None = None
    if req.mode == "continue" and session.last_solve is not None:
        try:
            warm_start = rows_to_assignments_dict(
                session.state, session.last_solve.assignments
            )
        except Exception:
            warm_start = None
    try:
        result = scheduler_solve(
            inst,
            time_limit_s=float(session.state.solver.time_limit),
            weights=weights,
            workload_weights=wl_weights,
            constraints=cfg,
            num_workers=session.state.solver.num_workers,
            feasibility_only=session.state.solver.feasibility_only,
            snapshot_assignments=req.snapshot_assignments,
            warm_start=warm_start,
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Solver error: {type(e).__name__}: {e}",
        )
    payload = solve_result_to_payload(session.state, result)
    session.last_solve = payload
    return payload


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
