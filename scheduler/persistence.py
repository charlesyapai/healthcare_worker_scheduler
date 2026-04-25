"""Serialize / deserialize the app's configuration state to YAML.

HF Spaces storage is ephemeral — a Space restart wipes session state. This
module lets the user download their entire configuration (doctors, stations,
blocks, weights, hours, constraints, horizon) as a single YAML file and
re-upload it later to restore state verbatim.

All fields use sensible defaults when absent, so older saved files keep
loading after schema additions.
"""

from __future__ import annotations

from datetime import date
from io import StringIO
from typing import Any

import pandas as pd
import yaml

SCHEMA_VERSION = 3


def _df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame to a list-of-dicts with dates serialised as ISO."""
    out: list[dict] = []
    for _, row in df.iterrows():
        rec: dict[str, Any] = {}
        for col, val in row.items():
            if pd.isna(val):
                continue
            if isinstance(val, date):
                rec[col] = val.isoformat()
            else:
                rec[col] = val
        out.append(rec)
    return out


def _records_to_df(records: list[dict], columns: list[str]) -> pd.DataFrame:
    """Build a DataFrame from records, coercing ISO date strings back to date."""
    if not records:
        return pd.DataFrame({c: pd.Series(dtype="object") for c in columns})
    df = pd.DataFrame(records)
    # Ensure all expected columns exist.
    for c in columns:
        if c not in df.columns:
            df[c] = None
    # Coerce date columns.
    if "date" in df.columns:
        def _parse(v):
            if isinstance(v, date):
                return v
            if isinstance(v, str):
                try:
                    return date.fromisoformat(v)
                except ValueError:
                    return None
            return None
        df["date"] = df["date"].map(_parse)
    if "end_date" in df.columns:
        df["end_date"] = df["end_date"].map(
            lambda v: date.fromisoformat(v) if isinstance(v, str) else v
        )
    return df[columns]


def dump_state(ss) -> str:
    """Serialize session state (a streamlit.session_state or a plain dict) to YAML."""
    # Accept either Streamlit SessionState (dict-like) or a plain dict.
    get = ss.get if hasattr(ss, "get") else (lambda k, d=None: ss.get(k, d))

    start_date = get("start_date")
    if isinstance(start_date, date):
        start_date = start_date.isoformat()

    public_holidays = [
        d.isoformat() if isinstance(d, date) else str(d)
        for d in (get("public_holidays") or [])
    ]

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "horizon": {
            "start_date": start_date,
            "n_days": int(get("n_days", 21)),
            "public_holidays": public_holidays,
        },
        "doctors": _df_to_records(get("doctors_df", pd.DataFrame())),
        "stations": _df_to_records(get("stations_df", pd.DataFrame())),
        "blocks": _df_to_records(get("blocks_df", pd.DataFrame())),
        "overrides": _df_to_records(get("overrides_df", pd.DataFrame())),
        "role_preferences": _df_to_records(
            get("role_prefs_df", pd.DataFrame())
        ),
        "on_call_types": list(get("on_call_types") or []),
        "tier_labels": get("tier_labels") or {
            "junior": "Junior", "senior": "Senior", "consultant": "Consultant",
        },
        "shift_labels": get("shift_labels") or {
            "am": "AM",
            "pm": "PM",
            "full_day": "Full day",
            "oncall": "Night call",
            "weekend_ext": "Weekend extended",
            "weekend_consult": "Weekend consultant",
        },
        "soft_weights": {
            "workload": int(get("w_workload", 40)),
            "sessions": int(get("w_sessions", 5)),
            "oncall": int(get("w_oncall", 10)),
            "weekend": int(get("w_weekend", 10)),
            "reporting": int(get("w_report", 5)),
            "idle_weekday": int(get("w_idle", 100)),
            "preference": int(get("w_pref", 5)),
        },
        "workload_weights": {
            "weekday_session": int(get("wl_wd_session", 10)),
            "weekend_session": int(get("wl_we_session", 15)),
            "weekday_oncall": int(get("wl_wd_oncall", 20)),
            "weekend_oncall": int(get("wl_we_oncall", 35)),
            "weekend_ext": int(get("wl_ext", 20)),
            "weekend_consult": int(get("wl_wconsult", 25)),
        },
        "hours": {
            "weekday_am": float(get("h_weekday_am", 4.0)),
            "weekday_pm": float(get("h_weekday_pm", 4.0)),
            "weekend_am": float(get("h_weekend_am", 4.0)),
            "weekend_pm": float(get("h_weekend_pm", 4.0)),
            "weekday_oncall": float(get("h_weekday_oncall", 12.0)),
            "weekend_oncall": float(get("h_weekend_oncall", 16.0)),
            "weekend_ext": float(get("h_weekend_ext", 12.0)),
            "weekend_consult": float(get("h_weekend_consult", 8.0)),
        },
        "constraints": {
            "h5_enabled": bool(get("h5_enabled", True)),
            "h9_enabled": bool(get("h9_enabled", True)),
            "h11_enabled": bool(get("h11_enabled", True)),
        },
        "solver": {
            "time_limit": int(get("time_limit", 60)),
            "num_workers": int(get("num_workers", 8)),
            "feasibility_only": bool(get("feasibility_only", False)),
        },
    }
    return yaml.safe_dump(payload, sort_keys=False, default_flow_style=False)


DOCTOR_COLS = ["name", "tier", "eligible_stations",
               "eligible_oncall_types",
               "prev_workload", "fte", "max_oncalls"]
STATION_COLS = ["name", "sessions", "required_per_session",
                "eligible_tiers", "is_reporting",
                "weekday_enabled", "weekend_enabled"]
BLOCK_COLS = ["doctor", "date", "end_date", "type"]
OVERRIDE_COLS = ["doctor", "date", "role"]
ROLE_PREF_COLS = ["doctor", "role", "min_allocations", "priority"]


def _v2_to_v3_oncall_migration(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build the 5-type default on_call_types from v2's legacy constraint
    toggles. Mirrors `scheduler.instance.default_on_call_types` exactly so
    the first solve post-Phase-B reproduces legacy behaviour."""
    constraints = data.get("constraints") or {}
    weekday_oncall = bool(constraints.get("weekday_oncall_coverage", True))
    h8_on = bool(constraints.get("h8_enabled", True))
    weekend_consultants = int(constraints.get("weekend_consultants_required", 1))
    h4_gap_raw = constraints.get("h4_gap", 3)
    try:
        h4_gap = int(h4_gap_raw)
    except (TypeError, ValueError):
        h4_gap = 3
    h4_enabled = bool(constraints.get("h4_enabled", True))
    h5_enabled = bool(constraints.get("h5_enabled", True))
    h6_enabled = bool(constraints.get("h6_enabled", True))
    h7_enabled = bool(constraints.get("h7_enabled", True))

    night_days: list[str] = []
    if weekday_oncall:
        night_days.extend(["Mon", "Tue", "Wed", "Thu", "Fri"])
    if h8_on:
        night_days.extend(["Sat", "Sun"])
    weekend_days = ["Sat", "Sun"] if h8_on else []

    types: list[dict[str, Any]] = []
    cap = h4_gap if h4_enabled else None
    if night_days:
        types.append({
            "key": "oncall_jr",
            "label": "Night call (junior)",
            "start_hour": 20, "end_hour": 8,
            "days_active": night_days,
            "eligible_tiers": ["junior"],
            "daily_required": 1,
            "post_shift_rest_hours": 11,
            "next_day_off": h5_enabled,
            "frequency_cap_days": cap,
            "counts_as_weekend_role": False,
            "works_full_day": False,
            "works_pm_only": h7_enabled,
            "legacy_role_alias": "ONCALL",
        })
        types.append({
            "key": "oncall_sr",
            "label": "Night call (senior)",
            "start_hour": 20, "end_hour": 8,
            "days_active": night_days,
            "eligible_tiers": ["senior"],
            "daily_required": 1,
            "post_shift_rest_hours": 11,
            "next_day_off": h5_enabled,
            "frequency_cap_days": cap,
            "counts_as_weekend_role": False,
            "works_full_day": h6_enabled,
            "works_pm_only": False,
            "legacy_role_alias": "ONCALL",
        })
    if weekend_days:
        types.append({
            "key": "weekend_ext_jr",
            "label": "Weekend extended (junior)",
            "start_hour": 8, "end_hour": 20,
            "days_active": weekend_days,
            "eligible_tiers": ["junior"],
            "daily_required": 1,
            "post_shift_rest_hours": 0,
            "next_day_off": False,
            "frequency_cap_days": None,
            "counts_as_weekend_role": True,
            "works_full_day": False,
            "works_pm_only": False,
            "legacy_role_alias": "WEEKEND_EXT",
        })
        types.append({
            "key": "weekend_ext_sr",
            "label": "Weekend extended (senior)",
            "start_hour": 8, "end_hour": 20,
            "days_active": weekend_days,
            "eligible_tiers": ["senior"],
            "daily_required": 1,
            "post_shift_rest_hours": 0,
            "next_day_off": False,
            "frequency_cap_days": None,
            "counts_as_weekend_role": True,
            "works_full_day": False,
            "works_pm_only": False,
            "legacy_role_alias": "WEEKEND_EXT",
        })
        if weekend_consultants > 0:
            types.append({
                "key": "weekend_consult",
                "label": "Weekend consultant",
                "start_hour": 8, "end_hour": 17,
                "days_active": weekend_days,
                "eligible_tiers": ["consultant"],
                "daily_required": int(weekend_consultants),
                "post_shift_rest_hours": 0,
                "next_day_off": False,
                "frequency_cap_days": None,
                "counts_as_weekend_role": True,
                "works_full_day": False,
                "works_pm_only": False,
                "legacy_role_alias": "WEEKEND_CONSULT",
            })
    return types


