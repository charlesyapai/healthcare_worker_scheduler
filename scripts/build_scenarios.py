"""Generate the pre-built scenarios shipped with the app.

Each scenario is verified against the solver before its YAML is written.
Outputs go to configs/scenarios/<id>.yaml plus a manifest.json that lists
id, title, one-line description, and a small stat line for each.

Run from repo root:

    python scripts/build_scenarios.py
"""

from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models.session import (  # noqa: E402
    BlockEntry,
    ConstraintsConfig,
    DoctorEntry,
    Horizon,
    SessionState,
    StationEntry,
    TierLabels,
)
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
            name=n, tier="junior", subspec=None,
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in ["Dr F", "Dr G", "Dr H", "Dr I"]:
        doctors.append(DoctorEntry(
            name=n, tier="senior", subspec=None,
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in [("Dr J", "Neuro"), ("Dr K", "Neuro"),
                  ("Dr L", "Body"), ("Dr M", "Body"),
                  ("Dr N", "MSK"), ("Dr O", "MSK")]:
        doctors.append(DoctorEntry(
            name=n, tier="consultant", subspec=ss,
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
        subspecs=["Neuro", "Body", "MSK"],
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
            name=n, tier="junior", subspec=None,
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior", subspec=None,
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants_ns:
        doctors.append(DoctorEntry(
            name=n, tier="consultant", subspec=ss,
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
        subspecs=["Neuro", "Body", "MSK"],
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
            name=n, tier="junior", subspec=None,
            eligible_stations=nurse_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in senior_nurses:
        doctors.append(DoctorEntry(
            name=n, tier="senior", subspec=None,
            eligible_stations=nurse_stations,
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in managers:
        doctors.append(DoctorEntry(
            name=n, tier="consultant", subspec=ss,
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
        subspecs=["Medical", "Surgical"],
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
            name=n, tier="junior", subspec=None,
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior", subspec=None,
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant", subspec=ss,
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
        subspecs=["Neuro", "Body", "MSK"],
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
        subspecs=["Neuro", "Body", "MSK"],
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
            name=name, tier="junior", subspec=None,
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for name in ["S1", "S2", "S3"]:
        doctors.append(DoctorEntry(
            name=name, tier="senior", subspec=None,
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for name, ss in [("C1", "Neuro"), ("C2", "Body"), ("C3", "MSK")]:
        doctors.append(DoctorEntry(
            name=name, tier="consultant", subspec=ss,
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

    # Weekday-only clinic: disable weekend H8 and the weekday-on-call
    # rule. H4–H7 / H9 are still on by default but become no-ops once
    # no on-call exists.
    constraints = ConstraintsConfig(
        h8_enabled=False,
        weekday_oncall_coverage=False,
    )

    return SessionState(
        horizon=Horizon(start_date=_monday(), n_days=7, public_holidays=[]),
        doctors=doctors, stations=stations,
        subspecs=["Neuro", "Body", "MSK"],
        constraints=constraints,
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
            name=n, tier="junior", subspec=None,
            eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n in seniors:
        doctors.append(DoctorEntry(
            name=n, tier="senior", subspec=None,
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
    for n, ss in consultants:
        doctors.append(DoctorEntry(
            name=n, tier="consultant", subspec=ss,
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
        subspecs=subspecs,
    )


# -------------------------------------------------------------- Generator

SCENARIOS: dict[str, tuple[str, str, Callable[[], SessionState]]] = {
    "clinic_week": (
        "Outpatient clinic — 1 week",
        "Small 10-person team: 4 juniors, 3 seniors, 3 consultants. "
        "Trimmed station list (US / XR_REPORT / GEN_AM / GEN_PM only). "
        "Good for seeing the tool's behaviour on a tight workforce.",
        clinic_week,
    ),
    "radiology_small": (
        "Radiology department — 1 week",
        "15 doctors across junior / senior / consultant. Clean slate. "
        "Solves to OPTIMAL in seconds — great smoke test.",
        radiology_small,
    ),
    "nursing_ward": (
        "Nursing ward — 2 weeks",
        "17 nurses across ward / senior / manager tiers with Medical and "
        "Surgical sub-wards. Same engine, different vocabulary.",
        nursing_ward,
    ),
    "busy_month_with_leave": (
        "Busy hospital — 2 weeks with leave",
        "22 doctors, a public holiday, and a handful of leave blocks. "
        "Realistic mid-sized problem; shows how leave affects coverage.",
        busy_month_with_leave,
    ),
    "teaching_hospital_week": (
        "Teaching hospital — 1 week",
        "Larger 30-doctor department (8 juniors, 6 seniors, 16 "
        "consultants across 3 subspecs). Station demand scaled to match "
        "the team size so weekday utilisation stays high. Small amount "
        "of leave + one preferred-shift request.",
        teaching_hospital_week,
    ),
    "regional_hospital_month": (
        "Regional hospital — 4 weeks",
        "Full month horizon over a 30-doctor team. One part-timer "
        "(0.5 FTE), one max-oncall cap, one public holiday, mixed "
        "leave + call blocks + soft preferences. Best scenario for "
        "stress-testing /lab/fairness's per-individual Δ view.",
        regional_hospital_month,
    ),
    "hospital_long_month": (
        "Large hospital — 4 weeks",
        "Biggest bundled scenario: 35 doctors (10/7/18), 8 stations "
        "scaled up, two public holidays, leave in every week, two "
        "part-time doctors (0.5 + 0.75 FTE). Solves more slowly — "
        "treat as 'how far can you push this'.",
        hospital_long_month,
    ),
}


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "configs" / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []

    for scenario_id, (title, description, builder) in SCENARIOS.items():
        state = builder()
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
        print(f"[{scenario_id}] Solving {n_doctors}×{n_days} — {title} …")
        result = solve(
            inst,
            time_limit_s=30,
            weights=weights,
            workload_weights=wl,
            constraints=cfg,
            num_workers=4,
            feasibility_only=False,
        )
        if result.status not in ("OPTIMAL", "FEASIBLE"):
            sys.exit(f"  ✗ {scenario_id} is not feasible ({result.status}); refine before committing.")
        print(f"  → {result.status} in {result.wall_time_s:.1f}s, "
              f"objective={result.objective}")

        yaml_text = dump_state(session_to_v1_dict(state))
        (out_dir / f"{scenario_id}.yaml").write_text(yaml_text)
        manifest.append({
            "id": scenario_id,
            "title": title,
            "description": description,
            "n_doctors": n_doctors,
            "n_stations": n_stations,
            "n_days": n_days,
            "highlights": _highlights(state),
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
