"""Regression: FULL_DAY stations must pass `api/validator.py` H1.

Context: the CP-SAT model unpacks a FULL_DAY station into paired AM+PM
variables so existing per-session rules keep working (see
`tests/test_full_day.py`). The solver therefore emits
``STATION_<name>_AM`` + ``STATION_<name>_PM`` rows for a FULL_DAY
booking — never ``STATION_<name>_FULL_DAY``. A previous version of
`api/validator.py` iterated ``st.sessions`` literally and looked up
``by_slot[(date, station, "FULL_DAY")]``, which was always empty,
producing a spurious "H1: 0/1 people assigned" error on every day of
every FULL_DAY station. This test locks the fix in.
"""

from __future__ import annotations

from datetime import date, timedelta

from api.models.events import AssignmentRow
from api.models.session import (
    ConstraintsConfig,
    DoctorEntry,
    Horizon,
    SessionState,
    StationEntry,
)
from api.sessions import session_to_instance
from api.validator import validate
from scheduler.model import solve


def _monday() -> date:
    today = date.today()
    return today + timedelta(days=(0 - today.weekday()) % 7)


def _state_with_full_day() -> SessionState:
    """Surgery-shaped fixture: consultant-only FULL_DAY OR_LIST +
    enough supporting headcount so weekend H8 is feasible."""
    doctors = [
        DoctorEntry(name=f"J{i}", tier="junior", subspec=None,
                    eligible_stations=["CLINIC"])
        for i in range(3)
    ] + [
        DoctorEntry(name=f"S{i}", tier="senior", subspec=None,
                    eligible_stations=["CLINIC"])
        for i in range(3)
    ] + [
        DoctorEntry(name="C_General", tier="consultant", subspec="General",
                    eligible_stations=["OR_LIST", "CLINIC"]),
        DoctorEntry(name="C_Ortho", tier="consultant", subspec="Orthopaedic",
                    eligible_stations=["OR_LIST", "CLINIC"]),
        DoctorEntry(name="C_Vasc", tier="consultant", subspec="Vascular",
                    eligible_stations=["OR_LIST", "CLINIC"]),
    ]
    stations = [
        StationEntry(name="OR_LIST", sessions=["FULL_DAY"],
                     required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="CLINIC", sessions=["AM", "PM"],
                     required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"],
                     is_reporting=False),
    ]
    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=5, public_holidays=[]),
        doctors=doctors, stations=stations,
        subspecs=["General", "Orthopaedic", "Vascular"],
        constraints=ConstraintsConfig(h11_enabled=False),
    )


def _assignments_from_result(result, state: SessionState) -> list[AssignmentRow]:
    """Turn a SolveResult's assignments dict into the flat AssignmentRow
    list the validator expects. Kept inline here rather than re-using
    api.sessions.assignments_to_rows to make the test independent of
    that helper's exact signature."""
    start = state.horizon.start_date
    assert start is not None
    rows: list[AssignmentRow] = []
    doc_by_id = {i: d.name for i, d in enumerate(state.doctors)}
    for (d_id, day, st_name, sess), v in result.assignments.get(
        "stations", {}
    ).items():
        if not v:
            continue
        rows.append(AssignmentRow(
            doctor=doc_by_id[d_id],
            date=start + timedelta(days=day),
            role=f"STATION_{st_name}_{sess}",
        ))
    for (d_id, day), v in result.assignments.get("oncall", {}).items():
        if v:
            rows.append(AssignmentRow(
                doctor=doc_by_id[d_id],
                date=start + timedelta(days=day),
                role="ONCALL",
            ))
    for (d_id, day), v in result.assignments.get("ext", {}).items():
        if v:
            rows.append(AssignmentRow(
                doctor=doc_by_id[d_id],
                date=start + timedelta(days=day),
                role="WEEKEND_EXT",
            ))
    for (d_id, day), v in result.assignments.get("wconsult", {}).items():
        if v:
            rows.append(AssignmentRow(
                doctor=doc_by_id[d_id],
                date=start + timedelta(days=day),
                role="WEEKEND_CONSULT",
            ))
    return rows


def test_full_day_solve_passes_validator_h1() -> None:
    state = _state_with_full_day()
    inst = session_to_instance(state)
    result = solve(inst, time_limit_s=10, num_workers=1, feasibility_only=True)
    assert result.status in ("OPTIMAL", "FEASIBLE"), result.status

    rows = _assignments_from_result(result, state)
    violations = validate(state, rows)
    h1_violations = [v for v in violations if v["rule"] == "H1"]
    assert not h1_violations, (
        f"Validator flagged {len(h1_violations)} H1 coverage violation(s) on a "
        f"feasible FULL_DAY solve — the validator doesn't understand the "
        f"paired AM/PM encoding. First violation: {h1_violations[0]}"
    )


def test_full_day_validator_catches_broken_pairing() -> None:
    """If the pairing is violated — say, AM and PM of a FULL_DAY station
    are held by different doctors — the validator MUST flag it. Build
    the broken assignment by hand; no solver involved."""
    state = _state_with_full_day()
    start = state.horizon.start_date
    assert start is not None
    broken_rows = [
        AssignmentRow(doctor="C_General", date=start,
                      role="STATION_OR_LIST_AM"),
        # PM held by a DIFFERENT consultant → pairing broken.
        AssignmentRow(doctor="C_Ortho", date=start,
                      role="STATION_OR_LIST_PM"),
    ]
    violations = validate(state, broken_rows)
    pair_errors = [
        v for v in violations
        if v["rule"] == "H1" and "pairing broken" in v["message"]
    ]
    assert pair_errors, (
        f"Validator missed a broken FULL_DAY pair. Got: {violations}"
    )
