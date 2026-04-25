"""Unit tests for api/metrics/fairness.py.

Hand-computable fixtures cover the core formulae (Gini, CV, FTE
normalisation, per-individual delta). Formulae are documented in
`docs/RESEARCH_METRICS.md §4` — if a number here changes, update the
doc in the same commit.
"""

from __future__ import annotations

from datetime import date

from api.metrics.fairness import compute_fairness
from api.models.events import AssignmentRow
from api.models.session import (
    ConstraintsConfig,
    DoctorEntry,
    Horizon,
    SessionState,
    StationEntry,
    WorkloadWeights,
)


def _station(name: str, tiers: list[str]) -> StationEntry:
    return StationEntry(
        name=name,
        sessions=["AM", "PM"],
        required_per_session=1,
        eligible_tiers=tiers,
        is_reporting=False,
    )


def _state_from_doctors(
    doctors: list[DoctorEntry],
    *,
    start: date = date(2026, 5, 4),  # Monday
    n_days: int = 7,
) -> SessionState:
    return SessionState(
        horizon=Horizon(start_date=start, n_days=n_days, public_holidays=[]),
        doctors=doctors,
        stations=[_station("GEN_AM", ["junior", "senior", "consultant"])],
        workload_weights=WorkloadWeights(),
        constraints=ConstraintsConfig(),
    )


def test_empty_assignments_returns_zeroed_metrics() -> None:
    state = _state_from_doctors([
        DoctorEntry(name="A", tier="junior", fte=1.0, eligible_stations=["GEN_AM"]),
    ])
    out = compute_fairness(state, assignments=[])
    assert out["per_tier"]["junior"]["n"] == 1
    assert out["per_tier"]["junior"]["range"] == 0
    assert out["per_tier"]["junior"]["gini"] == 0
    # Doctor should still appear in per_individual with zeroed fields.
    row = next(r for r in out["per_individual"] if r["doctor"] == "A")
    assert row["weighted_workload"] == 0
    assert row["fte_normalised"] == 0


def test_two_doctor_tier_range_and_gini() -> None:
    """Two juniors, one does twice the weekday station work as the other.
    Weights: weekday_session=10. Doctor A: 2 assignments → 20. Doctor B: 4 → 40.
    FTE=1 for both → fte_normalised = raw.

    Gini hand-calc:
      values = [20, 40], mean = 30
      MAD = (|20-20| + |20-40| + |40-20| + |40-40|) / 4 = 40/4 = 10
      G = MAD / (2 * mean) = 10 / 60 = 0.1667
    """
    state = _state_from_doctors([
        DoctorEntry(name="A", tier="junior", fte=1.0, eligible_stations=["GEN_AM"]),
        DoctorEntry(name="B", tier="junior", fte=1.0, eligible_stations=["GEN_AM"]),
    ])
    d0 = state.horizon.start_date
    assignments = [
        AssignmentRow(doctor="A", date=d0, role="STATION_GEN_AM_AM"),
        AssignmentRow(doctor="A", date=d0, role="STATION_GEN_AM_PM"),
        AssignmentRow(doctor="B", date=d0, role="STATION_GEN_AM_AM"),
        AssignmentRow(doctor="B", date=d0, role="STATION_GEN_AM_PM"),
        AssignmentRow(doctor="B", date=d0, role="STATION_GEN_AM_AM"),
        AssignmentRow(doctor="B", date=d0, role="STATION_GEN_AM_PM"),
    ]
    out = compute_fairness(state, assignments)
    junior = out["per_tier"]["junior"]
    assert junior["n"] == 2
    assert junior["mean"] == 30.0
    assert junior["range"] == 20.0
    # Gini = 10/60 = 0.1667 to 4 dp
    assert abs(junior["gini"] - 0.1667) < 1e-3
    # CV = std/mean. std([20,40]) population = 10. CV = 10/30 = 0.3333
    assert abs(junior["cv"] - 0.3333) < 1e-3


