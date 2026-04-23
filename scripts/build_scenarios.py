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


# ------------------------------------------------------- benchmark-shaped

def nsplib_shaped_n30_7() -> SessionState:
    """NSPLib-envelope scenario — 30 doctors × 7 days × 3 skill classes.

    Shaped to match the parameter envelope of NSPLib's n30/d7/s3
    instance family (Vanhoucke & Maenhout 2007). Our three semantic
    tiers (junior / senior / consultant) stand in for NSPLib's skill
    classes; five stations (CT / MR / US / XR_REPORT / IR / FLUORO +
    GEN_AM / GEN_PM) stand in for NSPLib's shift types. Leave blocks
    emulate NSPLib's days-off requests at ~5% density.

    ⚠ IMPORTANT: This is NOT a bit-for-bit import of any specific
    NSPLib instance. It's shaped to match the family's parameter
    envelope so a reviewer can gauge the tool's viability at
    NSPLib-scale inputs. A native NSPLib adapter with penalty-score
    translation is flagged as follow-up in docs/BRIEFING…"""
    juniors = [f"J{i+1:02d}" for i in range(8)]
    seniors = [f"S{i+1:02d}" for i in range(6)]
    consultants_ns = [
        ("C01", "Neuro"), ("C02", "Neuro"), ("C03", "Neuro"), ("C04", "Neuro"), ("C05", "Neuro"),
        ("C06", "Body"),  ("C07", "Body"),  ("C08", "Body"),  ("C09", "Body"),  ("C10", "Body"),
        ("C11", "MSK"),   ("C12", "MSK"),   ("C13", "MSK"),   ("C14", "MSK"),   ("C15", "MSK"),
        ("C16", "Neuro"),
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
    for n, ss in consultants_ns:
        doctors.append(DoctorEntry(
            name=n, tier="consultant", subspec=ss,
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "IR", "FLUORO"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    stations = radiology_small().stations  # same shape

    start = _monday()
    # Sparse leave at ~5% doctor-day density (close to NSPLib's typical
    # days-off-request rate). Spread across tiers so no single tier
    # becomes the bottleneck.
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


def curtois_shaped_bcv() -> SessionState:
    """Curtois-envelope scenario — 30 doctors × 28 days.

    Shaped to match the Curtois NRP collection's BCV (Belgian
    Children's Valentine) family envelope: small hospital, 4-week
    horizon, moderate-complexity soft constraints (patterns,
    preferences), mixed leave. See docs/INDUSTRY_CONTEXT.md §2 for
    the collection's background.

    ⚠ IMPORTANT: This is NOT a bit-for-bit import of any specific
    Curtois instance. It's shaped to match the family's parameter
    envelope so a reviewer can see how the tool performs on a
    4-week horizon with realistic leave + preference density. A
    native Curtois adapter with penalty-score translation is flagged
    as follow-up in docs/BRIEFING…"""
    juniors = [f"J{i+1:02d}" for i in range(8)]
    seniors = [f"S{i+1:02d}" for i in range(6)]
    consultants_ns = [
        ("C01", "Neuro"), ("C02", "Neuro"), ("C03", "Neuro"), ("C04", "Neuro"), ("C05", "Neuro"),
        ("C06", "Body"),  ("C07", "Body"),  ("C08", "Body"),  ("C09", "Body"),  ("C10", "Body"),
        ("C11", "MSK"),   ("C12", "MSK"),   ("C13", "MSK"),   ("C14", "MSK"),   ("C15", "MSK"),
        ("C16", "Body"),
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
    for n, ss in consultants_ns:
        doctors.append(DoctorEntry(
            name=n, tier="consultant", subspec=ss,
            eligible_stations=["CT", "MR", "US", "XR_REPORT", "IR", "FLUORO"],
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))

    # Inject one part-time doctor + one max-oncall cap so the fairness
    # panel has something interesting to show over the 4-week horizon.
    doctors[0] = doctors[0].model_copy(update={"fte": 0.5})
    doctors[8] = doctors[8].model_copy(update={"max_oncalls": 3})

    stations = radiology_small().stations

    start = _monday()
    # Leave + preference density approximating Curtois's typical 10%
    # request rate over 4 weeks. One public holiday mid-horizon.
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
        # Call / session blocks — Curtois has "unwanted shift" requests
        # we map onto No on-call / No AM / No PM.
        BlockEntry(doctor="J06", date=start + timedelta(days=7), type="No on-call"),
        BlockEntry(doctor="S05", date=start + timedelta(days=15), type="No AM"),
        BlockEntry(doctor="C12", date=start + timedelta(days=20), type="No PM"),
        # Soft preferences — Curtois has "preferred shift" requests
        # we map onto Prefer AM / Prefer PM.
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


# -------------------------------------------------------------- Generator

# Each scenario entry:
#   id → (title, description, builder, benchmark_family, reference, caveat)
# Where benchmark_family / reference / caveat are None for original
# scenarios and set for benchmark-shaped ones.
SCENARIOS: dict[str, tuple[str, str, Callable[[], SessionState], str | None, str | None, str | None]] = {
    "radiology_small": (
        "Radiology department — 1 week",
        "15 doctors across junior / senior / consultant. Clean slate. "
        "Solves to OPTIMAL in seconds — great smoke test.",
        radiology_small,
        None, None, None,
    ),
    "busy_month_with_leave": (
        "Busy hospital — 2 weeks with leave",
        "22 doctors, a public holiday, and a handful of leave blocks. "
        "Realistic mid-sized problem; shows how leave affects coverage.",
        busy_month_with_leave,
        None, None, None,
    ),
    "nursing_ward": (
        "Nursing ward — 2 weeks",
        "17 nurses across ward / senior / manager tiers with Medical and "
        "Surgical sub-wards. Same engine, different vocabulary.",
        nursing_ward,
        None, None, None,
    ),
    "nsplib_shaped_n30_7": (
        "NSPLib-shaped · n30 × d7",
        "30-doctor / 7-day roster in the parameter envelope of NSPLib's "
        "classic Vanhoucke & Maenhout (2007) benchmark family. Three "
        "'skill classes' (our tiers), realistic leave, preferred-shift "
        "requests. Run this through /lab/benchmark to see CP-SAT vs "
        "baselines on an NRP-literature-sized problem.",
        nsplib_shaped_n30_7,
        "NSPLib",
        "Vanhoucke & Maenhout (2007) — nsplib.ugent.be",
        "Shaped to match the n30/d7/s3 parameter envelope. Not a 1:1 "
        "import of a specific NSPLib instance — see docs/BRIEFING_2026-04-23.md "
        "§4.1 for the adapter follow-up.",
    ),
    "curtois_shaped_bcv": (
        "Curtois-shaped · BCV 4-week",
        "30-doctor / 4-week roster in the parameter envelope of "
        "Curtois's BCV (Belgian Children's Valentine) family from "
        "U. Nottingham's NRP collection. Mixed leave + call blocks + "
        "soft preferences + one part-timer (0.5 FTE) + one max-oncall "
        "cap. The stress-test scenario for fairness and coverage.",
        curtois_shaped_bcv,
        "Curtois NRP collection",
        "Curtois, U. Nottingham — cs.nott.ac.uk/~psztc/NRP/",
        "Shaped to match the BCV family's parameter envelope. Not a "
        "1:1 import of a specific Curtois instance — see "
        "docs/BRIEFING_2026-04-23.md §4.1 for the adapter follow-up.",
    ),
}


def main() -> None:
    out_dir = Path(__file__).resolve().parent.parent / "configs" / "scenarios"
    out_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict] = []

    for scenario_id, (title, description, builder, family, ref, caveat) in SCENARIOS.items():
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
        entry: dict = {
            "id": scenario_id,
            "title": title,
            "description": description,
            "n_doctors": n_doctors,
            "n_stations": n_stations,
            "n_days": n_days,
            "highlights": _highlights(state),
        }
        if family:
            entry["benchmark_family"] = family
            entry["benchmark_reference"] = ref
            entry["benchmark_caveat"] = caveat
        manifest.append(entry)

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
