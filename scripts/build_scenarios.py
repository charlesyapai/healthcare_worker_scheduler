"""Generate the pre-built scenarios shipped with the app.

Each scenario is verified against the solver before its YAML is written.
Outputs go to configs/scenarios/<id>.yaml plus a manifest.json that lists
id, title, one-line description, a small stat line, and (new) a category
+ tags so the Dashboard UI can group them into Quickstart / Specialty /
Realistic / Research buckets.

Run from repo root:

    python scripts/build_scenarios.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models.session import (  # noqa: E402
    BlockEntry,
    ConstraintsConfig,
    DoctorEntry,
    Horizon,
    Hours,
    OnCallType,
    SessionState,
    ShiftLabels,
    StationEntry,
    TierLabels,
)


# ============================================================== rota presets
#
# Mirrors the four presets the Shape sub-tab ships on the UI. Each
# scenario picks one of these so the template demonstrates the
# matching shift-label / hours shape — a clinic-style scenario gets
# "Morning 08:00–13:00" labels, a 24/7 ED gets "Early / Late / Night",
# a surgical department enables FULL_DAY for theatre lists, and so on.
# Keeping the source of truth here (duplicated from the UI) avoids the
# backend having to import from the frontend or ship a shared YAML.

RotaPresetKey = str  # "clinic" | "day_night_12h" | "surgical" | "shift_24_7"


@dataclass(frozen=True)
class _RotaPreset:
    labels: ShiftLabels
    hours: Hours
    # Whether the preset implies AM/PM stations also run on Saturdays /
    # Sundays. Phase A: stamped onto each station's `weekend_enabled` flag
    # (replacing the dropped global `weekend_am_pm` constraint).
    weekend_am_pm: bool
    # Phase B: per-OnCallType days_active replaces this. The flag still
    # lives on the preset so `_apply_preset` can decide whether to enable
    # the legacy 5-default-types' weekday on-call.
    weekday_oncall_coverage: bool


ROTA_PRESETS: dict[RotaPresetKey, _RotaPreset] = {
    "clinic": _RotaPreset(
        labels=ShiftLabels(
            am="Morning 08:00–13:00",
            pm="Afternoon 13:00–18:00",
            full_day="Full day 08:00–18:00",
            oncall="Night call 20:00–08:00",
            weekend_ext="Weekend extended",
            weekend_consult="Weekend consultant",
        ),
        hours=Hours(
            weekday_am=4, weekday_pm=4,
            weekend_am=4, weekend_pm=4,
            weekday_oncall=12, weekend_oncall=16,
            weekend_ext=12, weekend_consult=8,
        ),
        weekend_am_pm=False,
        weekday_oncall_coverage=False,
    ),
    "day_night_12h": _RotaPreset(
        labels=ShiftLabels(
            am="Day 08:00–14:00",
            pm="Day 14:00–20:00",
            full_day="Day shift 08:00–20:00",
            oncall="Night 20:00–08:00",
            weekend_ext="Weekend day",
            weekend_consult="Weekend consultant",
        ),
        hours=Hours(
            weekday_am=6, weekday_pm=6,
            weekend_am=6, weekend_pm=6,
            weekday_oncall=12, weekend_oncall=12,
            weekend_ext=12, weekend_consult=12,
        ),
        weekend_am_pm=True,
        weekday_oncall_coverage=True,
    ),
    "surgical": _RotaPreset(
        labels=ShiftLabels(
            am="Morning 08:00–13:00",
            pm="Afternoon 13:00–17:00",
            full_day="OR list 08:00–17:00",
            oncall="Night call 17:00–08:00",
            weekend_ext="Weekend on-call",
            weekend_consult="Weekend consultant",
        ),
        hours=Hours(
            weekday_am=4, weekday_pm=4,
            weekend_am=4, weekend_pm=4,
            weekday_oncall=15, weekend_oncall=16,
            weekend_ext=12, weekend_consult=9,
        ),
        weekend_am_pm=False,
        weekday_oncall_coverage=True,
    ),
    "shift_24_7": _RotaPreset(
        labels=ShiftLabels(
            am="Early 07:00–15:00",
            pm="Late 15:00–23:00",
            full_day="Long day 07:00–23:00",
            oncall="Night 23:00–07:00",
            weekend_ext="Weekend long day",
            weekend_consult="Weekend consultant",
        ),
        hours=Hours(
            weekday_am=8, weekday_pm=8,
            weekend_am=8, weekend_pm=8,
            weekday_oncall=8, weekend_oncall=8,
            weekend_ext=12, weekend_consult=10,
        ),
        weekend_am_pm=True,
        weekday_oncall_coverage=True,
    ),
}


def _legacy_oncall_types(
    *,
    weekday_oncall: bool,
    weekend_h8: bool = True,
    weekend_consultants_required: int = 1,
) -> list[OnCallType]:
    """Phase B: synthesize the 5 legacy default on-call types as Pydantic
    OnCallType entries. Mirrors `scheduler.instance.default_on_call_types`
    but emits the `OnCallType` Pydantic model used by the scenario
    pipeline."""
    night_days: list[str] = []
    if weekday_oncall:
        night_days.extend(["Mon", "Tue", "Wed", "Thu", "Fri"])
    if weekend_h8:
        night_days.extend(["Sat", "Sun"])
    weekend_days = ["Sat", "Sun"] if weekend_h8 else []
    types: list[OnCallType] = []
    if night_days:
        types.append(OnCallType.model_validate({
            "key": "oncall_jr",
            "label": "Night call (junior)",
            "start_hour": 20, "end_hour": 8,
            "days_active": night_days,
            "eligible_tiers": ["junior"],
            "daily_required": 1,
            "next_day_off": True, "frequency_cap_days": 3,
            "counts_as_weekend_role": False,
            "works_full_day": False, "works_pm_only": True,
            "legacy_role_alias": "ONCALL",
        }))
        types.append(OnCallType.model_validate({
            "key": "oncall_sr",
            "label": "Night call (senior)",
            "start_hour": 20, "end_hour": 8,
            "days_active": night_days,
            "eligible_tiers": ["senior"],
            "daily_required": 1,
            "next_day_off": True, "frequency_cap_days": 3,
            "counts_as_weekend_role": False,
            "works_full_day": True, "works_pm_only": False,
            "legacy_role_alias": "ONCALL",
        }))
    if weekend_days:
        types.append(OnCallType.model_validate({
            "key": "weekend_ext_jr",
            "label": "Weekend extended (junior)",
            "start_hour": 8, "end_hour": 20,
            "days_active": weekend_days,
            "eligible_tiers": ["junior"],
            "daily_required": 1,
            "next_day_off": False, "frequency_cap_days": None,
            "counts_as_weekend_role": True,
            "legacy_role_alias": "WEEKEND_EXT",
        }))
        types.append(OnCallType.model_validate({
            "key": "weekend_ext_sr",
            "label": "Weekend extended (senior)",
            "start_hour": 8, "end_hour": 20,
            "days_active": weekend_days,
            "eligible_tiers": ["senior"],
            "daily_required": 1,
            "next_day_off": False, "frequency_cap_days": None,
            "counts_as_weekend_role": True,
            "legacy_role_alias": "WEEKEND_EXT",
        }))
        if weekend_consultants_required > 0:
            types.append(OnCallType.model_validate({
                "key": "weekend_consult",
                "label": "Weekend consultant",
                "start_hour": 8, "end_hour": 17,
                "days_active": weekend_days,
                "eligible_tiers": ["consultant"],
                "daily_required": int(weekend_consultants_required),
                "next_day_off": False, "frequency_cap_days": None,
                "counts_as_weekend_role": True,
                "legacy_role_alias": "WEEKEND_CONSULT",
            }))
    return types


def _eligible_oncall_keys_for_tier(tier: str, types: list[OnCallType]) -> list[str]:
    return [t.key for t in types if tier in t.eligible_tiers]


def _apply_preset(state: SessionState, preset_key: RotaPresetKey) -> SessionState:
    """Stamp the rota preset's labels + hours onto a scenario's
    SessionState. Presets also carry an opinion on whether AM/PM stations
    run on weekends (per-station weekend_enabled, Phase A) and whether
    weekday on-call coverage is required (Phase B: encoded as days_active
    on the migrated default on-call types). Scenarios may override the
    on-call types or constraints before the preset is applied; if they
    do, we preserve their explicit choice."""
    p = ROTA_PRESETS[preset_key]
    new_stations = [
        s.model_copy(update={"weekend_enabled": p.weekend_am_pm})
        for s in state.stations
    ]
    # If the scenario already explicitly set on_call_types, leave them.
    if state.on_call_types:
        on_call_types = state.on_call_types
    else:
        on_call_types = _legacy_oncall_types(
            weekday_oncall=p.weekday_oncall_coverage,
            weekend_h8=True,
        )
    # Populate per-doctor `eligible_oncall_types` if missing. We only
    # backfill — preserving any per-doctor list the scenario set.
    eligible_for = {
        tier: _eligible_oncall_keys_for_tier(tier, on_call_types)
        for tier in ("junior", "senior", "consultant")
    }
    new_doctors = [
        d.model_copy(update={
            "eligible_oncall_types": (
                d.eligible_oncall_types
                if d.eligible_oncall_types
                else eligible_for.get(d.tier, [])
            ),
        })
        for d in state.doctors
    ]
    return state.model_copy(update={
        "shift_labels": p.labels,
        "hours": p.hours,
        "stations": new_stations,
        "on_call_types": on_call_types,
        "doctors": new_doctors,
    })
from api.sessions import (  # noqa: E402
    session_to_instance,
    session_to_solver_configs,
    session_to_v1_dict,
)
from scheduler.model import solve  # noqa: E402
from scheduler.persistence import dump_state  # noqa: E402


def _monday() -> date:
    today = date.today()
    return today + timedelta(days=(0 - today.weekday()) % 7)


# ------------------------------------------------------------- Scenario 1

def radiology_small() -> SessionState:
    """15 doctors × 7 days. Radiology. Clean slate — no leave, no overrides.
    Reaches OPTIMAL in ~7s."""
    doctors: list[DoctorEntry] = []
    for n in ["Dr A", "Dr B", "Dr C", "Dr D", "Dr E"]:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in ["Dr F", "Dr G", "Dr H", "Dr I"]:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in [("Dr J", "Neuro"), ("Dr K", "Neuro"),
                  ("Dr L", "Body"), ("Dr M", "Body"),
                  ("Dr N", "MSK"), ("Dr O", "MSK")]:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "IR", "FLUORO"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    stations = [
        StationEntry(name="CT", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="MR", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="US", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="XR_REPORT", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=True),
        StationEntry(name="IR", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="FLUORO", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="GEN_AM", sessions=["AM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="GEN_PM", sessions=["PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
    ]
    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=7, public_holidays=[]),
        doctors=doctors, stations=stations,
    )


# ------------------------------------------------------------- Scenario 2

def busy_month_with_leave() -> SessionState:
    """22 doctors × 14 days with a public holiday and scattered leave.
    Bigger problem with realistic constraints; proves the solver handles
    leave + public holidays together."""
    doctors: list[DoctorEntry] = []

    juniors = [f"J{i+1}" for i in range(8)]
    seniors = [f"S{i+1}" for i in range(6)]
    consultants_ns = [("C1", "Neuro"), ("C2", "Neuro"),
                      ("C3", "Body"), ("C4", "Body"),
                      ("C5", "MSK"), ("C6", "MSK"),
                      ("C7", "Neuro"), ("C8", "Body")]
    for n in juniors:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants_ns:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "IR", "FLUORO"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    stations = radiology_small().stations  # same shape, fine

    start = _monday()
    holiday = start + timedelta(days=3)

    # Small amount of leave — keep the system feasible.
    blocks = [
        BlockEntry(doctor="J2", date=start + timedelta(days=1),
                   end_date=start + timedelta(days=2), type="Leave"),
        BlockEntry(doctor="S2", date=start + timedelta(days=5),
                   end_date=start + timedelta(days=8), type="Leave"),
        BlockEntry(doctor="C3", date=start + timedelta(days=9),
                   end_date=start + timedelta(days=10), type="Leave"),
        BlockEntry(doctor="J4", date=start + timedelta(days=11),
                   end_date=None, type="No on-call"),
    ]

    return SessionState(
        horizon=Horizon(start_date=start, n_days=14,
                        public_holidays=[holiday]),
        doctors=doctors, stations=stations, blocks=blocks,
    )


# ------------------------------------------------------------- Scenario 3

def nursing_ward() -> SessionState:
    """Nursing ward roster: tier labels renamed, ward-flavoured stations,
    14-day horizon. Shows the same engine applies to nursing rosters as long
    as the three-tier / sub-spec shape fits the workforce."""
    doctors: list[DoctorEntry] = []

    staff_nurses = [f"Nurse {chr(65 + i)}" for i in range(8)]  # A-H
    senior_nurses = [f"RN {chr(65 + i)}" for i in range(5)]     # A-E
    managers = [
        ("Ward Mgr 1", "Medical"),
        ("Ward Mgr 2", "Medical"),
        ("Ward Mgr 3", "Surgical"),
        ("Ward Mgr 4", "Surgical"),
    ]

    nurse_stations = [
        "WARD_MED_A", "WARD_MED_B", "WARD_SURG_A", "WARD_SURG_B", "TRIAGE",
    ]
    for n in staff_nurses:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=nurse_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in senior_nurses:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=nurse_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in managers:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=nurse_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    stations = [
        StationEntry(name="WARD_MED_A", sessions=["AM", "PM"],
                     required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"],
                     is_reporting=False),
        StationEntry(name="WARD_MED_B", sessions=["AM", "PM"],
                     required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"],
                     is_reporting=False),
        StationEntry(name="WARD_SURG_A", sessions=["AM", "PM"],
                     required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"],
                     is_reporting=False),
        StationEntry(name="WARD_SURG_B", sessions=["AM", "PM"],
                     required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"],
                     is_reporting=False),
        StationEntry(name="TRIAGE", sessions=["AM", "PM"],
                     required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"],
                     is_reporting=False),
    ]

    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=14, public_holidays=[]),
        doctors=doctors, stations=stations,
        tier_labels=TierLabels(
            junior="Staff Nurse",
            senior="Senior Nurse",
            consultant="Ward Manager",
        ),
    )


# ---------------------------------------------------- larger radiology

def _big_radiology_stations() -> list[StationEntry]:
    """Station set sized for a 30-doctor radiology department.

    Tuned so weekday AM demand ≈ 14 and PM demand ≈ 14 (28
    station-sessions/weekday). With 2 on-call nights per weekday and
    ~30 doctors available (minus post-call rest), utilisation lands
    near 90% and the solver can satisfy H11 (every doctor on duty
    every weekday) on most days. The 15-doctor `radiology_small`
    setup had ~half this demand, which left too many idle doctors."""
    return [
        StationEntry(name="CT", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="MR", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="US", sessions=["AM", "PM"], required_per_session=3,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="XR_REPORT", sessions=["AM", "PM"], required_per_session=3,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=True),
        StationEntry(name="IR", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="FLUORO", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="GEN_AM", sessions=["AM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="GEN_PM", sessions=["PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
    ]


def _std_radiology_doctors(size: int) -> list[DoctorEntry]:
    """30-ish radiology department: 8 juniors, 6 seniors, rest consultants
    split across 3 subspecs. `size` must be ≥ 17 to cover weekend H8.
    """
    juniors = [f"J{i+1:02d}" for i in range(8)]
    seniors = [f"S{i+1:02d}" for i in range(6)]
    n_consultants = max(size - 14, 6)
    subspecs = ["Neuro", "Body", "MSK"]
    consultants = [
        (f"C{i+1:02d}", subspecs[i % 3]) for i in range(n_consultants)
    ]
    doctors: list[DoctorEntry] = []
    for n in juniors:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "IR", "FLUORO"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    return doctors


def teaching_hospital_week() -> SessionState:
    """Teaching hospital radiology department — 30 doctors × 1 week.

    Bigger team than `radiology_small`: 8 juniors + 6 seniors + 16
    consultants across three subspecs. Station demand scaled to match
    the team size so weekday utilisation stays high. A small amount
    of leave and one preferred-shift request keeps things realistic."""
    doctors = _std_radiology_doctors(size=30)
    stations = _big_radiology_stations()

    start = _monday()
    blocks = [
        BlockEntry(doctor="J01", date=start + timedelta(days=2), type="Leave"),
        BlockEntry(doctor="S02", date=start + timedelta(days=4),
                   end_date=start + timedelta(days=5), type="Leave"),
        BlockEntry(doctor="C03", date=start + timedelta(days=1), type="Leave"),
        BlockEntry(doctor="J05", date=start + timedelta(days=3), type="No on-call"),
        BlockEntry(doctor="S04", date=start + timedelta(days=2), type="Prefer AM"),
    ]

    return SessionState(
        horizon=Horizon(start_date=start, n_days=7, public_holidays=[]),
        doctors=doctors, stations=stations, blocks=blocks,
    )


def regional_hospital_month() -> SessionState:
    """Regional hospital — 30 doctors × 4 weeks.

    Full month horizon over the same 30-doctor team. Mixed leave,
    call blocks, preferences, one public holiday, one part-time
    doctor (0.5 FTE) and one max-oncall cap. The broadest scenario
    for fairness / coverage stress-testing, especially on
    `/lab/fairness`'s per-individual Δ view."""
    doctors = _std_radiology_doctors(size=30)
    stations = _big_radiology_stations()

    # Inject one part-time doctor + one max-oncall cap so the fairness
    # panel has something interesting to show over the 4-week horizon.
    doctors[0] = doctors[0].model_copy(update={"fte": 0.5})
    doctors[8] = doctors[8].model_copy(update={"max_oncalls": 3})

    start = _monday()
    public_holiday = start + timedelta(days=10)
    blocks = [
        BlockEntry(doctor="J02", date=start + timedelta(days=3),
                   end_date=start + timedelta(days=6), type="Leave"),
        BlockEntry(doctor="S03", date=start + timedelta(days=12),
                   end_date=start + timedelta(days=14), type="Leave"),
        BlockEntry(doctor="C05", date=start + timedelta(days=18),
                   end_date=start + timedelta(days=22), type="Leave"),
        BlockEntry(doctor="J04", date=start + timedelta(days=8),
                   end_date=start + timedelta(days=9), type="Leave"),
        BlockEntry(doctor="C10", date=start + timedelta(days=24), type="Leave"),
        BlockEntry(doctor="J06", date=start + timedelta(days=7), type="No on-call"),
        BlockEntry(doctor="S05", date=start + timedelta(days=15), type="No AM"),
        BlockEntry(doctor="C12", date=start + timedelta(days=20), type="No PM"),
        BlockEntry(doctor="J03", date=start + timedelta(days=2), type="Prefer AM"),
        BlockEntry(doctor="J07", date=start + timedelta(days=11), type="Prefer PM"),
        BlockEntry(doctor="S02", date=start + timedelta(days=5), type="Prefer AM"),
        BlockEntry(doctor="C01", date=start + timedelta(days=14), type="Prefer AM"),
    ]

    return SessionState(
        horizon=Horizon(start_date=start, n_days=28,
                        public_holidays=[public_holiday]),
        doctors=doctors, stations=stations, blocks=blocks,
    )


