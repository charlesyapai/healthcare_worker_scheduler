"""Phase A: tier eligibility is decoupled from station eligibility.

`station.eligible_tiers` is advisory metadata only — the solver enforces
only `doctor.eligible_stations`. A doctor whose tier is *not* in a
station's `eligible_tiers` set can still be assigned there if their
own eligibility list includes the station.
"""

from __future__ import annotations

from scheduler.instance import Doctor, Instance, Station
from scheduler.model import ConstraintConfig, solve


def test_senior_assignable_to_junior_only_station() -> None:
    """A station with eligible_tiers={'junior'} (advisory) — but a senior
    explicitly listed on it via per-doctor eligibility — must be allowed
    to cover that station. Pre-Phase-A, this would have been rejected
    at solver var-creation time."""
    doctors = [
        # Junior eligible for the station (canonical).
        Doctor(id=0, tier="junior",
               eligible_stations=frozenset({"WARD"})),
        # Senior also explicitly listed on the same station, even though
        # the station's advisory tier set is junior-only.
        Doctor(id=1, tier="senior",
               eligible_stations=frozenset({"WARD"})),
        # Need a junior+senior pair so weekend H8 is satisfiable on the
        # short horizon (the test focuses on weekday eligibility).
        Doctor(id=2, tier="junior",
               eligible_stations=frozenset({"WARD"})),
        Doctor(id=3, tier="senior",
               eligible_stations=frozenset({"WARD"})),
        Doctor(id=4, tier="consultant",
               eligible_stations=frozenset({"WARD"})),
    ]
    stations = [
        Station(
            name="WARD",
            sessions=("AM", "PM"),
            required_per_session=1,
            # Advisory: ward is "usually" junior-only. The solver should
            # ignore this — only per-doctor eligibility matters.
            eligible_tiers=frozenset({"junior"}),
        ),
    ]
    inst = Instance(
        n_days=3,             # Mon/Tue/Wed — no weekend
        start_weekday=0,
        doctors=doctors,
        stations=stations,
    )
    # Disable H11 so the solver doesn't fight the small bench.
    cfg = ConstraintConfig(h11_mandatory_weekday_enabled=False)
    result = solve(inst, time_limit_s=10, num_workers=1,
                   feasibility_only=True, constraints=cfg)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status

    # Force the senior to take WARD by leaving everyone else off it.
    # Easier check: confirm the var was *created* (not gated out at
    # var-creation time). If decoupling is honoured, var (1, 0, "WARD",
    # "AM") and friends exist; if the old gate is in place, they don't,
    # and the solver would either be infeasible (juniors only) or
    # silently exclude the senior.
    inst_only_senior = Instance(
        n_days=1,
        start_weekday=0,
        doctors=[
            # Only one doctor: a senior. If tier eligibility is still a
            # hard rule, the solver can't satisfy WARD/AM coverage.
            Doctor(id=0, tier="senior",
                   eligible_stations=frozenset({"WARD"})),
        ],
        stations=[
            Station(
                name="WARD",
                sessions=("AM", "PM"),
                required_per_session=1,
                eligible_tiers=frozenset({"junior"}),
            ),
        ],
    )
    # Phase B: per-type on-call rules replace the legacy global flags.
    # The fixture has no on_call_types, so H4/H5/H6/H7/H8 are all no-ops
    # — only H11/H9/H5 master toggles remain on ConstraintConfig.
    cfg2 = ConstraintConfig(
        h11_mandatory_weekday_enabled=False,
        h5_post_call_off_enabled=False,
    )
    res2 = solve(inst_only_senior, time_limit_s=5, num_workers=1,
                 feasibility_only=True, constraints=cfg2)
    assert res2.status in ("OPTIMAL", "FEASIBLE"), (
        f"Senior on a junior-only station should be solvable when only "
        f"per-doctor eligibility is enforced — got {res2.status}."
    )
    # Senior 0 must have taken both AM and PM of WARD.
    assert (0, 0, "WARD", "AM") in res2.assignments["stations"]
    assert (0, 0, "WARD", "PM") in res2.assignments["stations"]
