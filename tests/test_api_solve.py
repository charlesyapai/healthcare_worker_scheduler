"""WebSocket-layer tests for /api/solve and /api/overrides/fill-from-snapshot."""

from __future__ import annotations


def _seed_small(client) -> None:
    """Seed a 20-doctor default roster, then shrink it for fast solves."""
    client.post("/api/state/seed")
    client.patch("/api/state", json={
        "horizon": {"n_days": 7},
        "solver": {"time_limit": 10, "num_workers": 4},
    })


def test_ws_solve_completes_with_assignments(client) -> None:
    _seed_small(client)
    client.patch("/api/state",
                 json={"solver": {"feasibility_only": True, "time_limit": 10}})
    with client.websocket_connect(f"/api/solve?session_id={client.session_id}") as ws:
        ws.send_json({"action": "start", "snapshot_assignments": False})
        last = None
        while True:
            msg = ws.receive_json()
            if msg["type"] == "heartbeat":
                continue
            if msg["type"] == "done":
                last = msg
                break
            if msg["type"] == "error":
                raise AssertionError(f"solver error: {msg['message']}")
        assert last is not None
        assert last["result"]["status"] in ("OPTIMAL", "FEASIBLE")
        assert len(last["result"]["assignments"]) > 0
        first_row = last["result"]["assignments"][0]
        assert {"doctor", "date", "role"}.issubset(first_row)


def test_ws_solve_streams_events(client) -> None:
    """With the objective enabled, the solver should surface at least one event."""
    _seed_small(client)
    client.patch("/api/state",
                 json={"solver": {"feasibility_only": False, "time_limit": 10}})
    with client.websocket_connect(f"/api/solve?session_id={client.session_id}") as ws:
        ws.send_json({"action": "start", "snapshot_assignments": True})
        events = []
        result = None
        while True:
            msg = ws.receive_json()
            if msg["type"] == "heartbeat":
                continue
            if msg["type"] == "event":
                events.append(msg)
                # Snapshots should be list[AssignmentRow].
                assert msg.get("assignments") is not None
                assert len(msg["assignments"]) > 0
            elif msg["type"] == "done":
                result = msg["result"]
                break
            elif msg["type"] == "error":
                raise AssertionError(msg["message"])
        assert len(events) >= 1
        assert result is not None
        assert result["status"] in ("OPTIMAL", "FEASIBLE")
        # `intermediate` in the final result mirrors the streamed events.
        assert len(result["intermediate"]) == len(events)


def test_ws_stop_message_early_exits(client) -> None:
    _seed_small(client)
    # Long time limit so the solver is still running when we ask it to stop.
    client.patch("/api/state",
                 json={"solver": {"feasibility_only": False, "time_limit": 120}})
    with client.websocket_connect(f"/api/solve?session_id={client.session_id}") as ws:
        ws.send_json({"action": "start", "snapshot_assignments": True})
        # Wait for the first improving solution (skip heartbeats), then ask
        # CP-SAT to stop.
        while True:
            first = ws.receive_json()
            if first["type"] == "heartbeat":
                continue
            assert first["type"] == "event"
            break
        ws.send_json({"action": "stop"})
        # Drain until 'done'. Solver should exit quickly (well under the 120 s
        # time limit) since we signalled stop.
        while True:
            msg = ws.receive_json()
            if msg["type"] == "heartbeat":
                continue
            if msg["type"] == "done":
                assert msg["result"]["wall_time_s"] < 60
                assert msg["result"]["status"] in ("OPTIMAL", "FEASIBLE")
                break
            if msg["type"] == "error":
                raise AssertionError(msg["message"])


def test_fill_from_snapshot_populates_overrides(client) -> None:
    _seed_small(client)
    client.patch("/api/state",
                 json={"solver": {"feasibility_only": True, "time_limit": 10}})
    with client.websocket_connect(f"/api/solve?session_id={client.session_id}") as ws:
        ws.send_json({"action": "start", "snapshot_assignments": False})
        while True:
            msg = ws.receive_json()
            if msg["type"] == "heartbeat":
                continue
            if msg["type"] == "done":
                n_assignments = len(msg["result"]["assignments"])
                break

    r = client.post("/api/overrides/fill-from-snapshot",
                    json={"snapshot_id": "final"})
    assert r.status_code == 200, r.text
    overrides = r.json()
    assert len(overrides) == n_assignments
    assert {"doctor", "date", "role"}.issubset(overrides[0])


def test_fill_from_snapshot_without_solve_400s(client) -> None:
    client.post("/api/state/seed")
    r = client.post("/api/overrides/fill-from-snapshot",
                    json={"snapshot_id": "final"})
    assert r.status_code == 400
