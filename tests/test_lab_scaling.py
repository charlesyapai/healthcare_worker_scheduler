"""Scaling tab backend — `POST /api/lab/scaling/run`.

Checks that the synthetic-instance grid runs end-to-end, the response
shape matches the model, and the power-law fit reports sensible values.
The fit quality itself is not asserted (CP-SAT is not actually O(N^k)
for any fixed k — the exponent depends on instance structure and time
budget); we only check it's computed without error and falls in a
reasonable range when we have enough points.
"""

from __future__ import annotations

import math

from api.lab.scaling import _fit_power_law, run_scaling
from api.models.lab import ScalingCell, ScalingRequest, ScalingSize


# ------------------------------------------------------------- unit: fit


def _cell(size: int, wall: float, status: str = "OPTIMAL") -> ScalingCell:
    # Map `size` back to (n_doctors, n_days) — doesn't matter for the fit
    # math, only the product does.
    return ScalingCell(
        n_doctors=max(4, size // 7),
        n_days=7,
        seed=0,
        status=status,
        wall_time_s=wall,
        first_feasible_s=None,
        objective=None,
        n_assignments=0,
        size=size,
    )


def test_fit_rejects_single_point() -> None:
    fit = _fit_power_law([_cell(70, 1.0)])
    assert fit.exponent is None
    assert fit.coefficient is None
    assert fit.n_points == 1


def test_fit_rejects_error_cells() -> None:
    # Three points, all ERROR → nothing to fit against.
    cells = [
        _cell(70, 1.0, "ERROR:RuntimeError"),
        _cell(140, 2.0, "ERROR:RuntimeError"),
        _cell(210, 3.0, "ERROR:RuntimeError"),
    ]
    fit = _fit_power_law(cells)
    assert fit.exponent is None
    assert fit.n_points == 0


def test_fit_recovers_known_power_law() -> None:
    """Generate synthetic cells from T = 2.0 · N^1.5 and recover them."""
    a_true, b_true = 2.0, 1.5
    sizes = [70, 140, 210, 280, 350, 420]
    cells = [_cell(s, a_true * (s ** b_true)) for s in sizes]
    fit = _fit_power_law(cells)
    assert fit.exponent is not None
    assert fit.coefficient is not None
    assert math.isclose(fit.exponent, b_true, abs_tol=1e-3)
    assert math.isclose(fit.coefficient, a_true, rel_tol=1e-3)
    assert fit.r_squared is not None
    assert fit.r_squared > 0.999


def test_fit_degenerate_constant_x() -> None:
    # All cells have the same size — OLS slope is undefined.
    cells = [_cell(70, 0.5), _cell(70, 1.0), _cell(70, 1.5)]
    fit = _fit_power_law(cells)
    assert fit.exponent is None
    assert fit.n_points == 3


# ------------------------------------------------------------- endpoint


def test_scaling_endpoint_small_grid(client) -> None:
    """Tiny grid so the test stays under a few seconds. Two sizes × two
    seeds → 4 cells. Asserts the response shape, not the fit values."""
    req = {
        "sizes": [
            {"n_doctors": 10, "n_days": 7},
            {"n_doctors": 14, "n_days": 7},
        ],
        "seeds": [0, 1],
        "time_limit_s": 5,
        "num_workers": 1,
        "leave_rate": 0.0,
    }
    r = client.post("/api/lab/scaling/run", json=req)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "batch_id" in body
    assert body["time_limit_s"] == 5
    assert body["num_workers"] == 1
    assert len(body["cells"]) == 4
    sizes_seen = {(c["n_doctors"], c["n_days"]) for c in body["cells"]}
    assert sizes_seen == {(10, 7), (14, 7)}
    for c in body["cells"]:
        assert "wall_time_s" in c
        assert c["size"] == c["n_doctors"] * c["n_days"]
        assert c["status"] in ("OPTIMAL", "FEASIBLE", "INFEASIBLE", "UNKNOWN") \
            or c["status"].startswith("ERROR")
    # Fit may or may not have converged depending on the solver's choices;
    # either way the shape is well-formed.
    fit = body["fit"]
    assert "exponent" in fit and "coefficient" in fit
    assert "r_squared" in fit and "n_points" in fit


def test_scaling_rejects_empty_sizes(client) -> None:
    r = client.post("/api/lab/scaling/run", json={
        "sizes": [],
        "seeds": [0],
        "time_limit_s": 2,
    })
    assert r.status_code == 422


def test_scaling_integration_via_runner() -> None:
    """Directly invoke the runner so we can assert on the typed object.
    One (10, 7) × 1 seed cell — plenty for shape checks."""
    req = ScalingRequest(
        sizes=[ScalingSize(n_doctors=10, n_days=7)],
        seeds=[0],
        time_limit_s=5,
        num_workers=1,
        leave_rate=0.0,
    )
    resp = run_scaling(req)
    assert len(resp.cells) == 1
    cell = resp.cells[0]
    assert cell.n_doctors == 10
    assert cell.n_days == 7
    assert cell.size == 70
    assert cell.wall_time_s >= 0
