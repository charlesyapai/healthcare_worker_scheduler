"""Phase A: per-station weekday_enabled / weekend_enabled flags.

Replaces the old global `Instance.weekend_am_pm_enabled` toggle.
A station with `weekend_enabled=True` produces weekend bookings; a
station with `weekend_enabled=False` does not, regardless of how many
other stations are weekend-on.
"""

from __future__ import annotations

from scheduler.instance import Doctor, Instance, Station
from scheduler.model import ConstraintConfig, solve


def _doctors() -> list[Doctor]:
    """Mixed-tier bench big enough to satisfy weekend H8 + H4 1-in-3
    on-call cap across a 7-day horizon."""
    return [
        Doctor(id=0, tier="junior", eligible_stations=frozenset({"DAY", "WEEKEND_DAY"})),
        Doctor(id=1, tier="junior", eligible_stations=frozenset({"DAY", "WEEKEND_DAY"})),
        Doctor(id=2, tier="junior", eligible_stations=frozenset({"DAY", "WEEKEND_DAY"})),
        Doctor(id=3, tier="junior", eligible_stations=frozenset({"DAY", "WEEKEND_DAY"})),
        Doctor(id=4, tier="senior", eligible_stations=frozenset({"DAY", "WEEKEND_DAY"})),
        Doctor(id=5, tier="senior", eligible_stations=frozenset({"DAY", "WEEKEND_DAY"})),
        Doctor(id=6, tier="senior", eligible_stations=frozenset({"DAY", "WEEKEND_DAY"})),
        Doctor(id=7, tier="senior", eligible_stations=frozenset({"DAY", "WEEKEND_DAY"})),
        Doctor(id=8, tier="consultant", eligible_stations=frozenset({"DAY", "WEEKEND_DAY"})),
        Doctor(id=9, tier="consultant", eligible_stations=frozenset({"DAY", "WEEKEND_DAY"})),
    ]


def test_weekend_enabled_station_produces_weekend_bookings() -> None:
    """A station with `weekend_enabled=True` must be staffed on weekend
    days. A weekday-only station (default) must NOT be."""
    stations = [
        # Weekday-only (defaults).
        Station(name="DAY", sessions=("AM", "PM"), required_per_session=1,
                eligible_tiers=frozenset({"junior", "senior", "consultant"})),
        # Weekend-only.
        Station(name="WEEKEND_DAY", sessions=("AM", "PM"),
                required_per_session=1,
                eligible_tiers=frozenset({"junior", "senior", "consultant"}),
                weekday_enabled=False, weekend_enabled=True),
    ]
    inst = Instance(
        n_days=7,
        start_weekday=0,  # Mon..Sun → 5,6 are weekend
        doctors=_doctors(),
        stations=stations,
    )
    # Disable H11 + weekday on-call coverage so the small bench isn't
    # at the mercy of idle-weekday / weekday on-call pressure. The test
    # focuses on station-level weekend_enabled gating, not on-call.
    cfg = ConstraintConfig(
        h11_mandatory_weekday_enabled=False,
        weekday_oncall_coverage_enabled=False,
    )
    result = solve(inst, time_limit_s=10, num_workers=1,
                   feasibility_only=True, constraints=cfg)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status

    stations_assigned = result.assignments["stations"]

    # WEEKEND_DAY must produce assignments on Sat (day 5) and Sun (day 6).
    sat_weekend_day = [
        k for k in stations_assigned
        if k[1] == 5 and k[2] == "WEEKEND_DAY"
    ]
    sun_weekend_day = [
        k for k in stations_assigned
        if k[1] == 6 and k[2] == "WEEKEND_DAY"
    ]
    assert sat_weekend_day, "WEEKEND_DAY (weekend_enabled=True) should be staffed on Sat"
    assert sun_weekend_day, "WEEKEND_DAY (weekend_enabled=True) should be staffed on Sun"

    # WEEKEND_DAY must NOT have any weekday assignment (weekday_enabled=False).
    weekday_weekend_day = [
        k for k in stations_assigned
        if k[1] in (0, 1, 2, 3, 4) and k[2] == "WEEKEND_DAY"
    ]
    assert not weekday_weekend_day, (
        f"WEEKEND_DAY (weekday_enabled=False) leaked onto weekdays: "
        f"{sorted(weekday_weekend_day)}"
    )

    # DAY (weekend_enabled=False) must NOT have weekend assignments.
    weekend_day = [
        k for k in stations_assigned
        if k[1] in (5, 6) and k[2] == "DAY"
    ]
    assert not weekend_day, (
        f"DAY (weekend_enabled=False) was scheduled on the weekend: "
        f"{sorted(weekend_day)}"
    )