def test_fte_normalisation_flattens_part_timer() -> None:
    """A 0.5-FTE doctor doing half the work of a full-timer should look
    equal *after* FTE-normalisation. FTE-normalised: A=20/1=20, B=10/0.5=20."""
    state = _state_from_doctors([
        DoctorEntry(name="A", tier="junior", fte=1.0, eligible_stations=["GEN_AM"]),
        DoctorEntry(name="B", tier="junior", fte=0.5, eligible_stations=["GEN_AM"]),
    ])
    d0 = state.horizon.start_date
    assignments = [
        # A: 2 weekday sessions × 10 = 20
        AssignmentRow(doctor="A", date=d0, role="STATION_GEN_AM_AM"),
        AssignmentRow(doctor="A", date=d0, role="STATION_GEN_AM_PM"),
        # B: 1 weekday session × 10 = 10 → /0.5 → 20
        AssignmentRow(doctor="B", date=d0, role="STATION_GEN_AM_AM"),
    ]
    out = compute_fairness(state, assignments)
    by_name = {r["doctor"]: r for r in out["per_individual"]}
    assert by_name["A"]["weighted_workload"] == 20
    assert by_name["A"]["fte_normalised"] == 20.0
    assert by_name["B"]["weighted_workload"] == 10
    assert by_name["B"]["fte_normalised"] == 20.0
    # Range over normalised values should be 0.
    assert out["per_tier"]["junior"]["range"] == 0
    assert out["per_tier"]["junior"]["gini"] == 0


def test_oncall_uses_weekend_weight_on_saturday() -> None:
    """Start on Sat → day 0 is a weekend. On-call on day 0 picks the
    weekend_oncall weight (35 by default), not the weekday (20)."""
    state = _state_from_doctors(
        [DoctorEntry(name="A", tier="junior", fte=1.0, eligible_stations=["GEN_AM"])],
        start=date(2026, 5, 2),  # Saturday
        n_days=2,
    )
    assignments = [
        AssignmentRow(doctor="A", date=date(2026, 5, 2), role="ONCALL"),
    ]
    out = compute_fairness(state, assignments)
    a = next(r for r in out["per_individual"] if r["doctor"] == "A")
    assert a["weighted_workload"] == 35  # weekend_oncall default
    assert a["oncall_count"] == 1
    assert a["weekend_count"] == 1


def test_public_holiday_treated_as_weekend() -> None:
    """A weekday marked as a public holiday should trigger the weekend
    weight too."""
    holiday = date(2026, 5, 5)  # Tuesday
    state = SessionState(
        horizon=Horizon(start_date=date(2026, 5, 4), n_days=7, public_holidays=[holiday]),
        doctors=[DoctorEntry(name="A", tier="junior", fte=1.0, eligible_stations=["GEN_AM"])],
        stations=[_station("GEN_AM", ["junior", "senior", "consultant"])],
    )
    assignments = [
        AssignmentRow(doctor="A", date=holiday, role="STATION_GEN_AM_AM"),
    ]
    out = compute_fairness(state, assignments)
    a = next(r for r in out["per_individual"] if r["doctor"] == "A")
    assert a["weighted_workload"] == 15  # weekend_session, not weekday_session=10


def test_dow_load_buckets_by_day_of_week() -> None:
    """Three station assignments on Monday → Mon bucket only."""
    state = _state_from_doctors([
        DoctorEntry(name="A", tier="junior", fte=1.0, eligible_stations=["GEN_AM"]),
    ])
    d0 = state.horizon.start_date  # Mon 2026-05-04
    assignments = [
        AssignmentRow(doctor="A", date=d0, role="STATION_GEN_AM_AM"),
        AssignmentRow(doctor="A", date=d0, role="STATION_GEN_AM_PM"),
    ]
    out = compute_fairness(state, assignments)
    assert out["dow_load"]["junior"]["Mon"] == 20
    assert out["dow_load"]["junior"]["Tue"] == 0
    assert out["dow_load"]["senior"]["Mon"] == 0  # no seniors in fixture


