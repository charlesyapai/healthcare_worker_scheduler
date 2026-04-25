"""Coverage shortfall / over-coverage — first-class NRP metrics.

Per `docs/RESEARCH_METRICS.md §5.1b` and `docs/INDUSTRY_CONTEXT.md §3`.
Tests use small hand-constructed fixtures so the arithmetic is
verifiable on paper."""

from __future__ import annotations

from datetime import date

from api.metrics.coverage import compute_coverage
from api.models.events import AssignmentRow
from api.models.session import (
    ConstraintsConfig,
    DoctorEntry,
    Horizon,
    SessionState,
    StationEntry,
)


def _station(name: str, required: int = 1) -> StationEntry:
    return StationEntry(
        name=name, sessions=["AM", "PM"],
        required_per_session=required,
        eligible_tiers=["junior", "senior", "consultant"],
    )


def _state_with_two_stations() -> SessionState:
    # 3-day weekday horizon starting Mon 2026-05-04.
    return SessionState(
        horizon=Horizon(start_date=date(2026, 5, 4), n_days=3, public_holidays=[]),
        doctors=[
            DoctorEntry(name="A", tier="junior", eligible_stations=["S1", "S2"]),
            DoctorEntry(name="B", tier="senior", eligible_stations=["S1", "S2"]),
        ],
        stations=[_station("S1"), _station("S2", required=1)],
        constraints=ConstraintsConfig(),
    )


def test_empty_assignments_flags_total_shortfall() -> None:
    """Empty roster → shortfall = required × 2 sessions × 3 days × 2 stations."""
    state = _state_with_two_stations()
    out = compute_coverage(state, [])
    # 3 weekdays × 2 stations × 2 sessions = 12 slots, each needing 1 person.
    assert out["shortfall_total"] == 12
    assert out["over_total"] == 0
    assert out["ok"] is False


def test_exact_coverage_is_all_green() -> None:
    state = _state_with_two_stations()
    d0 = state.horizon.start_date
    assignments = []
    from datetime import timedelta
    for day_idx in range(3):
        d = d0 + timedelta(days=day_idx)
        for station in ("S1", "S2"):
            for sess in ("AM", "PM"):
                doctor = "A" if sess == "AM" else "B"
                assignments.append(AssignmentRow(doctor=doctor, date=d, role=f"STATION_{station}_{sess}"))
    out = compute_coverage(state, assignments)
    assert out["shortfall_total"] == 0
    assert out["over_total"] == 0
    assert out["ok"] is True


def test_over_coverage_when_extra_doctor_assigned() -> None:
    state = _state_with_two_stations()
    d0 = state.horizon.start_date
    # Required = 1 each. Assign both A and B to the same slot.
    assignments = [
        AssignmentRow(doctor="A", date=d0, role="STATION_S1_AM"),
        AssignmentRow(doctor="B", date=d0, role="STATION_S1_AM"),
    ]
    out = compute_coverage(state, assignments)
    # S1/AM on day 0 is over-covered by 1. Everything else is shortfalled.
    assert out["over_total"] == 1
    # 11 slots still unfilled.
    assert out["shortfall_total"] == 11


def test_per_station_breakdown_sums_correctly() -> None:
    state = _state_with_two_stations()
    d0 = state.horizon.start_date
    from datetime import timedelta
    assignments = [
        AssignmentRow(doctor="A", date=d0, role="STATION_S1_AM"),
        AssignmentRow(doctor="A", date=d0 + timedelta(days=1), role="STATION_S1_AM"),
    ]
    out = compute_coverage(state, assignments)
    s1 = out["per_station"]["S1"]
    # S1: required = 6 (3 days × 2 sessions × 1), assigned = 2, short = 4
    assert s1["required"] == 6
    assert s1["assigned"] == 2
    assert s1["shortfall"] == 4
    assert s1["over"] == 0
