"""/api/state routes — the single source of truth for a browser session."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.models.events import PrevWorkloadRequest
from api.models.session import DoctorEntry, Horizon, SessionState, StationEntry
from api.sessions import (
    ServerSession,
    deep_merge,
    get_session,
    v1_dict_to_session,
)
from scheduler.persistence import load_state, prev_workload_from_roster_json
from scheduler.ui_state import default_doctors_df, default_stations_df

router = APIRouter(prefix="/api/state", tags=["state"])


@router.get("", response_model=SessionState)
def get_state(session: ServerSession = Depends(get_session)) -> SessionState:
    return session.state


@router.put("", response_model=SessionState)
def put_state(
    state: SessionState,
    session: ServerSession = Depends(get_session),
) -> SessionState:
    session.state = state
    return session.state


@router.patch("", response_model=SessionState)
def patch_state(
    patch: dict[str, Any],
    session: ServerSession = Depends(get_session),
) -> SessionState:
    merged = deep_merge(session.state.model_dump(mode="json"), patch)
    try:
        session.state = SessionState.model_validate(merged)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid patch: {e}")
    return session.state


@router.post("/seed", response_model=SessionState)
def seed_defaults(session: ServerSession = Depends(get_session)) -> SessionState:
    """Replace the session with a sensible default roster problem.

    Useful for the SPA's empty-state "Start with defaults" button.
    """
    doctors_df = default_doctors_df(n=20, seed=0)
    stations_df = default_stations_df()
    doctors = [
        DoctorEntry.model_validate({
            "name": row["name"],
            "tier": row["tier"],
            "eligible_stations": row["eligible_stations"],
            "prev_workload": int(row.get("prev_workload", 0) or 0),
            "fte": float(row.get("fte", 1.0) or 1.0),
            "max_oncalls": row.get("max_oncalls"),
        })
        for _, row in doctors_df.iterrows()
    ]
    stations = [
        StationEntry.model_validate({
            "name": row["name"],
            "sessions": row["sessions"],
            "required_per_session": int(row["required_per_session"]),
            "eligible_tiers": row["eligible_tiers"],
            "is_reporting": bool(row["is_reporting"]),
            "weekday_enabled": bool(row.get("weekday_enabled", True)),
            "weekend_enabled": bool(row.get("weekend_enabled", False)),
        })
        for _, row in stations_df.iterrows()
    ]
    session.state = SessionState(
        horizon=Horizon(start_date=date.today(), n_days=21),
        doctors=doctors,
        stations=stations,
    )
    return session.state


SCENARIOS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "configs" / "scenarios"
)


@router.get("/scenarios")
def list_scenarios() -> list[dict]:
    """Return the manifest of pre-built scenarios (id, title, description,
    stats, highlights) for the SPA's scenario picker."""
    manifest_path = SCENARIOS_DIR / "manifest.json"
    if not manifest_path.exists():
        return []
    import json

    return json.loads(manifest_path.read_text())


@router.post("/scenarios/{scenario_id}", response_model=SessionState)
def load_scenario(
    scenario_id: str,
    session: ServerSession = Depends(get_session),
) -> SessionState:
    """Load one of the bundled scenarios into the current session."""
    yaml_path = SCENARIOS_DIR / f"{scenario_id}.yaml"
    if not yaml_path.exists():
        raise HTTPException(
            status_code=404, detail=f"Unknown scenario: {scenario_id}"
        )
    updates = load_state(yaml_path.read_text())
    session.state = v1_dict_to_session(updates, base=SessionState())
    return session.state


# Back-compat alias: the old /api/state/sample endpoint loads the first
# scenario (keeps existing SPA bundles working during a rolling upgrade).
@router.post("/sample", response_model=SessionState)
def load_sample(session: ServerSession = Depends(get_session)) -> SessionState:
    return load_scenario("radiology_small", session)


@router.post("/prev_workload", response_model=list[DoctorEntry])
def compute_prev_workload(
    req: PrevWorkloadRequest,
    session: ServerSession = Depends(get_session),
) -> list[DoctorEntry]:
    """Compute prev_workload from a prior-period roster JSON and apply it in place.

    Returns the updated doctors list so the client can diff what changed.
    """
    weights = session.state.workload_weights.model_dump()
    scores = prev_workload_from_roster_json(req.prev_roster_json, weights)
    updated: list[DoctorEntry] = []
    for d in session.state.doctors:
        new_score = int(scores.get(d.name, d.prev_workload))
        updated.append(d.model_copy(update={"prev_workload": new_score}))
    session.state = session.state.model_copy(update={"doctors": updated})
    return session.state.doctors
