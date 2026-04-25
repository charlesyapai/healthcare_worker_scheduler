"""Phase A: H8 weekend consultant rule is configurable count, not per-subspec.

The old rule was "1 consultant per subspec". Phase A replaces it with a
flat configurable count `Instance.weekend_consultants_required`. Verify
the solver fills exactly that many wconsult slots per weekend day.
"""

from __future__ import annotations

from scheduler.instance import Doctor, Instance, Station
from scheduler.model import ConstraintConfig, solve


def _fixture(weekend_consultants_required: int) -> Instance:
    """Headcount sized for a 2-day Sat+Sun horizon: 3 juniors and
    3 seniors (so H8's ext+oncall demands clear under H5 post-call),
    and 4 consultants (enough for required up to 4)."""
    doctors = [
        Doctor(id=0, tier="junior", eligible_stations=frozenset({"WARD"})),
        Doctor(id=1, tier="junior", eligible_stations=frozenset({"WARD"})),
        Doctor(id=2, tier="junior", eligible_stations=frozenset({"WARD"})),
        Doctor(id=3, tier="senior", eligible_stations=frozenset({"WARD"})),
        Doctor(id=4, tier="senior", eligible_stations=frozenset({"WARD"})),
        Doctor(id=5, tier="senior", eligible_stations=frozenset({"WARD"})),
        Doctor(id=6, tier="consultant", eligible_stations=frozenset({"WARD"})),
        Doctor(id=7, tier="consultant", eligible_stations=frozenset({"WARD"})),
        Doctor(id=8, tier="consultant", eligible_stations=frozenset({"WARD"})),
        Doctor(id=9, tier="consultant", eligible_stations=frozenset({"WARD"})),
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
        start_weekday=5,  # Sat,Sun → both days are weekend.
        doctors=doctors,
        stations=stations,
        weekend_consultants_required=weekend_consultants_required,
    )


def _weekend_only_cfg() -> ConstraintConfig:
    """Disable H11 (no weekday demand) so a pure-weekend fixture stays
    feasible without idle-weekday penalty churn."""
    return ConstraintConfig(h11_mandatory_weekday_enabled=False)


def test_h8_count_one() -> None:
    """Default (weekend_consultants_required=1): exactly one consultant
    on wconsult duty per weekend day."""
    inst = _fixture(weekend_consultants_required=1)
    result = solve(inst, time_limit_s=10, num_workers=1,
                   feasibility_only=True, constraints=_weekend_only_cfg())
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status
    wconsult = result.assignments["wconsult"]
    sat_count = sum(1 for (_did, day) in wconsult if day == 0)
    sun_count = sum(1 for (_did, day) in wconsult if day == 1)
    assert sat_count == 1, f"Sat should have 1 wconsult, got {sat_count}"
    assert sun_count == 1, f"Sun should have 1 wconsult, got {sun_count}"


def test_h8_count_two() -> None:
    """weekend_consultants_required=2: exactly two consultants on
    wconsult duty per weekend day."""
    inst = _fixture(weekend_consultants_required=2)
    result = solve(inst, time_limit_s=10, num_workers=1,
                   feasibility_only=True, constraints=_weekend_only_cfg())
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status
    wconsult = result.assignments["wconsult"]
    sat_count = sum(1 for (_did, day) in wconsult if day == 0)
    sun_count = sum(1 for (_did, day) in wconsult if day == 1)
    assert sat_count == 2, f"Sat should have 2 wconsult, got {sat_count}"
    assert sun_count == 2, f"Sun should have 2 wconsult, got {sun_count}"


def test_h8_count_zero_skips_consultant_rule() -> None:
    """weekend_consultants_required=0 means no consultant is forced on
    wconsult duty (other H8 roles still apply). The solver may still
    place a consultant via H11 / objective, but the rule itself
    doesn't require any."""
    inst = _fixture(weekend_consultants_required=0)
    result = solve(inst, time_limit_s=10, num_workers=1,
                   feasibility_only=True, constraints=_weekend_only_cfg())
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status
    # No assertion on count — rule is simply not enforced.
