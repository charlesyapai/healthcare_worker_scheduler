"""In-memory session store + adapters to the v1 scheduler data model.

The SPA owns state in localStorage; the backend's in-memory session is a
short-lived cache used only while a request or WebSocket is live.

Session identity is resolved in this priority:
  1. `X-Session-Id` HTTP header (set by the SPA from a localStorage UUID).
  2. `session_id` cookie (legacy; still used by pytest TestClient and v1
     clients that were running before the switch).
  3. A freshly minted UUID, returned to the client as a cookie.

The header path matters in production: HF Spaces load the SPA inside a
cross-site iframe on huggingface.co, where `SameSite=Lax` cookies are
blocked. A header-based session ID sidesteps that policy entirely.

This module is also the single place where Pydantic SessionState is
translated into the shapes the v1 `scheduler.*` modules already accept,
so routes stay thin and no solver code is duplicated.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

import pandas as pd
from fastapi import Request, Response

from api.models.events import AssignmentRow, SolveResultPayload
from api.models.session import (
    BlockEntry,
    DoctorEntry,
    OverrideEntry,
    SessionState,
    StationEntry,
)
from scheduler.instance import Instance
from scheduler.model import ConstraintConfig, SolveResult, Weights, WorkloadWeights
from scheduler.ui_state import build_instance

SESSION_COOKIE = "session_id"
SESSION_HEADER = "x-session-id"


# --------------------------------------------------------------- store

@dataclass
class ServerSession:
    id: str
    state: SessionState = field(default_factory=SessionState)
    last_solve: SolveResultPayload | None = None


_SESSIONS: dict[str, ServerSession] = {}


def _resolve_sid(request: Request) -> str | None:
    """Pick up the session id from the header first, cookie second."""
    header = request.headers.get(SESSION_HEADER)
    if header:
        return header
    return request.cookies.get(SESSION_COOKIE)


def get_session(request: Request, response: Response) -> ServerSession:
    """FastAPI dependency. Creates a session on first hit; returns the same one afterwards."""
    sid = _resolve_sid(request)
    if sid and sid in _SESSIONS:
        return _SESSIONS[sid]
    sid = sid or uuid.uuid4().hex
    session = ServerSession(id=sid)
    _SESSIONS[sid] = session
    # Echo the id back via both channels so an older client that only reads
    # cookies keeps working, while modern clients read the header value.
    response.headers[SESSION_HEADER] = sid
    is_https = request.url.scheme == "https"
    response.set_cookie(
        key=SESSION_COOKIE,
        value=sid,
        httponly=True,
        # HTTPS in prod → SameSite=None + Secure so the cookie survives the
        # HF Spaces cross-site iframe. HTTP in dev/tests → plain Lax so the
        # cookie actually round-trips without Secure enforcement dropping it.
        samesite="none" if is_https else "lax",
        secure=is_https,
        path="/",
    )
    return session


def get_or_create_session_by_id(sid: str | None) -> ServerSession:
    """WebSocket helper — takes an already-resolved session id (from the
    ?session_id=… query param, the X-Session-Id subprotocol, or the cookie)."""
    if sid and sid in _SESSIONS:
        return _SESSIONS[sid]
    new_sid = sid or uuid.uuid4().hex
    session = ServerSession(id=new_sid)
    _SESSIONS[new_sid] = session
    return session


def reset_store() -> None:
    """Test helper."""
    _SESSIONS.clear()


# --------------------------------------------------------------- adapters

def session_to_v1_dict(state: SessionState) -> dict[str, Any]:
    """Build the flat, DataFrame-rich dict that `persistence.dump_state` and
    `ui_state.build_instance` expect."""
    doctors_df = pd.DataFrame([
        {
            "name": d.name,
            "tier": d.tier,
            "subspec": d.subspec or "",
            "eligible_stations": ",".join(d.eligible_stations),
            "prev_workload": d.prev_workload,
            "fte": d.fte,
            "max_oncalls": d.max_oncalls,
        }
        for d in state.doctors
    ]) if state.doctors else pd.DataFrame()

    stations_df = pd.DataFrame([
        {
            "name": s.name,
            "sessions": ",".join(s.sessions),
            "required_per_session": s.required_per_session,
            "eligible_tiers": ",".join(s.eligible_tiers),
            "is_reporting": s.is_reporting,
        }
        for s in state.stations
    ]) if state.stations else pd.DataFrame()

    blocks_df = pd.DataFrame([
        {
            "doctor": b.doctor,
            "date": b.date,
            "end_date": b.end_date,
            "type": b.type,
        }
        for b in state.blocks
    ]) if state.blocks else pd.DataFrame()

    overrides_df = pd.DataFrame([
        {"doctor": o.doctor, "date": o.date, "role": o.role}
        for o in state.overrides
    ]) if state.overrides else pd.DataFrame()

    return {
        "start_date": state.horizon.start_date,
        "n_days": state.horizon.n_days,
        "public_holidays": list(state.horizon.public_holidays),
        "doctors_df": doctors_df,
        "stations_df": stations_df,
        "blocks_df": blocks_df,
        "overrides_df": overrides_df,
        "tier_labels": state.tier_labels.model_dump(),
        "subspecs": list(state.subspecs),
        # Flat soft weights — keys match what dump_state reads.
        "w_workload": state.soft_weights.workload,
        "w_sessions": state.soft_weights.sessions,
        "w_oncall": state.soft_weights.oncall,
        "w_weekend": state.soft_weights.weekend,
        "w_report": state.soft_weights.reporting,
        "w_idle": state.soft_weights.idle_weekday,
        "w_pref": state.soft_weights.preference,
        # Workload weights.
        "wl_wd_session": state.workload_weights.weekday_session,
        "wl_we_session": state.workload_weights.weekend_session,
        "wl_wd_oncall": state.workload_weights.weekday_oncall,
        "wl_we_oncall": state.workload_weights.weekend_oncall,
        "wl_ext": state.workload_weights.weekend_ext,
        "wl_wconsult": state.workload_weights.weekend_consult,
        # Hours.
        "h_weekday_am": state.hours.weekday_am,
        "h_weekday_pm": state.hours.weekday_pm,
        "h_weekend_am": state.hours.weekend_am,
        "h_weekend_pm": state.hours.weekend_pm,
        "h_weekday_oncall": state.hours.weekday_oncall,
        "h_weekend_oncall": state.hours.weekend_oncall,
        "h_weekend_ext": state.hours.weekend_ext,
        "h_weekend_consult": state.hours.weekend_consult,
        # Constraints.
        "h4_enabled": state.constraints.h4_enabled,
        "h4_gap": state.constraints.h4_gap,
        "h5_enabled": state.constraints.h5_enabled,
        "h6_enabled": state.constraints.h6_enabled,
        "h7_enabled": state.constraints.h7_enabled,
        "h8_enabled": state.constraints.h8_enabled,
        "h9_enabled": state.constraints.h9_enabled,
        "h11_enabled": state.constraints.h11_enabled,
        "weekend_am_pm": state.constraints.weekend_am_pm,
        # Solver.
        "time_limit": state.solver.time_limit,
        "num_workers": state.solver.num_workers,
        "feasibility_only": state.solver.feasibility_only,
    }


def v1_dict_to_session(update: dict[str, Any], base: SessionState | None = None) -> SessionState:
    """Apply a v1-style updates dict (returned by `persistence.load_state`) to a
    SessionState. Missing keys fall back to `base` (or defaults)."""
    base = base or SessionState()
    data = base.model_dump(mode="json")

    if "start_date" in update:
        sd = update["start_date"]
        data["horizon"]["start_date"] = sd.isoformat() if isinstance(sd, date) else sd
    if "n_days" in update:
        data["horizon"]["n_days"] = int(update["n_days"])
    if "public_holidays" in update:
        data["horizon"]["public_holidays"] = [
            d.isoformat() if isinstance(d, date) else d
            for d in update["public_holidays"]
        ]

    def _df_rows(df_key: str) -> list[dict]:
        df = update.get(df_key)
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            return []
        rows: list[dict] = []
        for _, row in df.iterrows():
            rec: dict = {}
            for col, val in row.items():
                if pd.isna(val):
                    continue
                if isinstance(val, date):
                    rec[col] = val.isoformat()
                else:
                    rec[col] = val
            rows.append(rec)
        return rows

    if "doctors_df" in update:
        data["doctors"] = _df_rows("doctors_df")
    if "stations_df" in update:
        data["stations"] = _df_rows("stations_df")
    if "blocks_df" in update:
        data["blocks"] = _df_rows("blocks_df")
    if "overrides_df" in update:
        data["overrides"] = _df_rows("overrides_df")
    if "tier_labels" in update and isinstance(update["tier_labels"], dict):
        data["tier_labels"].update(update["tier_labels"])
    if "subspecs" in update:
        data["subspecs"] = list(update["subspecs"])

    flat_to_nested: dict[str, tuple[str, str]] = {
        "w_workload": ("soft_weights", "workload"),
        "w_sessions": ("soft_weights", "sessions"),
        "w_oncall": ("soft_weights", "oncall"),
        "w_weekend": ("soft_weights", "weekend"),
        "w_report": ("soft_weights", "reporting"),
        "w_idle": ("soft_weights", "idle_weekday"),
        "w_pref": ("soft_weights", "preference"),
        "wl_wd_session": ("workload_weights", "weekday_session"),
        "wl_we_session": ("workload_weights", "weekend_session"),
        "wl_wd_oncall": ("workload_weights", "weekday_oncall"),
        "wl_we_oncall": ("workload_weights", "weekend_oncall"),
        "wl_ext": ("workload_weights", "weekend_ext"),
        "wl_wconsult": ("workload_weights", "weekend_consult"),
        "h_weekday_am": ("hours", "weekday_am"),
        "h_weekday_pm": ("hours", "weekday_pm"),
        "h_weekend_am": ("hours", "weekend_am"),
        "h_weekend_pm": ("hours", "weekend_pm"),
        "h_weekday_oncall": ("hours", "weekday_oncall"),
        "h_weekend_oncall": ("hours", "weekend_oncall"),
        "h_weekend_ext": ("hours", "weekend_ext"),
        "h_weekend_consult": ("hours", "weekend_consult"),
        "h4_enabled": ("constraints", "h4_enabled"),
        "h4_gap": ("constraints", "h4_gap"),
        "h5_enabled": ("constraints", "h5_enabled"),
        "h6_enabled": ("constraints", "h6_enabled"),
        "h7_enabled": ("constraints", "h7_enabled"),
        "h8_enabled": ("constraints", "h8_enabled"),
        "h9_enabled": ("constraints", "h9_enabled"),
        "h11_enabled": ("constraints", "h11_enabled"),
        "weekend_am_pm": ("constraints", "weekend_am_pm"),
        "time_limit": ("solver", "time_limit"),
        "num_workers": ("solver", "num_workers"),
        "feasibility_only": ("solver", "feasibility_only"),
    }
    for flat, (section, key) in flat_to_nested.items():
        if flat in update:
            data[section][key] = update[flat]

    return SessionState.model_validate(data)


# --------------------------------------------------------------- Instance

_BLOCK_TYPE_ALIAS = {
    # build_instance's normalizer produces "NO_ON_CALL" from "No on-call"
    # (spaces and hyphens both become underscores), which isn't in its
    # accepted set. Remap to "CALL_BLOCK" which it does understand.
    "No on-call": "CALL_BLOCK",
}


def session_to_instance(state: SessionState) -> Instance:
    """Build a solver `Instance` from the current session state.

    Delegates to `ui_state.build_instance`, which validates doctors/stations
    and converts date ranges into day indices. Raises `BuildError` on invalid
    input — routes should map that to HTTP 400.
    """
    if state.horizon.start_date is None:
        raise ValueError("start_date is required to build a solver instance.")
    v1 = session_to_v1_dict(state)
    block_entries = [
        (b.doctor, b.date, b.end_date, _BLOCK_TYPE_ALIAS.get(b.type, b.type))
        for b in state.blocks
    ]
    override_entries = [(o.doctor, o.date, o.role) for o in state.overrides]
    return build_instance(
        start_date=state.horizon.start_date,
        n_days=state.horizon.n_days,
        doctors_df=v1["doctors_df"],
        stations_df=v1["stations_df"],
        public_holidays=list(state.horizon.public_holidays),
        weekend_am_pm_enabled=state.constraints.weekend_am_pm,
        block_entries=block_entries,
        override_entries=override_entries,
        subspecs=list(state.subspecs),
    )


def session_to_solver_configs(
    state: SessionState,
) -> tuple[Weights, WorkloadWeights, ConstraintConfig]:
    """Build the three solver dataclass configs from session state."""
    weights = Weights(
        balance_sessions=state.soft_weights.sessions,
        balance_oncall=state.soft_weights.oncall,
        balance_weekend=state.soft_weights.weekend,
        reporting_spread=state.soft_weights.reporting,
        balance_workload=state.soft_weights.workload,
        idle_weekday=state.soft_weights.idle_weekday,
        preference=state.soft_weights.preference,
    )
    wl = WorkloadWeights(
        weekday_session=state.workload_weights.weekday_session,
        weekend_session=state.workload_weights.weekend_session,
        weekday_oncall=state.workload_weights.weekday_oncall,
        weekend_oncall=state.workload_weights.weekend_oncall,
        weekend_ext=state.workload_weights.weekend_ext,
        weekend_consult=state.workload_weights.weekend_consult,
    )
    cfg = ConstraintConfig(
        h4_oncall_cap_enabled=state.constraints.h4_enabled,
        h4_oncall_gap_days=state.constraints.h4_gap,
        h5_post_call_off_enabled=state.constraints.h5_enabled,
        h6_senior_oncall_full_off_enabled=state.constraints.h6_enabled,
        h7_junior_oncall_pm_enabled=state.constraints.h7_enabled,
        h8_weekend_coverage_enabled=state.constraints.h8_enabled,
        h9_lieu_day_enabled=state.constraints.h9_enabled,
        h11_mandatory_weekday_enabled=state.constraints.h11_enabled,
    )
    return weights, wl, cfg


def _doctor_name_map(state: SessionState) -> dict[int, str]:
    """Match the id convention used by `ui_state.build_instance` (row-order)."""
    return {i: d.name for i, d in enumerate(state.doctors)}


def assignments_to_rows(
    state: SessionState,
    assignments: dict[str, dict],
) -> list[AssignmentRow]:
    """Flatten a SolveResult.assignments dict into a list of AssignmentRow.

    `assignments` is the solver's {"stations": {(d,day,st,sess): 1, ...},
    "oncall": {(d,day): 1, ...}, "ext": ..., "wconsult": ...}.
    """
    if not assignments or state.horizon.start_date is None:
        return []
    names = _doctor_name_map(state)
    start = state.horizon.start_date
    rows: list[AssignmentRow] = []
    for (did, day, station, sess), v in (assignments.get("stations") or {}).items():
        if not v:
            continue
        rows.append(AssignmentRow(
            doctor=names.get(did, f"#{did}"),
            date=start + timedelta(days=day),
            role=f"STATION_{station}_{sess}",
        ))
    for (did, day), v in (assignments.get("oncall") or {}).items():
        if not v:
            continue
        rows.append(AssignmentRow(
            doctor=names.get(did, f"#{did}"),
            date=start + timedelta(days=day),
            role="ONCALL",
        ))
    for (did, day), v in (assignments.get("ext") or {}).items():
        if not v:
            continue
        rows.append(AssignmentRow(
            doctor=names.get(did, f"#{did}"),
            date=start + timedelta(days=day),
            role="WEEKEND_EXT",
        ))
    for (did, day), v in (assignments.get("wconsult") or {}).items():
        if not v:
            continue
        rows.append(AssignmentRow(
            doctor=names.get(did, f"#{did}"),
            date=start + timedelta(days=day),
            role="WEEKEND_CONSULT",
        ))
    rows.sort(key=lambda r: (r.date, r.role, r.doctor))
    return rows


def solve_result_to_payload(
    state: SessionState,
    result: SolveResult,
) -> SolveResultPayload:
    return SolveResultPayload(
        status=result.status,
        wall_time_s=result.wall_time_s,
        objective=result.objective,
        best_bound=result.best_bound,
        n_vars=result.n_vars,
        n_constraints=result.n_constraints,
        first_feasible_s=result.first_feasible_s,
        penalty_components=dict(result.penalty_components),
        assignments=assignments_to_rows(state, result.assignments or {}),
    )


def deep_merge(base: dict, patch: dict) -> dict:
    """Recursive dict merge where lists replace (not extend)."""
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out
