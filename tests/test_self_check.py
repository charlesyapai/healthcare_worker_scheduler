"""Validator-in-the-loop regression.

Every solve exposes a `self_check` field built from the same validator
that `/api/roster/validate` uses. For any scenario the solver returns
FEASIBLE or OPTIMAL on, the self-check must be all-green. A failing
self-check means the CP-SAT model and `api.validator` have diverged —
either the model is producing an infeasible roster, or the validator
disagrees with `docs/CONSTRAINTS.md`.

This test does the slow work (real solve over three scenarios), so it
runs behind `@pytest.mark.slow` and is opt-in via `-m slow`. The
fairness and model-unit tests cover the fast path.
"""

from __future__ import annotations

import pytest


SCENARIOS = ("radiology_small", "busy_month_with_leave", "nursing_ward")


@pytest.mark.parametrize("scenario_id", SCENARIOS)
def test_solver_self_check_is_green(client, scenario_id: str) -> None:
    r = client.post(f"/api/state/scenarios/{scenario_id}")
    assert r.status_code == 200, r.text
    # Cap the time budget so the full three-scenario sweep stays under a
    # minute even on CI. Every scenario in `configs/scenarios/` is tuned
    # to hit FEASIBLE in well under this budget.
    client.patch("/api/state", json={"solver": {"time_limit": 20, "num_workers": 4}})
    r = client.post("/api/solve/run", json={"snapshot_assignments": False})
    assert r.status_code == 200, r.text
    result = r.json()
    assert result["status"] in ("OPTIMAL", "FEASIBLE"), result["status"]
    sc = result.get("self_check")
    assert sc is not None, "self_check missing from solve result"
    assert sc["ok"], (
        f"{scenario_id}: solver self-check failed — "
        f"{sc['violation_count']} violation(s), rules={sc['rules_failed']}, "
        f"first={sc['violations'][0] if sc['violations'] else None}"
    )
    # Every validator-tracked rule should land in either the passed or
    # failed bucket; sanity-check the union.
    assert set(sc["rules_passed"]) | set(sc["rules_failed"]) >= {
        "H1", "H2", "H3", "H10",
    }


def test_self_check_flags_violations_when_solver_output_is_tampered(client) -> None:
    """If we take a solver's output and mangle it, the validator (which
    powers the self-check) should catch the break. Smokes the wiring: the
    same validator that `/api/roster/validate` uses builds the self-check,
    so a tampered roster caught by the SPA's live-validation is also
    caught by the self-check for batch runs.
    """
    r = client.post("/api/state/scenarios/radiology_small")
    assert r.status_code == 200
    client.patch("/api/state", json={"solver": {"time_limit": 20, "num_workers": 4}})
    r = client.post("/api/solve/run", json={"snapshot_assignments": False})
    assignments = r.json()["assignments"]
    # Drop every station assignment from day 0 → H1 violations everywhere.
    date0 = assignments[0]["date"]
    tampered = [
        a for a in assignments
        if not (a["date"] == date0 and a["role"].startswith("STATION_"))
    ]
    r = client.post("/api/roster/validate", json={"assignments": tampered})
    assert r.status_code == 200
    body = r.json()
    assert not body["ok"]
    assert "H1" in body["rules_failed"]
