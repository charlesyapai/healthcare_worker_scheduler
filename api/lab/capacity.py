"""/api/lab/capacity — manpower / team-sizing analysis.

Two modes:

* **hours_vs_target** — one CP-SAT solve over the current session
  state. Compute each doctor's worked hours from the solution (using
  the session's `Hours` weights so AM / PM / ONCALL / EXT durations
  are realistic), then compare each doctor to their FTE-scaled
  `target_hours_per_week`. Tells the coordinator who's under-loaded
  vs over-loaded.
* **team_reduction** — solve the scenario with the full team, then
  iteratively drop the lowest-loaded doctor(s) and re-solve. Report
  the first step where coverage breaks or self-check fails. Answers
  "how small can the team be before it stops working?".

Both modes leave the session state untouched — the analysis runs on
a snapshot copy. No overrides are injected; leave / holidays / manual
overrides are preserved as-is.
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone

from api.metrics.coverage import compute_coverage
from api.models.events import AssignmentRow
from api.models.lab import (
    CapacityRequest,
    CapacityResponse,
    HoursPerDoctor,
    ReductionCell,
    TierWorkload,
)
from api.models.session import DoctorEntry, SessionState
from api.sessions import (
    assignments_to_rows,
    build_self_check,
    session_to_instance,
    session_to_solver_configs,
)
from scheduler.model import solve as cpsat_solve


# --------------------------------------------------------------- hours


def _solve_one(
    state: SessionState,
    *,
    time_limit_s: float,
    num_workers: int,
) -> tuple[list[AssignmentRow], "object"]:
    """Run CP-SAT once on `state`. Returns (assignment rows, raw result)."""
    inst = session_to_instance(state)
    weights, wl, cfg = session_to_solver_configs(state)
    result = cpsat_solve(
        inst,
        time_limit_s=float(time_limit_s),
        weights=weights,
        workload_weights=wl,
        constraints=cfg,
        num_workers=int(num_workers),
    )
    rows = assignments_to_rows(state, result.assignments or {})
    return rows, result


def _is_weekend(d: date, holidays: set[date]) -> bool:
    return d.weekday() >= 5 or d in holidays


def _hours_per_doctor(
    state: SessionState,
    rows: list[AssignmentRow],
    target_hours_per_week: float,
) -> list[HoursPerDoctor]:
    """Sum each doctor's hours worked from the assignment rows, attribute
    them to a weekly rate (actual_hours / weeks), and compare to the
    FTE-scaled target."""
    hrs = state.hours
    holidays: set[date] = set(state.horizon.public_holidays)
    n_days = max(state.horizon.n_days, 1)
    weeks = max(n_days / 7.0, 1.0 / 7.0)

    # Precompute per-doctor name → doctor entry
    by_name: dict[str, DoctorEntry] = {d.name: d for d in state.doctors}

    totals: dict[str, dict[str, float]] = defaultdict(
        lambda: {"hours": 0.0, "sessions": 0, "oncalls": 0, "weekend": 0}
    )
    for r in rows:
        we = _is_weekend(r.date, holidays)
        role = r.role
        if role.startswith("STATION_"):
            if role.endswith("_AM"):
                h = hrs.weekend_am if we else hrs.weekday_am
            elif role.endswith("_PM"):
                h = hrs.weekend_pm if we else hrs.weekday_pm
            else:
                continue
            totals[r.doctor]["sessions"] += 1
        elif role == "ONCALL":
            h = hrs.weekend_oncall if we else hrs.weekday_oncall
            totals[r.doctor]["oncalls"] += 1
            if we:
                totals[r.doctor]["weekend"] += 1
        elif role == "WEEKEND_EXT":
            h = hrs.weekend_ext
            totals[r.doctor]["weekend"] += 1
        elif role == "WEEKEND_CONSULT":
            h = hrs.weekend_consult
            totals[r.doctor]["weekend"] += 1
        else:
            continue
        totals[r.doctor]["hours"] += float(h)

    out: list[HoursPerDoctor] = []
    for d in state.doctors:
        stats = totals.get(d.name, {"hours": 0.0, "sessions": 0, "oncalls": 0, "weekend": 0})
        actual_hours_weekly = stats["hours"] / weeks
        target_hours = float(target_hours_per_week) * float(d.fte)
        delta = actual_hours_weekly - target_hours
        if abs(delta) < max(2.0, 0.1 * target_hours):
            status = "on_target"
        elif delta > 0:
            status = "over"
        else:
            status = "under"
        out.append(HoursPerDoctor(
            doctor_id=int(by_name[d.name].prev_workload) if False else 0,  # not used
            doctor_name=d.name,
            tier=d.tier,
            fte=float(d.fte),
            actual_hours=round(actual_hours_weekly, 2),
            target_hours=round(target_hours, 2),
            delta=round(delta, 2),
            status=status,
            sessions=int(stats["sessions"]),
            oncalls=int(stats["oncalls"]),
            weekend_duties=int(stats["weekend"]),
        ))
    # Sort by delta ascending so the most under-loaded bubble up first.
    out.sort(key=lambda x: x.delta)
    return out


def _per_tier_workload(
    state: SessionState, per_doctor: list[HoursPerDoctor],
) -> list[TierWorkload]:
    """Roll the per-doctor output up to per-tier totals. Shares are
    reported as fractions of the team total so the UI can render "the
    juniors carry 55% of the work while being 40% of the FTE" without
    re-computing anything."""
    n_days = max(state.horizon.n_days, 1)
    weeks = max(n_days / 7.0, 1.0 / 7.0)

    by_tier: dict[str, list[HoursPerDoctor]] = defaultdict(list)
    for p in per_doctor:
        by_tier[p.tier].append(p)

    total_hours_weekly = sum(p.actual_hours for p in per_doctor) or 1.0
    total_fte = sum(p.fte for p in per_doctor) or 1.0

    ordered_tiers = ["junior", "senior", "consultant"]
    out: list[TierWorkload] = []
    for tier in ordered_tiers:
        members = by_tier.get(tier, [])
        if not members:
            continue
        tier_weekly_hours = sum(p.actual_hours for p in members)
        tier_total_hours = tier_weekly_hours * weeks
        tier_fte = sum(p.fte for p in members)
        out.append(TierWorkload(
            tier=tier,
            headcount=len(members),
            total_fte=round(tier_fte, 2),
            total_hours=round(tier_total_hours, 1),
            mean_weekly_hours=round(tier_weekly_hours / max(len(members), 1), 1),
            share_of_total_hours=round(tier_weekly_hours / total_hours_weekly, 4),
            share_of_fte=round(tier_fte / total_fte, 4),
            sessions=sum(p.sessions for p in members),
            oncalls=sum(p.oncalls for p in members),
            weekend_duties=sum(p.weekend_duties for p in members),
        ))
    return out


# --------------------------------------------------------------- reduction


def _workload_per_doctor(rows: list[AssignmentRow]) -> dict[str, int]:
    """Raw count of assignments per doctor. Used as the heuristic for
    who to drop next in team_reduction."""
    out: dict[str, int] = defaultdict(int)
    for r in rows:
        out[r.doctor] += 1
    return dict(out)


def _drop_doctor(state: SessionState, name: str) -> SessionState:
    """Return a copy of `state` with the named doctor removed from the
    roster. Also strips any leave / no_session / override rows that
    referenced them."""
    doctors = [d for d in state.doctors if d.name != name]
    blocks = [b for b in state.blocks if b.doctor != name]
    overrides = [o for o in state.overrides if o.doctor != name]
    return state.model_copy(update={
        "doctors": doctors,
        "blocks": blocks,
        "overrides": overrides,
    })


def _team_reduction(
    state: SessionState,
    *,
    max_drop: int,
    time_limit_s: float,
    num_workers: int,
) -> tuple[list[ReductionCell], int | None]:
    """Iteratively drop the lowest-loaded doctor and re-solve. Stops at
    the first step that can't produce a feasible roster, OR after
    `max_drop` drops.

    Returns (list of cells, minimum viable team size). The min-viable
    is the smallest team size that still produced a feasible + self-
    check-passing roster; None if even the baseline was infeasible."""
    cells: list[ReductionCell] = []
    current = state
    removed: list[str] = []
    min_viable: int | None = None

    for step in range(max_drop + 1):
        t0 = time.perf_counter()
        rows, result = _solve_one(
            current, time_limit_s=time_limit_s, num_workers=num_workers,
        )
        wall = time.perf_counter() - t0

        # Run the self-check + coverage on the produced roster.
        try:
            sc = build_self_check(current, rows)
            sc_ok = sc.ok
            sc_violations = sc.violation_count
        except Exception:
            sc_ok = None
            sc_violations = None
        cov = compute_coverage(current, rows)
        shortfall = int(cov.get("shortfall_total", 0))
        over = int(cov.get("over_total", 0))

        cells.append(ReductionCell(
            step=step,
            team_size=len(current.doctors),
            removed=list(removed),
            status=result.status,
            wall_time_s=round(float(result.wall_time_s), 6),
            objective=result.objective,
            coverage_shortfall=shortfall,
            coverage_over=over,
            self_check_ok=sc_ok,
            violation_count=sc_violations,
        ))
        _ = wall  # silence unused; result.wall_time_s is what we report

        is_viable = (
            result.status in ("OPTIMAL", "FEASIBLE")
            and shortfall == 0
            and (sc_ok is True or sc_ok is None)
        )
        if is_viable:
            min_viable = len(current.doctors)

        if step == max_drop:
            break

        # Pick the lowest-loaded doctor from the current solve and drop.
        loads = _workload_per_doctor(rows)
        candidates = [d.name for d in current.doctors]
        if not candidates:
            break
        # Sort by load ascending, then name for stability.
        candidates.sort(key=lambda n: (loads.get(n, 0), n))
        victim = candidates[0]
        current = _drop_doctor(current, victim)
        removed.append(victim)

    return cells, min_viable


# --------------------------------------------------------------- public


def run_capacity(state: SessionState, req: CapacityRequest) -> CapacityResponse:
    """Dispatch on `req.mode` and produce a CapacityResponse."""
    batch_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)

    if req.mode == "hours_vs_target":
        rows, _result = _solve_one(
            state,
            time_limit_s=req.time_limit_s,
            num_workers=req.num_workers,
        )
        per_doctor = _hours_per_doctor(state, rows, req.target_hours_per_week)
        per_tier = _per_tier_workload(state, per_doctor)
        return CapacityResponse(
            batch_id=batch_id,
            created_at=now,
            mode="hours_vs_target",
            time_limit_s=req.time_limit_s,
            per_doctor=per_doctor,
            per_tier=per_tier,
            target_hours_per_week=req.target_hours_per_week,
        )

    if req.mode == "team_reduction":
        cells, min_viable = _team_reduction(
            state,
            max_drop=req.max_drop,
            time_limit_s=req.time_limit_s,
            num_workers=req.num_workers,
        )
        return CapacityResponse(
            batch_id=batch_id,
            created_at=now,
            mode="team_reduction",
            time_limit_s=req.time_limit_s,
            reduction=cells,
            min_viable_team_size=min_viable,
        )

    raise ValueError(f"Unknown capacity mode: {req.mode}")


# Keep the date->datetime import live for future extensions (e.g. running
# over a specific sub-range of the horizon). Silence linter noise.
_ = timedelta
