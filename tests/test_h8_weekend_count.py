"""Phase B: H8 weekend consultant rule expressed as per-OnCallType
`daily_required`.

Phase A replaced the legacy "1 consultant per subspec" rule with a flat
configurable count. Phase B then folds that count into a regular
`OnCallType.daily_required` field on a `weekend_consult` type — no
special-casing in the solver, just one number on the type.
"""

from __future__ import annotations

from dataclasses import replace

from scheduler.instance import (
    Doctor,
    Instance,
    OnCallType,
    Station,
    default_on_call_types,
    eligible_types_for_tier,
)
from scheduler.model import ConstraintConfig, solve


def _fixture(weekend_consultants_required: int) -> Instance:
    """2-day Sat+Sun fixture with enough headcount to cover up to 4
    weekend consultants. Bench: 3 jr + 3 sr + 4 cn + 1 station."""
    doctors_data = [
        ("J0", "junior"), ("J1", "junior"), ("J2", "junior"),
        ("S0", "senior"), ("S1", "senior"), ("S2", "senior"),
        ("C0", "consultant"), ("C1", "consultant"),
        ("C2", "consultant"), ("C3", "consultant"),
    ]
    types = default_on_call_types(weekday_oncall=False)
    types = [
        replace(t, daily_required=weekend_consultants_required)
        if t.key == "weekend_consult" else t
        for t in types
    ]
    eligible = {tier: eligible_types_for_tier(tier, types)
                for tier in ("junior", "senior", "consultant")}
    doctors = [
        Doctor(id=i, tier=tier,
               eligible_stations=frozenset({"WARD"}),
               eligible_oncall_types=eligible[tier])
        for i, (_name, tier) in enumerate(doctors_data)
    ]
    stations = [
        Station(
            name="WARD",
            sessions=("AM", "PM"),
            required_per_session=1,
            eligible_tiers=frozenset({"junior", "senior", "consultant"}),
        ),
    ]
    return Instance(
        n_days=2,
        start_weekday=5,
        doctors=doctors,
        stations=stations,
        on_call_types=types,
    )


def _weekend_only_cfg() -> ConstraintConfig:
    return ConstraintConfig(h11_mandatory_weekday_enabled=False)


def test_h8_count_one() -> None:
    """daily_required=1: exactly one consultant on weekend_consult per
    weekend day."""
    inst = _fixture(weekend_consultants_required=1)
    result = solve(inst, time_limit_s=10, num_workers=1,
                   feasibility_only=True, constraints=_weekend_only_cfg())
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status
    by_type = result.assignments["oncall_by_type"]
    sat = sum(1 for (_did, day) in by_type["weekend_consult"] if day == 0)
    sun = sum(1 for (_did, day) in by_type["weekend_consult"] if day == 1)
    assert sat == 1, f"Sat should have 1 weekend_consult, got {sat}"
    assert sun == 1, f"Sun should have 1 weekend_consult, got {sun}"


def test_h8_count_two() -> None:
    """daily_required=2: exactly two consultants on weekend_consult per
    weekend day."""
    inst = _fixture(weekend_consultants_required=2)
    result = solve(inst, time_limit_s=10, num_workers=1,
                   feasibility_only=True, constraints=_weekend_only_cfg())
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status
    by_type = result.assignments["oncall_by_type"]
    sat = sum(1 for (_did, day) in by_type["weekend_consult"] if day == 0)
    sun = sum(1 for (_did, day) in by_type["weekend_consult"] if day == 1)
    assert sat == 2, f"Sat should have 2 weekend_consult, got {sat}"
    assert sun == 2, f"Sun should have 2 weekend_consult, got {sun}"


def test_h8_count_zero_skips_consultant_rule() -> None:
    """daily_required=0 means no consultant is forced on weekend_consult.
    The solver may still place a consultant via H11 / objective, but the
    rule itself doesn't require any."""
    inst = _fixture(weekend_consultants_required=0)
    result = solve(inst, time_limit_s=10, num_workers=1,
                   feasibility_only=True, constraints=_weekend_only_cfg())
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status
