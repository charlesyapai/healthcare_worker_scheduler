"""UI-state helpers: default editable tables + builder from them to Instance.

The Streamlit UI keeps mutable state as pandas DataFrames (one row per
doctor, per station, per leave entry). This module is the adapter
between those tables and the frozen `Instance` the solver expects.

Date convention: the UI picks a calendar start date; this module
converts calendar dates ↔ day indices used by the solver.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable, Union

import pandas as pd

from scheduler.instance import (
    DEFAULT_STATIONS,
    SUBSPECS,
    Doctor,
    Instance,
    Station,
)

TIERS = ("junior", "senior", "consultant")
# Exposed only for legacy default-table scaffolding. The UI re-reads the
# current subspec list from session_state["subspecs"].
SUBSPEC_CHOICES = ("", *SUBSPECS)


# ----------------------------------------------------------------- defaults

def default_doctors_df(n: int = 20, seed: int = 0) -> pd.DataFrame:
    """Seed an editable doctor table with sensible defaults.

    Tier mix mirrors `scheduler.instance._tier_split`. Names are generated
    as `Dr A`, `Dr B`, ... for readability. Eligible stations default to
    all tier-allowed stations (users can narrow later).
    """
    import random
    rng = random.Random(seed)
    n_j = max(4, int(round(n * 0.35)))
    n_s = max(3, int(round(n * 0.15)))
    n_c = max(6, n - n_j - n_s)
    if n_c < 2 * len(SUBSPECS):
        n_c = 2 * len(SUBSPECS)
    total = n_j + n_s + n_c
    if total != n:
        n_c += n - total

    rows: list[dict] = []

    def _name(i: int) -> str:
        """Spreadsheet-style names: A, B, ..., Z, AA, AB, ..."""
        if i < 26:
            return f"Dr {chr(65 + i)}"
        return f"Dr {chr(65 + i // 26 - 1)}{chr(65 + i % 26)}"

    idx = 0
    for _ in range(n_j):
        rows.append(dict(
            name=_name(idx), tier="junior", subspec="",
            eligible_stations=",".join(_default_elig("junior", rng)),
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
        idx += 1
    for _ in range(n_s):
        rows.append(dict(
            name=_name(idx), tier="senior", subspec="",
            eligible_stations=",".join(_default_elig("senior", rng)),
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
        idx += 1
    for i in range(n_c):
        ss = SUBSPECS[i % len(SUBSPECS)]
        rows.append(dict(
            name=_name(idx), tier="consultant", subspec=ss,
            eligible_stations=",".join(_default_elig("consultant", rng)),
            prev_workload=0, fte=1.0, max_oncalls=None,
        ))
        idx += 1
    return pd.DataFrame(rows)


def _default_elig(tier: str, rng) -> list[str]:
    allowed = [s.name for s in DEFAULT_STATIONS if tier in s.eligible_tiers]
    if len(allowed) > 4 and rng.random() < 0.3:
        drop = rng.choice(allowed)
        allowed = [s for s in allowed if s != drop]
    return allowed


def default_stations_df() -> pd.DataFrame:
    rows = []
    for s in DEFAULT_STATIONS:
        rows.append(dict(
            name=s.name,
            sessions=",".join(s.sessions),
            required_per_session=s.required_per_session,
            eligible_tiers=",".join(sorted(s.eligible_tiers)),
            is_reporting=s.is_reporting,
        ))
    return pd.DataFrame(rows)


# ----------------------------------------------------------------- date utils

def dates_for_horizon(start: date, n_days: int) -> list[date]:
    return [start + timedelta(days=i) for i in range(n_days)]


def day_index(d: date, start: date) -> int:
    return (d - start).days


def format_date(d: date) -> str:
    """'Mon 13 May' — human-friendly, fits in a column header."""
    return d.strftime("%a %d %b")


# ------------------------------------------------ build Instance from state

class BuildError(ValueError):
    """Raised when the editable tables can't form a valid Instance."""


