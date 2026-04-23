"""/api/lab/scaling — solve-time vs problem size.

Runs CP-SAT on a grid of synthetic instances generated via
`scheduler.instance.make_synthetic`, records wall time + objective per
cell, and fits a power law T = a · N^b where N = n_doctors × n_days.

The fit is done in log-log space via ordinary least squares over stdlib
math — no numpy/scipy dependency. R² is reported so the UI can flag
fits that aren't well-described by a single power law (e.g. a CP-SAT
phase transition between instance sizes).

Output shape is deliberately different from the `/api/lab/run` batch
runner: scaling doesn't need fairness/coverage drill-downs because the
cells are synthetic and the point of the tab is a single curve. See
`docs/LAB_TAB_SPEC.md §5`.
"""

from __future__ import annotations

import math
import time
import uuid
from datetime import datetime, timezone

from api.models.lab import ScalingCell, ScalingFit, ScalingRequest, ScalingResponse
from scheduler.instance import make_synthetic
from scheduler.model import solve as cpsat_solve


def run_scaling(req: ScalingRequest) -> ScalingResponse:
    """Execute the scaling sweep.

    Each (size × seed) cell is run with a freshly generated synthetic
    instance. CP-SAT runs in single-worker mode by default so the
    reported times are deterministic under a fixed seed. Raising
    `num_workers` is allowed for realism measurements but non-deterministic.
    """
    cells: list[ScalingCell] = []
    for size in req.sizes:
        for seed in req.seeds:
            inst = make_synthetic(
                n_doctors=size.n_doctors,
                n_days=size.n_days,
                seed=seed,
                leave_rate=req.leave_rate,
            )
            t0 = time.perf_counter()
            try:
                result = cpsat_solve(
                    inst,
                    time_limit_s=float(req.time_limit_s),
                    num_workers=int(req.num_workers),
                    feasibility_only=bool(req.feasibility_only),
                    random_seed=int(seed),
                )
                status = result.status
                wall = float(result.wall_time_s)
                first = result.first_feasible_s
                obj = result.objective
                n_assign = sum(len(v) for v in result.assignments.values())
            except Exception as exc:  # noqa: BLE001
                status = f"ERROR:{type(exc).__name__}"
                wall = round(time.perf_counter() - t0, 3)
                first = None
                obj = None
                n_assign = 0
            cells.append(ScalingCell(
                n_doctors=size.n_doctors,
                n_days=size.n_days,
                seed=seed,
                status=status,
                wall_time_s=round(wall, 3),
                first_feasible_s=first,
                objective=obj,
                n_assignments=n_assign,
                size=size.n_doctors * size.n_days,
            ))

    return ScalingResponse(
        batch_id=uuid.uuid4().hex[:12],
        created_at=datetime.now(timezone.utc),
        time_limit_s=req.time_limit_s,
        num_workers=req.num_workers,
        leave_rate=req.leave_rate,
        cells=cells,
        fit=_fit_power_law(cells),
    )


def _fit_power_law(cells: list[ScalingCell]) -> ScalingFit:
    """Fit T = a · N^b via linear regression on (log N, log T).

    Only cells that actually solved (OPTIMAL/FEASIBLE) and took > 0s
    contribute; ERROR and UNKNOWN cells are dropped because their timing
    signal is meaningless.
    """
    points: list[tuple[float, float]] = []
    for c in cells:
        if c.status not in ("OPTIMAL", "FEASIBLE"):
            continue
        if c.wall_time_s <= 0 or c.size <= 0:
            continue
        points.append((math.log(c.size), math.log(c.wall_time_s)))

    if len(points) < 2:
        return ScalingFit(n_points=len(points))

    # Degenerate case: every point has the same x (e.g., all n_doctors ×
    # n_days collapses to one value). OLS slope is undefined. Report n
    # only; UI falls back to the raw scatter.
    xs = [p[0] for p in points]
    if max(xs) - min(xs) < 1e-9:
        return ScalingFit(n_points=len(points))

    n = len(points)
    sx = sum(p[0] for p in points)
    sy = sum(p[1] for p in points)
    sxx = sum(p[0] * p[0] for p in points)
    sxy = sum(p[0] * p[1] for p in points)
    denom = n * sxx - sx * sx
    if denom == 0:
        return ScalingFit(n_points=n)
    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n

    # R² = 1 - SSres / SStot.
    y_mean = sy / n
    ss_tot = sum((p[1] - y_mean) ** 2 for p in points)
    ss_res = sum(
        (p[1] - (slope * p[0] + intercept)) ** 2 for p in points
    )
    r_squared = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 1.0

    return ScalingFit(
        exponent=round(slope, 4),
        coefficient=round(math.exp(intercept), 6),
        r_squared=round(r_squared, 4),
        n_points=n,
    )