def _eligible_types_for_tier(tier: str, types: list[dict]) -> list[str]:
    return [t["key"] for t in types if tier in (t.get("eligible_tiers") or [])]


def load_state(yaml_text: str) -> dict[str, Any]:
    """Parse a YAML string and return a dict of updates to apply to session_state.

    Missing sections fall back to defaults so old save files keep loading.

    Schema migration:
      * v1 → v2: drops `Doctor.subspec` + `subspecs` list (silently ignored
        on load). Per-station `weekday_enabled` defaults to True; per-station
        `weekend_enabled` inherits from the legacy
        `constraints.weekend_am_pm` flag once. The legacy flag itself is
        dropped from the returned update dict.
      * v2 → v3: synthesises the 5 default on_call_types from the legacy
        h4/h5/h6/h7/h8 + weekday_oncall_coverage + weekend_consultants_required
        constraint flags, populates each doctor's `eligible_oncall_types`
        from their tier, and drops the now-redundant constraint flags.
    """
    data = yaml.safe_load(yaml_text) or {}
    out: dict[str, Any] = {}

    schema_in = int(data.get("schema_version", 1) or 1)
    legacy_constraints = data.get("constraints") or {}
    legacy_weekend_am_pm = bool(legacy_constraints.get("weekend_am_pm", False))

    # Migrate v1 records in-place before they hit the DataFrame builders.
    if schema_in < 2:
        for d in (data.get("doctors") or []):
            if isinstance(d, dict):
                d.pop("subspec", None)
        for st in (data.get("stations") or []):
            if isinstance(st, dict):
                st.setdefault("weekday_enabled", True)
                st.setdefault("weekend_enabled", legacy_weekend_am_pm)

    # Migrate v2 records: build on_call_types from legacy toggles + derive
    # per-doctor eligible_oncall_types from tier.
    if schema_in < 3 and "on_call_types" not in data:
        types = _v2_to_v3_oncall_migration(data)
        data["on_call_types"] = types
        # Populate per-doctor eligible_oncall_types from tier if not present.
        for d in (data.get("doctors") or []):
            if not isinstance(d, dict):
                continue
            if d.get("eligible_oncall_types"):
                continue
            tier = str(d.get("tier", "")).lower()
            d["eligible_oncall_types"] = _eligible_types_for_tier(tier, types)

    horizon = data.get("horizon", {}) or {}
    if horizon.get("start_date"):
        try:
            out["start_date"] = date.fromisoformat(str(horizon["start_date"]))
        except ValueError:
            pass
    if "n_days" in horizon:
        out["n_days"] = int(horizon["n_days"])
    if "public_holidays" in horizon:
        parsed: list[date] = []
        for d in horizon["public_holidays"] or []:
            try:
                parsed.append(date.fromisoformat(str(d)))
            except ValueError:
                continue
        out["public_holidays"] = parsed

    if "doctors" in data:
        out["doctors_df"] = _records_to_df(data["doctors"] or [], DOCTOR_COLS)
    if "stations" in data:
        out["stations_df"] = _records_to_df(data["stations"] or [], STATION_COLS)
    if "blocks" in data:
        out["blocks_df"] = _records_to_df(data["blocks"] or [], BLOCK_COLS)
    if "overrides" in data:
        out["overrides_df"] = _records_to_df(data["overrides"] or [], OVERRIDE_COLS)
    if "role_preferences" in data:
        out["role_prefs_df"] = _records_to_df(
            data["role_preferences"] or [], ROLE_PREF_COLS,
        )

    if "on_call_types" in data and isinstance(data["on_call_types"], list):
        out["on_call_types"] = list(data["on_call_types"])

    if "tier_labels" in data and isinstance(data["tier_labels"], dict):
        out["tier_labels"] = {
            "junior": str(data["tier_labels"].get("junior", "Junior")),
            "senior": str(data["tier_labels"].get("senior", "Senior")),
            "consultant": str(data["tier_labels"].get("consultant", "Consultant")),
        }
    if "shift_labels" in data and isinstance(data["shift_labels"], dict):
        sl = data["shift_labels"]
        out["shift_labels"] = {
            "am": str(sl.get("am", "AM")),
            "pm": str(sl.get("pm", "PM")),
            "full_day": str(sl.get("full_day", "Full day")),
            "oncall": str(sl.get("oncall", "Night call")),
            "weekend_ext": str(sl.get("weekend_ext", "Weekend extended")),
            "weekend_consult": str(sl.get("weekend_consult", "Weekend consultant")),
        }
    # Legacy `subspecs` list is silently dropped on load (Phase A removal).

    for section, keys in (
        ("soft_weights", {
            "workload": "w_workload", "sessions": "w_sessions",
            "oncall": "w_oncall", "weekend": "w_weekend",
            "reporting": "w_report", "idle_weekday": "w_idle",
            "preference": "w_pref",
        }),
        ("workload_weights", {
            "weekday_session": "wl_wd_session", "weekend_session": "wl_we_session",
            "weekday_oncall": "wl_wd_oncall", "weekend_oncall": "wl_we_oncall",
            "weekend_ext": "wl_ext", "weekend_consult": "wl_wconsult",
        }),
        ("hours", {
            "weekday_am": "h_weekday_am", "weekday_pm": "h_weekday_pm",
            "weekend_am": "h_weekend_am", "weekend_pm": "h_weekend_pm",
            "weekday_oncall": "h_weekday_oncall", "weekend_oncall": "h_weekend_oncall",
            "weekend_ext": "h_weekend_ext", "weekend_consult": "h_weekend_consult",
        }),
        ("constraints", {
            "h5_enabled": "h5_enabled",
            "h9_enabled": "h9_enabled",
            "h11_enabled": "h11_enabled",
        }),
        ("solver", {
            "time_limit": "time_limit", "num_workers": "num_workers",
            "feasibility_only": "feasibility_only",
        }),
    ):
        section_data = data.get(section, {}) or {}
        for src, dst in keys.items():
            if src in section_data:
                out[dst] = section_data[src]

    return out