# ---------------------------------------------------- clinic (small team)

def clinic_week() -> SessionState:
    """Small outpatient clinic — 10 doctors × 1 week.

    Minimal headcount: 4 juniors, 3 seniors, 3 consultants (1 per
    subspec). Trimmed station list: US / XR_REPORT / GEN_AM / GEN_PM
    only. A real outpatient clinic doesn't run overnight or weekend
    cover, so H8 (weekend coverage) and the weekday on-call rule
    are both disabled — the clinic is a Mon–Fri daytime operation.
    Demonstrates how toggling constraints narrows the problem shape.
    """
    doctors: list[DoctorEntry] = []
    for name in ["J1", "J2", "J3", "J4"]:
        doctors.append(DoctorEntry(
            name=name, tier="junior",
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for name in ["S1", "S2", "S3"]:
        doctors.append(DoctorEntry(
            name=name, tier="senior",
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for name, ss in [("C1", "Neuro"), ("C2", "Body"), ("C3", "MSK")]:
        doctors.append(DoctorEntry(
            name=name, tier="consultant",
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    # Weekday AM demand = 1+1+1 = 3, PM = 1+1+1 = 3. No weekend or
    # oncall. 10 doctors × 5 weekdays = 50 slots, demand 30 = 20
    # idle-weekday slots, which H11 penalises at 100 per slot → the
    # objective score reflects that consultants often don't work every
    # weekday at a clinic.
    stations = [
        StationEntry(name="US", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="XR_REPORT", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=True),
        StationEntry(name="GEN_AM", sessions=["AM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="GEN_PM", sessions=["PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
    ]

    # Weekday-only clinic: no on-call types at all (disables both weekend
    # H8 and weekday on-call coverage in one go). The Phase B equivalent
    # of the legacy `h8_enabled=False, weekday_oncall_coverage=False`
    # combo is simply an empty `on_call_types` list — the scenario-level
    # `_apply_preset` honours that explicit choice.
    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=7, public_holidays=[]),
        doctors=doctors, stations=stations,
        on_call_types=[],
    )


# ------------------------------------------------- very-large hospital

def hospital_long_month() -> SessionState:
    """Large radiology + reporting department — 35 doctors × 4 weeks.

    The biggest bundled scenario: 10 juniors, 7 seniors, 18
    consultants across three subspecs. Stations scaled up from the
    30-doctor set so utilisation stays realistic. Two public
    holidays, leave blocks in every week, and two part-time doctors
    to stress FTE-normalisation on the fairness panel.

    Solves more slowly than the others; treat it as the
    'how far can you push this' scenario rather than a smoke test."""
    juniors = [f"J{i+1:02d}" for i in range(10)]
    seniors = [f"S{i+1:02d}" for i in range(7)]
    subspecs = ["Neuro", "Body", "MSK"]
    consultants = [(f"C{i+1:02d}", subspecs[i % 3]) for i in range(18)]

    doctors: list[DoctorEntry] = []
    for n in juniors:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "IR", "FLUORO"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    # Two part-timers.
    doctors[0] = doctors[0].model_copy(update={"fte": 0.5})
    doctors[5] = doctors[5].model_copy(update={"fte": 0.75})

    # Bigger station set — weekday demand ≈ 17 AM + 17 PM = 34 slots
    # against 35 × 5 = 175 weekday doctor-slots minus oncall/post-call.
    stations = [
        StationEntry(name="CT", sessions=["AM", "PM"], required_per_session=3,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="MR", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="US", sessions=["AM", "PM"], required_per_session=4,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="XR_REPORT", sessions=["AM", "PM"], required_per_session=3,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=True),
        StationEntry(name="IR", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="FLUORO", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="GEN_AM", sessions=["AM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="GEN_PM", sessions=["PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
    ]

    start = _monday()
    public_holidays = [start + timedelta(days=5), start + timedelta(days=19)]
    blocks = [
        BlockEntry(doctor="J02", date=start + timedelta(days=2),
                   end_date=start + timedelta(days=3), type="Leave"),
        BlockEntry(doctor="S04", date=start + timedelta(days=9),
                   end_date=start + timedelta(days=11), type="Leave"),
        BlockEntry(doctor="C08", date=start + timedelta(days=15),
                   end_date=start + timedelta(days=18), type="Leave"),
        BlockEntry(doctor="J07", date=start + timedelta(days=22),
                   end_date=start + timedelta(days=24), type="Leave"),
        BlockEntry(doctor="S02", date=start + timedelta(days=7), type="No on-call"),
        BlockEntry(doctor="C03", date=start + timedelta(days=12), type="No AM"),
        BlockEntry(doctor="J05", date=start + timedelta(days=17), type="Prefer PM"),
        BlockEntry(doctor="C12", date=start + timedelta(days=20), type="Prefer AM"),
    ]

    return SessionState(
        horizon=Horizon(start_date=start, n_days=28,
                        public_holidays=public_holidays),
        doctors=doctors, stations=stations, blocks=blocks,
    )


# ============================================================== specialties
#
# Each specialty picks station names, tier split, subspec list, and
# constraint toggles to fit the realistic shape of that department. The
# goal is to show that the solver adapts to the *shape* of the work —
# not to perfectly model the clinical detail of every sub-field.

# ---------------------------------------------------- Cardiology (1 week)

def cardiology_week() -> SessionState:
    """Cardiology department — 18 doctors × 1 week.

    Three subspecs (Invasive / Non-invasive / Electrophysiology) with one
    or two consultants each. Stations reflect the daily cardiology mix:
    cath lab, echo, outpatient clinic, ward round, plus a reporting desk
    for ECG/imaging. Juniors + seniors rotate through echo and clinic;
    cath lab is consultant-led.
    """
    juniors = [f"Reg{i+1}" for i in range(6)]
    seniors = [f"Fel{i+1}" for i in range(4)]
    consultants = [
        ("Dr Hart", "Invasive"), ("Dr Stent", "Invasive"),
        ("Dr Beat", "Non-invasive"), ("Dr Echo", "Non-invasive"),
        ("Dr Arrhy", "Electrophys"), ("Dr Pace", "Electrophys"),
        ("Dr Cor", "Invasive"), ("Dr Valve", "Non-invasive"),
    ]

    junior_stations = ["WARD", "CLINIC", "ECG_READ"]
    senior_stations = ["WARD", "CLINIC", "ECHO", "ECG_READ"]
    consultant_stations = [
        "CATH_LAB", "ECHO", "CLINIC", "WARD", "ECG_READ",
    ]

    doctors: list[DoctorEntry] = []
    for n in juniors:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=junior_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=senior_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=consultant_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    # Cath lab runs as an all-day list (Invasive consultants on a FULL_DAY
    # session). Everything else is still AM/PM half-day.
    stations = [
        StationEntry(name="CATH_LAB", sessions=["FULL_DAY"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="ECHO", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="CLINIC", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="WARD", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="ECG_READ", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=True),
    ]

    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=7, public_holidays=[]),
        doctors=doctors, stations=stations,
    )


# ---------------------------------------------------- Anaesthesia (2 weeks)

def anaesthesia_two_weeks() -> SessionState:
    """Anaesthesia department — 24 doctors × 2 weeks.

    Four consultant subspecs (General / Cardiac / Obstetric / Paediatric);
    each station restricted to the matching subspec or generally-eligible
    staff. Trainees (juniors) handle pre-op + recovery; senior registrars
    scrub in with consultants on theatre lists. Weekend EXT covers
    labour-ward cover.
    """
    juniors = [f"T{i+1}" for i in range(8)]
    seniors = [f"SR{i+1}" for i in range(6)]
    consultants = [
        ("Dr Gen1", "General"), ("Dr Gen2", "General"), ("Dr Gen3", "General"),
        ("Dr Card1", "Cardiac"), ("Dr Card2", "Cardiac"),
        ("Dr Obs1", "Obstetric"), ("Dr Obs2", "Obstetric"),
        ("Dr Paed1", "Paediatric"), ("Dr Paed2", "Paediatric"),
        ("Dr Gen4", "General"),
    ]

    junior_stations = ["PREOP", "RECOVERY", "ICU_COVER"]
    senior_stations = ["PREOP", "RECOVERY", "ICU_COVER", "OR_GENERAL", "OBSTETRIC"]
    consultant_stations = ["OR_GENERAL", "OR_CARDIAC", "OR_PAEDS", "OBSTETRIC", "ICU_COVER"]

    doctors: list[DoctorEntry] = []
    for n in juniors:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=junior_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=senior_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=consultant_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    # Theatre lists are FULL_DAY — anaesthetists hold a whole list. OR_GENERAL
    # keeps AM/PM so pre-op and recovery can rotate staff through half-sessions
    # (two different anaesthetists can cover the two halves of a general list).
    stations = [
        StationEntry(name="OR_GENERAL", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="OR_CARDIAC", sessions=["FULL_DAY"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="OR_PAEDS", sessions=["FULL_DAY"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="OBSTETRIC", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="PREOP", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="RECOVERY", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="ICU_COVER", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
    ]

    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=14, public_holidays=[]),
        doctors=doctors, stations=stations,
    )


# ---------------------------------------------------- ICU / Critical Care (2 weeks)

def icu_two_weeks() -> SessionState:
    """ICU / critical care — 16 doctors × 2 weeks.

    Smaller team with 24/7 cover. Single subspec (General ICU) because
    most ICUs aren't subspecialised. Station structure: bedside rounds
    (AM), post-round review (PM), and a senior-led admissions station.
    Heavy on-call reliance — `max_oncalls = 4` per doctor so the rota
    spreads fatigue evenly over the fortnight.
    """
    juniors = [f"ICU-R{i+1}" for i in range(6)]
    # 5 seniors (was 4 pre-Phase-B): the per-OnCallType H4 1-in-3 cap +
    # H9 weekend lieu day requires a slightly bigger senior bench than
    # the legacy fixture had.
    seniors = [f"ICU-F{i+1}" for i in range(5)]
    consultants = [
        ("Dr Crit1", "ICU"), ("Dr Crit2", "ICU"),
        ("Dr Crit3", "ICU"), ("Dr Crit4", "ICU"),
        ("Dr Crit5", "ICU"), ("Dr Crit6", "ICU"),
    ]

    stations_all = ["ROUNDS_A", "ROUNDS_B", "ADMISSIONS", "FAMILY_MTG"]

    doctors: list[DoctorEntry] = []
    for n in juniors:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=stations_all,
            prev_workload=0, fte=1.0, max_oncalls=4,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=stations_all,
            prev_workload=0, fte=1.0, max_oncalls=4,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=stations_all,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    stations = [
        StationEntry(name="ROUNDS_A", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="ROUNDS_B", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="ADMISSIONS", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="FAMILY_MTG", sessions=["PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
    ]

    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=14, public_holidays=[]),
        doctors=doctors, stations=stations,
    )


# ---------------------------------------------------- Emergency (1 week)

def emergency_week() -> SessionState:
    """Emergency department — 26 doctors × 1 week.

    ED runs a natural AM/PM/night pattern: AM = day shift, PM = evening
    shift, on-call = night shift. Heavier weekend EXT + oncall demand.
    One subspec (Trauma lead) so weekend H8 has a consultant per
    subspec.
    """
    juniors = [f"SHO{i+1}" for i in range(10)]
    seniors = [f"ED-R{i+1}" for i in range(8)]
    consultants = [
        ("Dr ED1", "General"), ("Dr ED2", "General"),
        ("Dr ED3", "General"), ("Dr ED4", "General"),
        ("Dr Traum1", "Trauma"), ("Dr Traum2", "Trauma"),
        ("Dr ED5", "General"), ("Dr Traum3", "Trauma"),
    ]

    stations_all = ["MAJORS", "MINORS", "RESUS", "TRIAGE", "PAEDS_ED"]

    doctors: list[DoctorEntry] = []
    for n in juniors:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=stations_all,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=stations_all,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=stations_all,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    stations = [
        StationEntry(name="MAJORS", sessions=["AM", "PM"], required_per_session=3,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="MINORS", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="RESUS", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="TRIAGE", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="PAEDS_ED", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
    ]

    # ED runs weekend cover like a weekday — the `shift_24_7` preset
    # applied by `_apply_preset` flips every station's `weekend_enabled`
    # to True, so we don't need to override constraints here.
    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=7, public_holidays=[]),
        doctors=doctors, stations=stations,
    )


# ---------------------------------------------------- Surgery (1 week)

def surgery_week() -> SessionState:
    """General Surgery — 16 doctors × 1 week.

    Three consultant surgeons run all-day OR lists (FULL_DAY stations:
    OR_MAIN, OR_DAY_CASE, OR_EMERGENCY). Registrars scrub in on a
    SR_THEATRE station (AM/PM) when they're not on ward round, and
    juniors cover clinics + post-op ward rounds in AM/PM. This is the
    first bundled scenario that exercises the FULL_DAY session shape.
    """
    juniors = [f"FY{i+1}" for i in range(6)]
    seniors = [f"SpR{i+1}" for i in range(4)]
    consultants = [
        ("Mr Cutler", "General"), ("Mr Keyhole", "General"),
        ("Ms Mend", "General"), ("Mr Ortho", "Orthopaedic"),
        ("Ms Ortho", "Orthopaedic"), ("Mr Vasc", "Vascular"),
    ]

    junior_stations = ["WARD_ROUND", "CLINIC", "POSTOP"]
    senior_stations = [
        "WARD_ROUND", "CLINIC", "POSTOP", "SR_THEATRE", "EMERGENCY",
    ]
    consultant_stations = [
        "OR_MAIN", "OR_DAY_CASE", "OR_EMERGENCY", "CLINIC", "WARD_ROUND",
    ]

    doctors: list[DoctorEntry] = []
    for n in juniors:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=junior_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=senior_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=consultant_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    stations = [
        # Full-day theatre lists — consultant holds both halves.
        StationEntry(name="OR_MAIN", sessions=["FULL_DAY"],
                     required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="OR_DAY_CASE", sessions=["FULL_DAY"],
                     required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="OR_EMERGENCY", sessions=["FULL_DAY"],
                     required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        # Registrar theatre cover — AM/PM half-sessions.
        StationEntry(name="SR_THEATRE", sessions=["AM", "PM"],
                     required_per_session=1,
                     eligible_tiers=["senior"], is_reporting=False),
        StationEntry(name="EMERGENCY", sessions=["AM", "PM"],
                     required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        # Mixed-tier: clinics, ward rounds, post-op.
        StationEntry(name="CLINIC", sessions=["AM", "PM"],
                     required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="WARD_ROUND", sessions=["AM", "PM"],
                     required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="POSTOP", sessions=["AM", "PM"],
                     required_per_session=1,
                     eligible_tiers=["junior", "senior"], is_reporting=False),
    ]

    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=7, public_holidays=[]),
        doctors=doctors, stations=stations,
    )


# ---------------------------------------------------- Paediatrics (2 weeks)

def paediatrics_two_weeks() -> SessionState:
    """Paediatrics — 20 doctors × 2 weeks.

    Two consultant subspecs (General paeds / Neonatology). NICU
    stations are neonatology-led and only consultants in that subspec
    are eligible — the solver has to respect that when it fills weekend
    coverage and weekly station demand.
    """
    juniors = [f"ST{i+1}" for i in range(7)]
    seniors = [f"PEM-R{i+1}" for i in range(5)]
    consultants = [
        ("Dr Tots1", "General"), ("Dr Tots2", "General"),
        ("Dr Tots3", "General"), ("Dr Tots4", "General"),
        ("Dr Neo1", "Neonatal"), ("Dr Neo2", "Neonatal"),
        ("Dr Neo3", "Neonatal"), ("Dr Tots5", "General"),
    ]

    junior_stations = ["GEN_WARD", "OUTPATIENTS", "NICU_COVER"]
    senior_stations = ["GEN_WARD", "OUTPATIENTS", "NICU_COVER", "HDU"]
    consultant_stations = ["GEN_WARD", "OUTPATIENTS", "NICU_LEAD", "HDU"]

    doctors: list[DoctorEntry] = []
    for n in juniors:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=junior_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=senior_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=consultant_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    stations = [
        StationEntry(name="GEN_WARD", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="OUTPATIENTS", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="HDU", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        # NICU lead: consultant-only. NICU cover: more junior-friendly.
        StationEntry(name="NICU_LEAD", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="NICU_COVER", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
    ]

    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=14, public_holidays=[]),
        doctors=doctors, stations=stations,
    )


# ============================================================== research
#
# Reproducible benchmark-shaped scenarios. Plain-vanilla default stations,
# no leave, no overrides, no holidays — the least-surprising inputs for
# cross-solver / cross-paper comparisons. Mark-them as `research` in the
# manifest so the UI groups them separately from day-to-day templates.

def _benchmark_doctors(
    n_juniors: int,
    n_seniors: int,
    n_consultants: int,
    *,
    stations: list[StationEntry],
) -> list[DoctorEntry]:
    """Build a balanced doctor set whose eligibility only references
    stations that actually exist in `stations`. Without this clamp the
    Instance builder raises on `unknown stations in eligibility`."""
    available = {s.name for s in stations}

    def _keep(names: list[str]) -> list[str]:
        return [n for n in names if n in available]

    junior_pool = _keep(["US", "XR_REPORT", "GEN_AM", "GEN_PM"])
    senior_pool = _keep(["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"])
    consultant_pool = _keep(["CT", "MR", "US", "XR_REPORT", "IR", "FLUORO"])

    out: list[DoctorEntry] = []
    for i in range(n_juniors):
        out.append(DoctorEntry(
            name=f"J{i+1:02d}", tier="junior",
            eligible_stations=junior_pool,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for i in range(n_seniors):
        out.append(DoctorEntry(
            name=f"S{i+1:02d}", tier="senior",
            eligible_stations=senior_pool,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for i in range(n_consultants):
        out.append(DoctorEntry(
            name=f"C{i+1:02d}", tier="consultant",
            eligible_stations=consultant_pool,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    return out


def _benchmark_stations_small() -> list[StationEntry]:
    """Demand tuned for 10-doctor benchmark: ~5 AM + 5 PM slots/weekday.
    Idle-weekday penalty is still on (H11), but with only 10 doctors
    available and ~5 slots per session we leave a chunk idle on purpose —
    that's what benchmark instances look like in the literature."""
    return [
        StationEntry(name="US", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="XR_REPORT", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=True),
        StationEntry(name="CT", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="IR", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="GEN_AM", sessions=["AM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="GEN_PM", sessions=["PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
    ]


def _benchmark_stations_medium() -> list[StationEntry]:
    """Demand tuned for ~20 doctors: ~10 AM + 10 PM slots/weekday."""
    return [
        StationEntry(name="US", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="XR_REPORT", sessions=["AM", "PM"], required_per_session=2,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=True),
        StationEntry(name="CT", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="MR", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["senior", "consultant"], is_reporting=False),
        StationEntry(name="IR", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="FLUORO", sessions=["AM", "PM"], required_per_session=1,
                     eligible_tiers=["consultant"], is_reporting=False),
        StationEntry(name="GEN_AM", sessions=["AM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
        StationEntry(name="GEN_PM", sessions=["PM"], required_per_session=1,
                     eligible_tiers=["junior", "senior", "consultant"], is_reporting=False),
    ]


def benchmark_nrp_small() -> SessionState:
    """NRP reference instance — small (11 doctors × 14 days).

    Clean-room setup: default stations, no leave, no holidays. Matches
    the shape of the instances `/lab/scaling` uses for its synthetic
    grid, so results are directly comparable across the two surfaces.

    Tier mix: 4 juniors, 4 seniors, 3 consultants (one per subspec).
    The fourth senior is required: H4 (1-in-3 on-call) + H5 (post-call
    off) over 14 days plus weekday on-call coverage forces at least 4
    distinct seniors to rotate through nights without clashing.
    """
    stations = _benchmark_stations_small()
    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=14, public_holidays=[]),
        doctors=_benchmark_doctors(
            n_juniors=4, n_seniors=4, n_consultants=3, stations=stations,
        ),
        stations=stations,
    )


# ============================================================== stress-test
#
# These are intentionally hard: either borderline-infeasible or too big
# to solve to optimal inside the usual 30 s budget. Their point is to
# show users where the solver's limits are, not to produce a clean
# roster. The UI labels them `stress` so nobody expects an instant
# OPTIMAL.

def stress_tight_oncall() -> SessionState:
    """Tight on-call staffing — 12 doctors × 4 weeks.

    Four weeks of 1-in-3 on-call with a small senior bench. Most seniors
    will hit their H4 cap; the solver spends real wall-time hunting for
    a distribution that satisfies every weekday on-call day without
    violating post-call rules. Often stops at FEASIBLE rather than
    OPTIMAL.
    """
    stations = _benchmark_stations_small()
    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=28, public_holidays=[]),
        doctors=_benchmark_doctors(
            n_juniors=4, n_seniors=4, n_consultants=4, stations=stations,
        ),
        stations=stations,
    )


def stress_dense_leave() -> SessionState:
    """Dense leave across a crowded fortnight — 18 doctors × 14 days.

    Same footprint as `busy_month_with_leave` but with twice the leave
    volume and two public holidays inside the same horizon. Useful for
    demonstrating what happens when coverage-pressure is high but not
    catastrophic — the solver usually lands somewhere between FEASIBLE
    and UNKNOWN inside 30 s.
    """
    # Reuse the busy-month tier split / station shape.
    juniors = [f"J{i+1}" for i in range(7)]
    seniors = [f"S{i+1}" for i in range(5)]
    consultants = [
        ("C1", "Neuro"), ("C2", "Neuro"),
        ("C3", "Body"), ("C4", "Body"),
        ("C5", "MSK"), ("C6", "MSK"),
    ]
    doctors: list[DoctorEntry] = []
    for n in juniors:
        doctors.append(DoctorEntry(
            name=n, tier="junior",
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior",
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant",
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "IR", "FLUORO"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    stations = radiology_small().stations
    start = _monday()
    holidays = [start + timedelta(days=3), start + timedelta(days=10)]
    blocks = [
        BlockEntry(doctor="J1", date=start + timedelta(days=1),
                   end_date=start + timedelta(days=4), type="Leave"),
        BlockEntry(doctor="J3", date=start + timedelta(days=6),
                   end_date=start + timedelta(days=9), type="Leave"),
        BlockEntry(doctor="S1", date=start + timedelta(days=2),
                   end_date=start + timedelta(days=5), type="Leave"),
        BlockEntry(doctor="S4", date=start + timedelta(days=8),
                   end_date=start + timedelta(days=11), type="Leave"),
        BlockEntry(doctor="C3", date=start + timedelta(days=0),
                   end_date=start + timedelta(days=2), type="Leave"),
        BlockEntry(doctor="C5", date=start + timedelta(days=12),
                   end_date=start + timedelta(days=13), type="Leave"),
        BlockEntry(doctor="J5", date=start + timedelta(days=7),
                   type="No on-call"),
        BlockEntry(doctor="S2", date=start + timedelta(days=9),
                   type="No on-call"),
    ]

    return SessionState(
        horizon=Horizon(start_date=start, n_days=14, public_holidays=holidays),
        doctors=doctors, stations=stations, blocks=blocks,
    )


def benchmark_nrp_medium() -> SessionState:
    """NRP reference instance — medium (20 doctors × 28 days).

    Four-week horizon, 8-station default set, balanced tier mix. The
    prototypical mid-sized NRP problem in our YAML dialect. Intended
    for publishing a `CP-SAT vs greedy` gap on a stable, well-defined
    shape rather than a clinical one-off.
    """
    stations = _benchmark_stations_medium()
    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=28, public_holidays=[]),
        doctors=_benchmark_doctors(
            n_juniors=7, n_seniors=4, n_consultants=9, stations=stations,
        ),
        stations=stations,
    )


# -------------------------------------------------------------- Generator

Category = str  # "quickstart" | "specialty" | "realistic" | "research"


@dataclass(frozen=True)
class ScenarioDef:
    title: str
    description: str
    builder: Callable[[], SessionState]
    category: Category
    tags: tuple[str, ...] = ()
    preset: RotaPresetKey = "clinic"


SCENARIOS: dict[str, ScenarioDef] = {
    # ---- Quickstart (small, fast, demo-friendly) ------------------------
    "clinic_week": ScenarioDef(
        title="Outpatient clinic — 1 week",
        description=(
            "Small 10-person team: 4 juniors, 3 seniors, 3 consultants. "
            "Trimmed station list (US / XR_REPORT / GEN_AM / GEN_PM only). "
            "Good for seeing the tool's behaviour on a tight workforce."
        ),
        builder=clinic_week,
        category="quickstart",
        tags=("10 people", "weekday-only"),
        preset="clinic",
    ),
    "radiology_small": ScenarioDef(
        title="Radiology — 1 week",
        description=(
            "15 doctors across junior / senior / consultant. Clean slate. "
            "Solves to OPTIMAL in seconds — great smoke test."
        ),
        builder=radiology_small,
        category="quickstart",
        tags=("15 people", "fastest"),
        preset="clinic",
    ),
    # ---- Specialty scenarios --------------------------------------------
    "cardiology_week": ScenarioDef(
        title="Cardiology — 1 week",
        description=(
            "18 cardiologists with Invasive / Non-invasive / "
            "Electrophysiology subspecs. Cath lab runs as a FULL_DAY "
            "consultant list; echo is senior+; clinic + ward rounds "
            "are mixed-tier."
        ),
        builder=cardiology_week,
        category="specialty",
        tags=("cardiology", "FULL_DAY", "3 subspecs"),
        preset="clinic",
    ),
    "anaesthesia_two_weeks": ScenarioDef(
        title="Anaesthesia — 2 weeks (FULL_DAY theatre lists)",
        description=(
            "24 anaesthetists across General / Cardiac / Obstetric / "
            "Paediatric subspecs. Cardiac and paediatric theatre lists "
            "are FULL_DAY; general theatre + obstetric stay AM/PM."
        ),
        builder=anaesthesia_two_weeks,
        category="specialty",
        tags=("anaesthesia", "FULL_DAY", "4 subspecs"),
        preset="surgical",
    ),
    "icu_two_weeks": ScenarioDef(
        title="ICU / Critical Care — 2 weeks (12h shifts)",
        description=(
            "16-doctor critical-care unit on a 12h day/night pattern. "
            "Single subspec, max 4 on-calls per doctor over the "
            "fortnight so the fatigue load spreads evenly."
        ),
        builder=icu_two_weeks,
        category="specialty",
        tags=("icu", "12h shifts", "max_oncalls"),
        preset="day_night_12h",
    ),
    "emergency_week": ScenarioDef(
        title="Emergency Department — 1 week (24/7 shifts)",
        description=(
            "26 ED doctors on a 24/7 early / late / night shift pattern "
            "with weekend cover enabled. Trauma-lead subspec for "
            "weekend H8 compliance."
        ),
        builder=emergency_week,
        category="specialty",
        tags=("emergency", "24/7 shifts", "weekend on"),
        preset="shift_24_7",
    ),
    "paediatrics_two_weeks": ScenarioDef(
        title="Paediatrics — 2 weeks",
        description=(
            "20 paediatricians with General / Neonatal subspecs. NICU "
            "lead station is neonatology-only — solver has to respect "
            "the subspec restriction during weekend H8."
        ),
        builder=paediatrics_two_weeks,
        category="specialty",
        tags=("paediatrics", "NICU"),
        preset="clinic",
    ),
    "surgery_week": ScenarioDef(
        title="General Surgery — 1 week (FULL_DAY OR lists)",
        description=(
            "16 doctors. Three consultant OR lists run as FULL_DAY "
            "stations — exercises the all-day session shape. Registrars "
            "+ juniors still split AM/PM on clinic, ward round, and "
            "post-op."
        ),
        builder=surgery_week,
        category="specialty",
        tags=("surgery", "FULL_DAY", "OR lists"),
        preset="surgical",
    ),
    "nursing_ward": ScenarioDef(
        title="Nursing ward — 2 weeks (12h shifts)",
        description=(
            "17 nurses across ward / senior / manager tiers with Medical "
            "and Surgical sub-wards on a 12h day/night pattern."
        ),
        builder=nursing_ward,
        category="specialty",
        tags=("nursing", "12h shifts", "renamed tiers"),
        preset="day_night_12h",
    ),
    # ---- Realistic / stress-test ----------------------------------------
    "busy_month_with_leave": ScenarioDef(
        title="Busy hospital — 2 weeks with leave",
        description=(
            "22 doctors, a public holiday, and a handful of leave blocks. "
            "Realistic mid-sized problem; shows how leave affects coverage."
        ),
        builder=busy_month_with_leave,
        category="realistic",
        tags=("leave", "public holiday"),
        preset="clinic",
    ),
    "teaching_hospital_week": ScenarioDef(
        title="Teaching hospital — 1 week",
        description=(
            "Larger 30-doctor radiology department. Station demand scaled "
            "to match team size so weekday utilisation stays high. Small "
            "amount of leave + one preferred-shift request."
        ),
        builder=teaching_hospital_week,
        category="realistic",
        tags=("30 doctors", "preferences"),
        preset="clinic",
    ),
    "regional_hospital_month": ScenarioDef(
        title="Regional hospital — 4 weeks",
        description=(
            "Full month horizon over a 30-doctor team. One part-timer "
            "(0.5 FTE), one max-oncall cap, one public holiday, mixed "
            "leave + call blocks + soft preferences. Best scenario for "
            "stress-testing /lab/fairness's per-individual Δ view."
        ),
        builder=regional_hospital_month,
        category="realistic",
        tags=("4 weeks", "FTE", "fairness stress"),
        preset="clinic",
    ),
    "hospital_long_month": ScenarioDef(
        title="Large hospital — 4 weeks",
        description=(
            "Biggest day-to-day scenario: 35 doctors (10/7/18), 8 stations "
            "scaled up, two public holidays, leave in every week, two "
            "part-time doctors (0.5 + 0.75 FTE). Solves more slowly — "
            "treat as 'how far can you push this'."
        ),
        builder=hospital_long_month,
        category="realistic",
        tags=("35 doctors", "4 weeks", "largest"),
        preset="clinic",
    ),
    # ---- Research / benchmark references --------------------------------
    "benchmark_nrp_small": ScenarioDef(
        title="Benchmark · NRP small (11×14)",
        description=(
            "Clean-room reference instance: 11 doctors × 14 days, default "
            "stations, no leave / no holidays / no overrides. Reproducible "
            "baseline for CP-SAT vs greedy comparisons and /lab/scaling."
        ),
        builder=benchmark_nrp_small,
        category="research",
        tags=("benchmark", "NRP", "reproducible"),
        preset="clinic",
    ),
    "benchmark_nrp_medium": ScenarioDef(
        title="Benchmark · NRP medium (20×28)",
        description=(
            "Mid-sized reference: 20 doctors × 28 days with the standard "
            "8-station set. Clean inputs for publishing CP-SAT vs greedy "
            "gaps at a non-trivial problem size."
        ),
        builder=benchmark_nrp_medium,
        category="research",
        tags=("benchmark", "NRP", "mid-sized"),
        preset="clinic",
    ),
    # ---- Stress-test (deliberately hard) --------------------------------
    "stress_tight_oncall": ScenarioDef(
        title="Stress · Tight on-call bench",
        description=(
            "12 doctors × 4 weeks with a thin senior bench. H4 + H5 + "
            "weekday on-call coverage push the solver to its limits — "
            "expect FEASIBLE rather than OPTIMAL inside 30 s."
        ),
        builder=stress_tight_oncall,
        category="research",
        tags=("stress", "hard", "oncall pressure"),
        preset="clinic",
    ),
    "stress_dense_leave": ScenarioDef(
        title="Stress · Dense leave + holidays",
        description=(
            "18 doctors × 14 days with heavy overlapping leave and two "
            "public holidays. Shows what happens when a coordinator "
            "tries to schedule through a holiday-and-leave crunch."
        ),
        builder=stress_dense_leave,
        category="research",
        tags=("stress", "leave", "holidays"),
        preset="clinic",
    ),
}


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "configs" / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []

    for scenario_id, sdef in SCENARIOS.items():
        state = sdef.builder()
        # Stamp the scenario's rota preset onto the state — this is what
        # gives each template realistic shift labels + hours + weekend
        # coverage toggles. Scenarios that pre-set a weekend-coverage
        # constraint (e.g. emergency_week) keep their explicit choice;
        # see `_apply_preset`.
        state = _apply_preset(state, sdef.preset)
        # Bias scenarios toward a shorter solver budget so they always
        # produce a result inside typical cloud-proxy WebSocket timeouts.
        state = state.model_copy(
            update={"solver": state.solver.model_copy(update={"time_limit": 30})}
        )
        inst = session_to_instance(state)
        weights, wl, cfg = session_to_solver_configs(state)
        n_doctors = len(state.doctors)
        n_stations = len(state.stations)
        n_days = state.horizon.n_days
        print(f"[{scenario_id}] Solving {n_doctors}×{n_days} — {sdef.title} …")
        result = solve(
            inst,
            time_limit_s=30,
            weights=weights,
            workload_weights=wl,
            constraints=cfg,
            num_workers=4,
            feasibility_only=False,
        )
        # Don't gate on feasibility. Hard / stress-test scenarios are
        # useful even when they don't solve cleanly inside 30s — they
        # show users (and reviewers) where the solver's limits are.
        # Record the status so the UI can badge each template honestly.
        print(
            f"  → {result.status} in {result.wall_time_s:.1f}s, "
            f"objective={result.objective}"
        )

        # Classify difficulty from the 30s build-time solve. The values
        # are a pragmatic label for the UI, not a promise: a user running
        # the scenario on their own machine with a bigger time budget
        # may reach OPTIMAL on any of these.
        if result.status == "OPTIMAL":
            difficulty = "easy"
        elif result.status == "FEASIBLE" and result.wall_time_s < 5:
            difficulty = "easy"
        elif result.status == "FEASIBLE":
            difficulty = "hard"
        else:
            difficulty = "stress"

        yaml_text = dump_state(session_to_v1_dict(state))
        (out_dir / f"{scenario_id}.yaml").write_text(yaml_text)
        manifest.append({
            "id": scenario_id,
            "title": sdef.title,
            "description": sdef.description,
            "category": sdef.category,
            "tags": list(sdef.tags),
            "preset": sdef.preset,
            "n_doctors": n_doctors,
            "n_stations": n_stations,
            "n_days": n_days,
            "highlights": _highlights(state),
            # Observed solve behaviour at build time (30 s / 4 workers).
            "solve_status": result.status,
            "solve_time_s": round(float(result.wall_time_s), 2),
            "difficulty": difficulty,
        })

    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=False) + "\n"
    )
    print(f"\nWrote {len(manifest)} scenarios to {out_dir}")


def _highlights(state: SessionState) -> list[str]:
    tier_counts = {"junior": 0, "senior": 0, "consultant": 0}
    for d in state.doctors:
        tier_counts[d.tier] += 1
    highlights = [
        f"{len(state.doctors)} {'people' if state.tier_labels.junior != 'Junior' else 'doctors'} "
        f"({tier_counts['junior']}/{tier_counts['senior']}/{tier_counts['consultant']})",
        f"{len(state.stations)} stations",
        f"{state.horizon.n_days}-day horizon",
    ]
    if state.horizon.public_holidays:
        highlights.append(f"{len(state.horizon.public_holidays)} public holiday(s)")
    if state.blocks:
        highlights.append(f"{len(state.blocks)} leave / block entr{'y' if len(state.blocks)==1 else 'ies'}")
    if state.tier_labels.junior != "Junior":
        highlights.append(
            f"Tiers: {state.tier_labels.junior} / {state.tier_labels.senior} / {state.tier_labels.consultant}"
        )
    return highlights


if __name__ == "__main__":
    main()
