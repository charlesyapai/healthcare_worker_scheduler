"""Generate configs/sample_feasible.yaml — a small, known-feasible roster.

Run from repo root:

    python scripts/build_sample_config.py

Writes configs/sample_feasible.yaml. The script also runs a quick solve
to confirm the instance is OPTIMAL / FEASIBLE before writing.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models.session import (  # noqa: E402
    DoctorEntry,
    Horizon,
    SessionState,
    StationEntry,
)
from api.sessions import session_to_instance, session_to_solver_configs  # noqa: E402
from scheduler.model import solve  # noqa: E402
from scheduler.persistence import dump_state  # noqa: E402
from api.sessions import session_to_v1_dict  # noqa: E402


def build_state() -> SessionState:
    # 15-doctor, 14-day configuration sized so coverage has comfortable
    # slack under the 1-in-3 on-call cap and H11 mandatory-weekday rule.
    doctors: list[DoctorEntry] = []

    # 5 juniors — eligible for all-tier stations.
    for n in ["Dr A", "Dr B", "Dr C", "Dr D", "Dr E"]:
        doctors.append(
            DoctorEntry(
                name=n,
                tier="junior",
                subspec=None,
                eligible_stations=["US", "XR_REPORT", "GEN_AM", "GEN_PM"],
                prev_workload=0,
                fte=1.0,
                max_oncalls=None,
            )
        )

    # 4 seniors — all-tier + cross-sectional.
    for n in ["Dr F", "Dr G", "Dr H", "Dr I"]:
        doctors.append(
            DoctorEntry(
                name=n,
                tier="senior",
                subspec=None,
                eligible_stations=["CT", "MR", "US", "XR_REPORT", "GEN_AM", "GEN_PM"],
                prev_workload=0,
                fte=1.0,
                max_oncalls=None,
            )
        )

    # 6 consultants, 2 per subspec.
    consultant_rows = [
        ("Dr J", "Neuro"),
        ("Dr K", "Neuro"),
        ("Dr L", "Body"),
        ("Dr M", "Body"),
        ("Dr N", "MSK"),
        ("Dr O", "MSK"),
    ]
    for n, ss in consultant_rows:
        doctors.append(
            DoctorEntry(
                name=n,
                tier="consultant",
                subspec=ss,
                eligible_stations=["CT", "MR", "US", "XR_REPORT", "IR", "FLUORO"],
                prev_workload=0,
                fte=1.0,
                max_oncalls=None,
            )
        )

    stations = [
        StationEntry(
            name="CT",
            sessions=["AM", "PM"],
            required_per_session=1,
            eligible_tiers=["senior", "consultant"],
            is_reporting=False,
        ),
        StationEntry(
            name="MR",
            sessions=["AM", "PM"],
            required_per_session=1,
            eligible_tiers=["senior", "consultant"],
            is_reporting=False,
        ),
        StationEntry(
            name="US",
            sessions=["AM", "PM"],
            required_per_session=2,
            eligible_tiers=["junior", "senior", "consultant"],
            is_reporting=False,
        ),
        StationEntry(
            name="XR_REPORT",
            sessions=["AM", "PM"],
            required_per_session=2,
            eligible_tiers=["junior", "senior", "consultant"],
            is_reporting=True,
        ),
        StationEntry(
            name="IR",
            sessions=["AM", "PM"],
            required_per_session=1,
            eligible_tiers=["consultant"],
            is_reporting=False,
        ),
        StationEntry(
            name="FLUORO",
            sessions=["AM", "PM"],
            required_per_session=1,
            eligible_tiers=["consultant"],
            is_reporting=False,
        ),
        StationEntry(
            name="GEN_AM",
            sessions=["AM"],
            required_per_session=1,
            eligible_tiers=["junior", "senior", "consultant"],
            is_reporting=False,
        ),
        StationEntry(
            name="GEN_PM",
            sessions=["PM"],
            required_per_session=1,
            eligible_tiers=["junior", "senior", "consultant"],
            is_reporting=False,
        ),
    ]

    start = date.today() + timedelta(days=(0 - date.today().weekday()) % 7)
    return SessionState(
        horizon=Horizon(start_date=start, n_days=7, public_holidays=[]),
        doctors=doctors,
        stations=stations,
        subspecs=["Neuro", "Body", "MSK"],
    )


def main() -> None:
    state = build_state()
    inst = session_to_instance(state)
    weights, wl, cfg = session_to_solver_configs(state)
    print(f"Solving {len(state.doctors)}-doctor × {state.horizon.n_days}-day sample …")
    result = solve(
        inst,
        time_limit_s=60,
        weights=weights,
        workload_weights=wl,
        constraints=cfg,
        num_workers=4,
        feasibility_only=False,
    )
    print(f"  → {result.status} in {result.wall_time_s:.1f}s, "
          f"objective={result.objective}, assignments={len(result.assignments.get('stations', {}))}")
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        sys.exit(f"Sample is not feasible (status={result.status}); refine before committing.")

    # Dump to YAML via the v1 persistence path — same format the SPA
    # reads through /api/state/yaml.
    v1 = session_to_v1_dict(state)
    yaml_text = dump_state(v1)

    out = Path(__file__).resolve().parent.parent / "configs" / "sample_feasible.yaml"
    out.write_text(yaml_text)
    print(f"  → wrote {out.relative_to(Path.cwd())} ({len(yaml_text)} bytes)")


if __name__ == "__main__":
    main()