def build_instance(
    *,
    start_date: date,
    n_days: int,
    doctors_df: pd.DataFrame,
    stations_df: pd.DataFrame,
    leave_entries: Iterable[tuple[str, date]] = (),
    public_holidays: Iterable[date] = (),
    weekend_am_pm_enabled: bool = False,
    prev_oncall_names: Iterable[str] = (),
    block_entries: Iterable[tuple[str, date, date | None, str]] = (),
    override_entries: Iterable[tuple[str, date, str]] = (),
    subspecs: Iterable[str] | None = None,
) -> Instance:
    """Assemble an Instance from editable tables.

    `block_entries` is an iterable of (doctor_name, start_date, end_date, kind).
    `end_date` may be None (single-day) or a date; the block applies every day
    from start_date through end_date inclusive. `kind` is one of "Leave",
    "No on-call", "No AM", "No PM", "Prefer AM", "Prefer PM" (case/space
    insensitive).
    `override_entries` is an iterable of (doctor_name, date, role) where role
    is a string like "STATION_CT_AM", "ONCALL", "WEEKEND_EXT", "WEEKEND_CONSULT".
    `subspecs` is the list of consultant sub-spec labels; defaults to the
    module-level SUBSPECS if None.
    """
    if n_days < 1:
        raise BuildError("n_days must be ≥ 1")

    # Stations first so we can validate eligibility.
    stations: list[Station] = []
    station_names: set[str] = set()
    for i, row in stations_df.iterrows():
        name = str(row["name"]).strip()
        if not name:
            continue
        if name in station_names:
            raise BuildError(f"Station name '{name}' appears twice.")
        station_names.add(name)
        sessions_s = str(row.get("sessions", "AM,PM")).strip() or "AM,PM"
        sessions = tuple(s.strip() for s in sessions_s.split(",") if s.strip())
        for s in sessions:
            if s not in ("AM", "PM", "FULL_DAY"):
                raise BuildError(
                    f"Station {name}: session '{s}' must be AM, PM, or "
                    f"FULL_DAY.")
        # FULL_DAY is exclusive — a station can't be both FULL_DAY and AM/PM.
        if "FULL_DAY" in sessions and len(sessions) > 1:
            raise BuildError(
                f"Station {name}: FULL_DAY cannot be combined with AM or PM.")
        try:
            req = int(row.get("required_per_session", 1))
        except (TypeError, ValueError):
            raise BuildError(f"Station {name}: required_per_session must be int.")
        tiers_s = str(row.get("eligible_tiers", "")).strip()
        tiers = frozenset(t.strip() for t in tiers_s.split(",") if t.strip())
        bad = tiers - set(TIERS)
        if bad:
            raise BuildError(f"Station {name}: unknown tiers {sorted(bad)}.")
        is_rep = bool(row.get("is_reporting", False))
        stations.append(Station(name, sessions, req, tiers, is_rep))

    if not stations:
        raise BuildError("At least one station is required.")

    # Subspec list (either user-supplied or module default).
    subspec_tuple: tuple[str, ...] = tuple(
        str(s).strip() for s in (subspecs or SUBSPECS) if s and str(s).strip()
    )
    if not subspec_tuple:
        subspec_tuple = tuple(SUBSPECS)

    # Doctors.
    doctors: list[Doctor] = []
    name_to_id: dict[str, int] = {}
    prev_workload_map: dict[int, int] = {}
    for i, row in doctors_df.iterrows():
        name = str(row["name"]).strip()
        if not name:
            continue
        if name in name_to_id:
            raise BuildError(f"Doctor name '{name}' appears twice.")
        tier = str(row.get("tier", "")).strip().lower()
        if tier not in TIERS:
            raise BuildError(
                f"Doctor {name}: tier must be one of {TIERS}, got '{tier}'.")
        subspec_raw = str(row.get("subspec", "")).strip()
        subspec = subspec_raw if subspec_raw else None
        if tier == "consultant" and subspec is None:
            raise BuildError(
                f"Consultant {name}: subspec is required (choose {list(subspec_tuple)}).")
        if subspec is not None and subspec not in subspec_tuple:
            raise BuildError(
                f"Doctor {name}: subspec '{subspec}' not in {list(subspec_tuple)}.")
        elig_s = str(row.get("eligible_stations", "")).strip()
        elig = frozenset(s.strip() for s in elig_s.split(",") if s.strip())
        bad = elig - station_names
        if bad:
            raise BuildError(
                f"Doctor {name}: unknown stations in eligibility {sorted(bad)}.")
        if not elig:
            raise BuildError(
                f"Doctor {name}: eligible_stations is empty — pick at least one.")

        # FTE (0.0–1.0) and max_oncalls (optional int).
        try:
            fte_raw = row.get("fte", 1.0)
            fte = float(fte_raw) if pd.notna(fte_raw) else 1.0
            fte = max(0.01, min(1.0, fte))
        except (TypeError, ValueError):
            fte = 1.0
        max_oncalls: int | None = None
        try:
            mo_raw = row.get("max_oncalls")
            if mo_raw is not None and pd.notna(mo_raw) and str(mo_raw).strip() != "":
                max_oncalls = int(mo_raw)
        except (TypeError, ValueError):
            max_oncalls = None

        new_id = len(doctors)
        doctors.append(Doctor(new_id, tier, subspec, elig,
                              fte=fte, max_oncalls=max_oncalls))
        name_to_id[name] = new_id
        try:
            prev_raw = row.get("prev_workload", 0)
            prev_workload_map[new_id] = int(prev_raw) if pd.notna(prev_raw) else 0
        except (TypeError, ValueError):
            prev_workload_map[new_id] = 0

    if not doctors:
        raise BuildError("At least one doctor is required.")

    # Leave + blocks + preferences: convert named entries → id-keyed dicts.
    leave: dict[int, set[int]] = {}
    no_oncall: dict[int, set[int]] = {}
    no_session: dict[int, dict[int, set[str]]] = {}
    prefer_session: dict[int, dict[int, set[str]]] = {}
    for name, d in leave_entries:
        if name not in name_to_id:
            raise BuildError(f"Leave entry for unknown doctor '{name}'.")
        idx = day_index(d, start_date)
        if 0 <= idx < n_days:
            leave.setdefault(name_to_id[name], set()).add(idx)

    def _daterange_indices(start_d: date, end_d: date | None) -> list[int]:
        """Inclusive range of day indices within [0, n_days) between start and end."""
        if end_d is None or end_d < start_d:
            end_d = start_d
        days: list[int] = []
        delta = (end_d - start_d).days
        for offset in range(delta + 1):
            idx = day_index(start_d + timedelta(days=offset), start_date)
            if 0 <= idx < n_days:
                days.append(idx)
        return days

    for entry in block_entries:
        if entry is None:
            continue
        # Support (name, date, kind) OR (name, start, end, kind).
        if len(entry) == 3:
            name, d_start, kind = entry
            d_end = None
        elif len(entry) == 4:
            name, d_start, d_end, kind = entry
        else:
            raise BuildError(f"Block entry has unexpected shape: {entry!r}")
        if not name:
            continue
        name = str(name).strip()
        if not name:
            continue
        if name not in name_to_id:
            raise BuildError(f"Block entry for unknown doctor '{name}'.")
        did = name_to_id[name]
        k = (kind or "").strip().upper().replace(" ", "_").replace("-", "_")
        for idx in _daterange_indices(d_start, d_end):
            if k in ("LEAVE", "OFF", "ANNUAL_LEAVE"):
                leave.setdefault(did, set()).add(idx)
            elif k in ("NO_ONCALL", "CALL_BLOCK", "NO_CALL"):
                no_oncall.setdefault(did, set()).add(idx)
            elif k in ("NO_AM", "NO_AM_SESSION"):
                no_session.setdefault(did, {}).setdefault(idx, set()).add("AM")
            elif k in ("NO_PM", "NO_PM_SESSION"):
                no_session.setdefault(did, {}).setdefault(idx, set()).add("PM")
            elif k in ("PREFER_AM", "PREF_AM"):
                prefer_session.setdefault(did, {}).setdefault(idx, set()).add("AM")
            elif k in ("PREFER_PM", "PREF_PM"):
                prefer_session.setdefault(did, {}).setdefault(idx, set()).add("PM")
            else:
                raise BuildError(
                    f"Block for {name}: unknown type '{kind}'. Use one of: "
                    "Leave, No on-call, No AM, No PM, Prefer AM, Prefer PM.")

    # Manual overrides.
    overrides: list[tuple[int, int, str | None, str | None, str]] = []
    station_name_set = {s.name for s in stations}
    for entry in override_entries or ():
        if entry is None:
            continue
        name, d, role = entry
        if not name:
            continue
        name = str(name).strip()
        if name not in name_to_id:
            raise BuildError(f"Override for unknown doctor '{name}'.")
        idx = day_index(d, start_date)
        if not (0 <= idx < n_days):
            continue
        did = name_to_id[name]
        r = (role or "").strip().upper()
        if r.startswith("STATION_"):
            # STATION_<name>_<session>
            parts = r[len("STATION_"):].rsplit("_", 1)
            if len(parts) != 2:
                raise BuildError(f"Override role '{role}': expected STATION_<name>_<AM|PM>.")
            st_name, sess = parts
            # Station names in the UI are upper-case identifiers; look up
            # case-insensitively against our station set.
            st_match = next((s for s in station_name_set if s.upper() == st_name), None)
            if st_match is None:
                raise BuildError(f"Override for {name}: unknown station '{st_name}'.")
            if sess not in ("AM", "PM"):
                raise BuildError(f"Override for {name}: session must be AM or PM.")
            overrides.append((did, idx, st_match, sess, "STATION"))
        elif r in ("ONCALL", "OC"):
            overrides.append((did, idx, None, None, "ONCALL"))
        elif r in ("EXT", "WEEKEND_EXT", "EXTENDED"):
            overrides.append((did, idx, None, None, "EXT"))
        elif r in ("WCONSULT", "WC", "WEEKEND_CONSULT"):
            overrides.append((did, idx, None, None, "WCONSULT"))
        else:
            raise BuildError(
                f"Override for {name}: unknown role '{role}'. Use one of: "
                "STATION_<name>_AM, STATION_<name>_PM, ONCALL, EXT, WCONSULT.")

    # Public holidays.
    ph_idx: set[int] = set()
    for d in public_holidays:
        idx = day_index(d, start_date)
        if 0 <= idx < n_days:
            ph_idx.add(idx)

    prev_oncall_ids = {
        name_to_id[n] for n in prev_oncall_names if n in name_to_id
    }

    # start_weekday: Monday=0 convention in Instance; Python's weekday() matches.
    return Instance(
        n_days=n_days,
        start_weekday=start_date.weekday(),
        doctors=doctors,
        stations=stations,
        leave=leave,
        public_holidays=ph_idx,
        prev_oncall=prev_oncall_ids,
        weekend_am_pm_enabled=weekend_am_pm_enabled,
        prev_workload=prev_workload_map,
        no_oncall=no_oncall,
        no_session=no_session,
        prefer_session=prefer_session,
        overrides=overrides,
        subspecs=subspec_tuple,
    )


def doctor_name_map(doctors_df: pd.DataFrame, inst: Instance) -> dict[int, str]:
    """Map solver doctor id → display name. Builds by row order (same as build_instance)."""
    out: dict[int, str] = {}
    names = [str(n).strip() for n in doctors_df["name"].tolist()]
    names = [n for n in names if n]
    for idx, d in enumerate(inst.doctors):
        if idx < len(names):
            out[d.id] = names[idx]
        else:
            out[d.id] = f"Dr #{d.id}"
    return out
