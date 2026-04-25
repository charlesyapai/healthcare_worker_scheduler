"""Per-doctor role preferences (S7 soft shortfall).

The model adds a soft penalty ``priority × max(0, min − actual)`` to
the objective for each (doctor, role) preference. These tests verify:

1. A preference with priority=0 or min=0 is a no-op.
2. A preference biases the solver toward giving the doctor more of the
   named role — against a "neutral" baseline (no preferences), a high-
   priority preference should increase that doctor's count.
3. An unreachable preference (doctor has no eligibility for the role)
   produces a reported shortfall without crashing.
"""

from __future__ import annotations

from scheduler.instance import (
    Doctor,
    Instance,
    OnCallType,
    Station,
    default_on_call_types,
    eligible_types_for_tier,
)
from scheduler.model import solve

# Default on-call types for the role-preferences fixture so legacy ONCALL
# preferences resolve to actual solver vars.
_TYPES = default_on_call_types(weekday_oncall=False)
_ELIG_JR = eligible_types_for_tier("junior", _TYPES)
_ELIG_SR = eligible_types_for_tier("senior", _TYPES)
_ELIG_CN = eligible_types_for_tier("consultant", _TYPES)


def _base_doctors_stations() -> tuple[list[Doctor], list[Station]]:
    """Small radiology-flavoured fixture. 6 doctors, 5 stations, 2
    consultants so weekend H8 is trivially satisfiable.
    Juniors are eligible for US + XR_REPORT; seniors + CT + MR on top."""
    doctors = [
        Doctor(id=0, tier="junior",
               eligible_stations=frozenset({"US", "XR_REPORT"}),
               eligible_oncall_types=_ELIG_JR),
        Doctor(id=1, tier="junior",
               eligible_stations=frozenset({"US", "XR_REPORT"}),
               eligible_oncall_types=_ELIG_JR),
        Doctor(id=2, tier="senior",
               eligible_stations=frozenset({"CT", "MR", "US", "XR_REPORT"}),
               eligible_oncall_types=_ELIG_SR),
        Doctor(id=3, tier="senior",
               eligible_stations=frozenset({"CT", "MR", "US", "XR_REPORT"}),
               eligible_oncall_types=_ELIG_SR),
        Doctor(id=4, tier="consultant",
               eligible_stations=frozenset({"CT", "MR", "US", "XR_REPORT"}),
               eligible_oncall_types=_ELIG_CN),
        Doctor(id=5, tier="consultant",
               eligible_stations=frozenset({"CT", "MR", "US", "XR_REPORT"}),
               eligible_oncall_types=_ELIG_CN),
    ]
    stations = [
        Station(name="CT", sessions=("AM", "PM"), required_per_session=1,
                eligible_tiers=frozenset({"senior", "consultant"})),
        Station(name="MR", sessions=("AM", "PM"), required_per_session=1,
                eligible_tiers=frozenset({"senior", "consultant"})),
        Station(name="US", sessions=("AM", "PM"), required_per_session=2,
                eligible_tiers=frozenset({"junior", "senior", "consultant"})),
        Station(name="XR_REPORT", sessions=("AM", "PM"), required_per_session=1,
                eligible_tiers=frozenset({"junior", "senior", "consultant"})),
    ]
    return doctors, stations


def _count_station_assignments(result, doctor_id: int, station: str) -> int:
    """Helper: count AM + PM hits for (doctor, station) in a result."""
    total = 0
    for (d, _day, st, _sess), v in result.assignments.get("stations", {}).items():
        if d == doctor_id and st == station and v:
            total += 1
    return total


def _short_instance(
    n_days: int = 5,
    role_preferences: dict | None = None,
) -> Instance:
    doctors, stations = _base_doctors_stations()
    # 5 weekdays, start Monday → everything in the horizon is a weekday.
    return Instance(
        n_days=n_days, start_weekday=0,
        doctors=doctors, stations=stations,
        on_call_types=_TYPES,
        role_preferences=role_preferences or {},
    )


def test_zero_priority_or_min_is_noop() -> None:
    """A preference with priority = 0 or min = 0 mustn't change the
    objective. A regression here would silently tax every solve."""
    # Senior (id=2) gets a "preference" for CT but with min = 0.
    baseline = solve(_short_instance(), time_limit_s=5, num_workers=1)
    with_zero = solve(
        _short_instance(role_preferences={2: {"CT": (0, 5)}}),
        time_limit_s=5, num_workers=1,
    )
    assert baseline.objective == with_zero.objective