def prev_workload_from_roster_json(
    roster_json: dict,
    workload_weights: dict | None = None,
    hours_config: dict | None = None,
) -> dict[str, int]:
    """Compute per-doctor weighted workload from a prior-period export.

    `roster_json` is the dict from the Export tab's JSON download. Returns
    `{doctor_name: score}` that can be slotted into the current doctors_df's
    `prev_workload` column.
    """
    w = workload_weights or {
        "weekday_session": 10, "weekend_session": 15,
        "weekday_oncall": 20, "weekend_oncall": 35,
        "weekend_ext": 20, "weekend_consult": 25,
    }
    start_date_str = (roster_json.get("meta") or {}).get("start_date")
    if not start_date_str:
        return {}
    try:
        start = date.fromisoformat(start_date_str)
    except ValueError:
        return {}

    scores: dict[str, int] = {}
    for row in roster_json.get("assignments") or []:
        doctor = row.get("doctor")
        d_str = row.get("date")
        role = (row.get("role") or "").upper()
        if not doctor or not d_str:
            continue
        try:
            d = date.fromisoformat(d_str)
        except ValueError:
            continue
        wd = d.weekday()
        is_weekend = wd >= 5
        if role.startswith("STATION_"):
            parts = role.split("_")
            sess = parts[-1] if parts else "AM"
            key = f"{'weekend' if is_weekend else 'weekday'}_session"
            # Session-specific weights — AM and PM share a single weight today.
            inc = int(w.get(key, 10))
        elif role == "ONCALL" or role.startswith("ONCALL_"):
            # Phase B: user-defined on-call types use the weekday/weekend
            # on-call weights as a fallback (matches `model._oncall_weight`
            # for types without a legacy alias).
            key = f"{'weekend' if is_weekend else 'weekday'}_oncall"
            inc = int(w.get(key, 20))
        elif role == "WEEKEND_EXT":
            inc = int(w.get("weekend_ext", 20))
        elif role == "WEEKEND_CONSULT":
            inc = int(w.get("weekend_consult", 25))
        else:
            continue
        scores[doctor] = scores.get(doctor, 0) + inc
    return scores
