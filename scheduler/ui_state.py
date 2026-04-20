"""UI-state helpers: default editable tables + builder from them to Instance.

The Streamlit UI keeps mutable state as pandas DataFrames (one row per
doctor, per station, per leave entry). This module is the adapter
between those tables and the frozen `Instance` the solver expects.

Date convention: the UI picks a calendar start date; this module
converts calendar dates ↔ day indices used by the solver.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Iterable

import pandas as pd

from scheduler.instance import (
    DEFAULT_STATIONS,
    SUBSPECS,
    Doctor,
    Instance,
    Station,
)

TIERS = ("junior", "senior", "consultant")
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
            prev_workload=0,
        ))
        idx += 1
    for _ in range(n_s):
        rows.append(dict(
            name=_name(idx), tier="senior", subspec="",
            eligible_stations=",".join(_default_elig("senior", rng)),
            prev_workload=0,
        ))
        idx += 1
    for i in range(n_c):
        ss = SUBSPECS[i % len(SUBSPECS)]
        rows.append(dict(
            name=_name(idx), tier="consultant", subspec=ss,
            eligible_stations=",".join(_default_elig("consultant", rng)),
            prev_workload=0,
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
    block_entries: Iterable[tuple[str, date, str]] = (),
) -> Instance:
    """Assemble an Instance from editable tables.

    `leave_entries` is an iterable of (doctor_name, date) pairs.
    `block_entries` is an iterable of (doctor_name, date, kind) where `kind`
    is one of "LEAVE", "NO_ONCALL", "NO_AM", "NO_PM". If you pass both
    `leave_entries` and "LEAVE" rows in `block_entries`, they are unioned.
    `public_holidays` is a list of dates. `prev_oncall_names` is a list of
    doctor names who were on-call on the day before `start_date`.
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
            if s not in ("AM", "PM"):
                raise BuildError(
                    f"Station {name}: session '{s}' must be AM or PM.")
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
                f"Consultant {name}: subspec is required (choose {list(SUBSPECS)}).")
        if subspec is not None and subspec not in SUBSPECS:
            raise BuildError(
                f"Doctor {name}: subspec '{subspec}' not in {SUBSPECS}.")
        elig_s = str(row.get("eligible_stations", "")).strip()
        elig = frozenset(s.strip() for s in elig_s.split(",") if s.strip())
        bad = elig - station_names
        if bad:
            raise BuildError(
                f"Doctor {name}: unknown stations in eligibility {sorted(bad)}.")
        if not elig:
            raise BuildError(
                f"Doctor {name}: eligible_stations is empty — pick at least one.")
        new_id = len(doctors)
        doctors.append(Doctor(new_id, tier, subspec, elig))
        name_to_id[name] = new_id
        try:
            prev_raw = row.get("prev_workload", 0)
            prev_workload_map[new_id] = int(prev_raw) if pd.notna(prev_raw) else 0
        except (TypeError, ValueError):
            prev_workload_map[new_id] = 0

    if not doctors:
        raise BuildError("At least one doctor is required.")

    # Leave + blocks: convert named entries → id-keyed dicts.
    leave: dict[int, set[int]] = {}
    no_oncall: dict[int, set[int]] = {}
    no_session: dict[int, dict[int, set[str]]] = {}
    for name, d in leave_entries:
        if name not in name_to_id:
            raise BuildError(f"Leave entry for unknown doctor '{name}'.")
        idx = day_index(d, start_date)
        if 0 <= idx < n_days:
            leave.setdefault(name_to_id[name], set()).add(idx)
    for name, d, kind in block_entries:
        if not name:
            continue
        if name not in name_to_id:
            raise BuildError(f"Block entry for unknown doctor '{name}'.")
        idx = day_index(d, start_date)
        if not (0 <= idx < n_days):
            continue
        did = name_to_id[name]
        k = (kind or "").strip().upper().replace(" ", "_").replace("-", "_")
        if k in ("LEAVE", "OFF", "ANNUAL_LEAVE"):
            leave.setdefault(did, set()).add(idx)
        elif k in ("NO_ONCALL", "CALL_BLOCK", "NO_CALL"):
            no_oncall.setdefault(did, set()).add(idx)
        elif k in ("NO_AM", "NO_AM_SESSION"):
            no_session.setdefault(did, {}).setdefault(idx, set()).add("AM")
        elif k in ("NO_PM", "NO_PM_SESSION"):
            no_session.setdefault(did, {}).setdefault(idx, set()).add("PM")
        else:
            raise BuildError(
                f"Block for {name}: unknown type '{kind}'. "
                "Use one of: Leave, No on-call, No AM, No PM.")

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
