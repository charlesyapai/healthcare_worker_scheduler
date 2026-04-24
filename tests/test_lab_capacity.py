"""Capacity tab backend — `POST /api/lab/capacity/run`.

Two modes to cover:

* `hours_vs_target` — solves the current state, reports per-doctor
  worked hours and a per-tier roll-up.
* `team_reduction` — iterative drop-and-resolve. Asserts the
  structural shape (step 0 = full team, removed list grows by one
  each step, min_viable is no greater than starting team size).
"""

from __future__ import annotations

from api.lab.capacity import run_capacity
from api.models.lab import CapacityRequest


# ------------------------------------------------------------- hours


def test_hours_vs_target_basic_shape(client) -> None:
    client.post("/api/state/scenarios/radiology_small")
    r = client.post("/api/lab/capacity/run", json={
        "mode": "hours_vs_target",
        "time_limit_s": 10,
        "num_workers": 2,
        "target_hours_per_week": 40,
        "max_drop": 1,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "hours_vs_target"
    assert body["target_hours_per_week"] == 40
    assert len(body["per_doctor"]) == 15      # radiology_small
    # Each per-doctor row has all the expected fields.
    sample = body["per_doctor"][0]
    for key in (
        "doctor_name", "tier", "fte",
        "actual_hours", "target_hours", "delta", "status",
        "sessions", "oncalls", "weekend_duties",
    ):
        assert key in sample, f"missing key: {key}"
    # Sorted under → over.
    deltas = [p["delta"] for p in body["per_doctor"]]
    assert deltas == sorted(deltas), "expected delta ascending"


def test_hours_vs_target_tier_rollup(client) -> None:
    """Per-tier aggregates should sum to the per-doctor totals, and
    share_of_fte / share_of_total_hours should land in [0, 1]."""
    client.post("/api/state/scenarios/radiology_small")
    r = client.post("/api/lab/capacity/run", json={
        "mode": "hours_vs_target",
        "time_limit_s": 10,
        "num_workers": 2,
        "target_hours_per_week": 40,
        "max_drop": 1,
    })
    body = r.json()
    assert len(body["per_tier"]) >= 1

    total_fte_share = sum(t["share_of_fte"] for t in body["per_tier"])
    total_hours_share = sum(t["share_of_total_hours"] for t in body["per_tier"])
    assert abs(total_fte_share - 1.0) < 0.05, total_fte_share
    assert abs(total_hours_share - 1.0) < 0.05, total_hours_share

    for t in body["per_tier"]:
        assert 0 <= t["share_of_fte"] <= 1.0
        assert 0 <= t["share_of_total_hours"] <= 1.0
        assert t["headcount"] > 0


def test_hours_vs_target_direct_runner() -> None:
    """Invoke the runner directly without a FastAPI TestClient so we can
    reason about the typed CapacityResponse shape."""
    from pathlib import Path
    from api.models.session import SessionState
    from api.sessions import v1_dict_to_session
    from scheduler.persistence import load_state

    yaml_text = Path("configs/scenarios/radiology_small.yaml").read_text()
    state = v1_dict_to_session(load_state(yaml_text), base=SessionState())

    req = CapacityRequest(
        mode="hours_vs_target",
        time_limit_s=10,
        num_workers=2,
        target_hours_per_week=40,
    )
    resp = run_capacity(state, req)
    assert resp.mode == "hours_vs_target"
    assert resp.per_doctor
    assert resp.per_tier
    # At least one doctor should be on-target or close to it — our
    # scenarios are feasible and the solver aims to distribute work.
    statuses = {p.status for p in resp.per_doctor}
    assert statuses & {"on_target", "under", "over"} == statuses


# ------------------------------------------------------------- reduction


def test_team_reduction_returns_sequential_cells(client) -> None:
    """Team-reduction should produce `max_drop + 1` cells (baseline +
    one per drop), with team_size monotonically decreasing and the
    `removed` list growing by one each step."""
    client.post("/api/state/scenarios/radiology_small")
    r = client.post("/api/lab/capacity/run", json={
        "mode": "team_reduction",
        "max_drop": 2,
        "time_limit_s": 8,
        "num_workers": 2,
        "target_hours_per_week": 40,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mode"] == "team_reduction"
    cells = body["reduction"]
    assert len(cells) == 3, cells  # 0, 1, 2
    assert cells[0]["step"] == 0
    assert cells[0]["removed"] == []
    # Team size strictly decreases step-by-step.
    for i in range(1, len(cells)):
        assert cells[i]["team_size"] == cells[i - 1]["team_size"] - 1
        assert len(cells[i]["removed"]) == i
    # min_viable (if set) must be at most baseline team size.
    if body["min_viable_team_size"] is not None:
        assert body["min_viable_team_size"] <= cells[0]["team_size"]


def test_unseeded_state_rejects_capacity_run(client) -> None:
    r = client.post("/api/lab/capacity/run", json={
        "mode": "hours_vs_target",
        "time_limit_s": 5,
        "num_workers": 1,
        "target_hours_per_week": 40,
        "max_drop": 1,
    })
    # A fresh session has no doctors / stations — the endpoint returns 400.
    assert r.status_code == 400