def test_high_priority_preference_biases_toward_role() -> None:
    """With a strong preference for CT, senior 2 should get at least
    as many CT hits as in a baseline run (usually strictly more).

    We can't assert strict >, because the baseline may already be at the
    ceiling (CT has demand 2 × 5 = 10 senior-or-consultant slots, senior 2
    is one of 4 eligible doctors). But strong preferences shouldn't
    *reduce* the count, which is the floor we lock in."""
    baseline = solve(_short_instance(), time_limit_s=5, num_workers=1)
    baseline_ct = _count_station_assignments(baseline, 2, "CT")

    with_pref = solve(
        _short_instance(role_preferences={2: {"CT": (5, 10)}}),
        time_limit_s=5, num_workers=1,
    )
    with_pref_ct = _count_station_assignments(with_pref, 2, "CT")
    assert with_pref_ct >= baseline_ct, (
        f"Preference for CT (priority=10) caused senior 2's CT count to "
        f"fall from {baseline_ct} to {with_pref_ct}."
    )


def test_ineligible_role_produces_constant_shortfall_no_crash() -> None:
    """Junior 0 isn't eligible for CT (seniors + consultants only). A
    preference for CT is permanently unsatisfiable; the solver should
    record the shortfall in the penalty_components without raising."""
    result = solve(
        _short_instance(role_preferences={0: {"CT": (3, 5)}}),
        time_limit_s=5, num_workers=1,
    )
    assert result.status in ("OPTIMAL", "FEASIBLE")
    # S7_role_pref_<did>_<role>_missed component should exist.
    missed_keys = [
        k for k in result.penalty_components
        if k.startswith("S7_role_pref_0_CT_missed")
    ]
    assert missed_keys, (
        f"Expected an S7 missed-preference component for junior 0 on CT. "
        f"Got components: {sorted(result.penalty_components)}"
    )


def test_oncall_role_preference_counts_oncall_vars() -> None:
    """Role preferences accept 'ONCALL' (legacy) and 'ONCALL_<type_key>'
    (Phase B). The solver resolves the legacy alias to any type whose
    `legacy_role_alias=='ONCALL'` and that the doctor is eligible for.
    With weekday on-call enabled the senior MUST do at least one
    oncall_sr night under H8 daily_required, and the preference biases
    the solver to pick this senior over others in the tier."""
    types = default_on_call_types(weekday_oncall=True)
    elig_sr = eligible_types_for_tier("senior", types)
    elig_jr = eligible_types_for_tier("junior", types)
    elig_cn = eligible_types_for_tier("consultant", types)
    # Bench: 4 sr (so 5 weekday on-calls + 2 weekend on-calls fit under
    # H4 1-in-3 cap), 4 jr, 2 cn.
    doctors = [
        Doctor(id=i, tier="junior",
               eligible_stations=frozenset({"US", "XR_REPORT"}),
               eligible_oncall_types=elig_jr) for i in range(4)
    ]
    doctors += [
        Doctor(id=4 + i, tier="senior",
               eligible_stations=frozenset({"CT", "MR", "US", "XR_REPORT"}),
               eligible_oncall_types=elig_sr) for i in range(4)
    ]
    doctors += [
        Doctor(id=8 + i, tier="consultant",
               eligible_stations=frozenset({"CT", "MR", "US", "XR_REPORT"}),
               eligible_oncall_types=elig_cn) for i in range(2)
    ]
    _, stations = _base_doctors_stations()
    inst = Instance(
        n_days=7, start_weekday=0,
        doctors=doctors, stations=stations, on_call_types=types,
        # Senior id=4 gets a preference for ONCALL.
        role_preferences={4: {"ONCALL": (2, 5)}},
    )
    result = solve(inst, time_limit_s=10, num_workers=1)
    assert result.status in ("OPTIMAL", "FEASIBLE")
    # Senior id=4 should have at least one oncall_sr in the horizon.
    obt = result.assignments.get("oncall_by_type", {})
    sr_oncall = sum(1 for (d, _day) in obt.get("oncall_sr", {}) if d == 4)
    assert sr_oncall >= 1
