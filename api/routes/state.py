"""/api/state routes — the single source of truth for a browser session."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException

from api.models.events import PrevWorkloadRequest
from api.models.session import (
    DoctorEntry,
    Horizon,
    OnCallType,
    SessionState,
    StationEntry,
)
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
    on_call_types = _default_oncall_types()
    types_by_tier = {
        tier: [t.key for t in on_call_types if tier in t.eligible_tiers]
        for tier in ("junior", "senior", "consultant")
    }
    doctors = [
        DoctorEntry.model_validate({
            "name": row["name"],
            "tier": row["tier"],
            "eligible_stations": row["eligible_stations"],
            "eligible_oncall_types": types_by_tier.get(row["tier"], []),
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
        on_call_types=on_call_types,
    )
    return session.state


def _default_oncall_types() -> list[OnCallType]:
    """Phase B default 5-type on-call config used by `/api/state/seed`.
    Mirrors `scheduler.instance.default_on_call_types(weekday_oncall=True)`
    so the seeded session matches the legacy weekday + weekend coverage
    pattern."""
    return [
        OnCallType.model_validate({
            "key": "oncall_jr",
            "label": "Night call (junior)",
            "start_hour": 20, "end_hour": 8,
            "days_active": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "eligible_tiers": ["junior"],
            "daily_required": 1,
            "next_day_off": True,
            "frequency_cap_days": 3,
            "counts_as_weekend_role": False,
            "works_full_day": False,
            "works_pm_only": True,
            "legacy_role_alias": "ONCALL",
        }),
        OnCallType.model_validate({
            "key": "oncall_sr",
            "label": "Night call (senior)",
            "start_hour": 20, "end_hour": 8,
            "days_active": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
            "eligible_tiers": ["senior"],
            "daily_required": 1,
            "next_day_off": True,
            "frequency_cap_days": 3,
            "counts_as_weekend_role": False,
            "works_full_day": True,
            "works_pm_only": False,
            "legacy_role_alias": "ONCALL",
        }),
        OnCallType.model_validate({
            "key": "weekend_ext_jr",
            "label": "Weekend extended (junior)",
            "start_hour": 8, "end_hour": 20,
            "days_active": ["Sat", "Sun"],
            "eligible_tiers": ["junior"],
            "daily_required": 1,
            "next_day_off": False,
            "frequency_cap_days": None,
            "counts_as_weekend_role": True,
            "legacy_role_alias": "WEEKEND_EXT",
        }),
        OnCallType.model_validate({
            "key": "weekend_ext_sr",
            "label": "Weekend extended (senior)",
            "start_hour": 8, "end_hour": 20,
            "days_active": ["Sat", "Sun"],
            "eligible_tiers": ["senior"],
            "daily_required": 1,
            "next_day_off": False,
            "frequency_cap_days": None,
            "counts_as_weekend_role": True,
            "legacy_role_alias": "WEEKEND_EXT",
        }),
        OnCallType.model_validate({
            "key": "weekend_consult",
            "label": "Weekend consultant",
            "start_hour": 8, "end_hour": 17,
            "days_active": ["Sat", "Sun"],
            "eligible_tiers": ["consultant"],
            "daily_required": 1,
            "next_day_off": False,
            "frequency_cap_days": None,
            "counts_as_weekend_role": True,
            "legacy_role_alias": "WEEKEND_CONSULT",
        }),
    ]


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
