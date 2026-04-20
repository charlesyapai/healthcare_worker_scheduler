"""Streamlit UI for the healthcare roster scheduler (v0.5).

Three-tab flow: **Configure** (doctors, stations, dates, leave, constraints,
weights), **Solve & Roster** (streaming solve, verdict banner, doctor×date
grid, weighted workload breakdown), **Export** (JSON/CSV download). Sidebar
holds solver settings and diagnostics.

Run locally:    streamlit run app.py
HF Spaces:      deploy via the Docker frontmatter in README.md.
"""

from __future__ import annotations

import io
import json
import threading
import time
from datetime import date, timedelta
from queue import Empty, Queue

import pandas as pd
import streamlit as st

from scheduler import plots
from scheduler.diagnostics import explain_infeasibility, presolve_feasibility
from scheduler.metrics import (
    count_idle_weekdays,
    hours_per_doctor,
    problem_metrics,
    solution_metrics,
    solve_metrics,
    workload_breakdown,
)
from scheduler.model import (
    ConstraintConfig,
    HoursConfig,
    Weights,
    WorkloadWeights,
    solve,
)
from scheduler.persistence import (
    dump_state,
    load_state,
    prev_workload_from_roster_json,
)
from scheduler.ui_state import (
    BuildError,
    SUBSPEC_CHOICES,
    TIERS,
    build_instance,
    dates_for_horizon,
    default_doctors_df,
    default_stations_df,
    doctor_name_map,
    format_date,
)

POLL_INTERVAL_S = 0.2
ROLE_CODES = {
    "leave": "LV",
    "oncall": "OC",
    "ext": "EXT",
    "wconsult": "WC",
}


# ========================================================== Session state
def _next_monday(today: date) -> date:
    offset = (7 - today.weekday()) % 7 or 7
    return today + timedelta(days=offset)


BLOCK_TYPES = (
    "Leave", "No on-call", "No AM", "No PM", "Prefer AM", "Prefer PM"
)
OVERRIDE_ROLES_HELP = (
    "Examples: `STATION_CT_AM`, `STATION_XR_REPORT_PM`, `ONCALL`, "
    "`EXT`, `WCONSULT`. Case-insensitive."
)
DEFAULT_TIER_LABELS = {
    "junior": "Junior", "senior": "Senior", "consultant": "Consultant",
}
DEFAULT_SUBSPECS = ["Neuro", "Body", "MSK"]


def _ensure_defaults() -> None:
    ss = st.session_state
    if "doctors_df" not in ss:
        ss.doctors_df = default_doctors_df(20)
    if "stations_df" not in ss:
        ss.stations_df = default_stations_df()
    if "blocks_df" not in ss:
        ss.blocks_df = pd.DataFrame({
            "doctor": pd.Series(dtype="object"),
            "date": pd.Series(dtype="object"),
            "end_date": pd.Series(dtype="object"),
            "type": pd.Series(dtype="object"),
        })
    if "overrides_df" not in ss:
        ss.overrides_df = pd.DataFrame({
            "doctor": pd.Series(dtype="object"),
            "date": pd.Series(dtype="object"),
            "role": pd.Series(dtype="object"),
        })
    ss.setdefault("tier_labels", dict(DEFAULT_TIER_LABELS))
    ss.setdefault("subspecs", list(DEFAULT_SUBSPECS))
    ss.setdefault("start_date", _next_monday(date.today()))
    ss.setdefault("n_days", 21)
    ss.setdefault("public_holidays", [])
    # Objective weights.
    ss.setdefault("w_workload", 40)
    ss.setdefault("w_sessions", 5)
    ss.setdefault("w_oncall", 10)
    ss.setdefault("w_weekend", 10)
    ss.setdefault("w_report", 5)
    ss.setdefault("w_idle", 100)
    # Workload weights.
    ss.setdefault("wl_wd_session", 10)
    ss.setdefault("wl_we_session", 15)
    ss.setdefault("wl_wd_oncall", 20)
    ss.setdefault("wl_we_oncall", 35)
    ss.setdefault("wl_ext", 20)
    ss.setdefault("wl_wconsult", 25)
    # Hours per shift (for "hours per week" display only — does not affect solver).
    ss.setdefault("h_weekday_am", 4.0)
    ss.setdefault("h_weekday_pm", 4.0)
    ss.setdefault("h_weekend_am", 4.0)
    ss.setdefault("h_weekend_pm", 4.0)
    ss.setdefault("h_weekday_oncall", 12.0)
    ss.setdefault("h_weekend_oncall", 16.0)
    ss.setdefault("h_weekend_ext", 12.0)
    ss.setdefault("h_weekend_consult", 8.0)
    ss.setdefault("w_pref", 5)
    # Constraint toggles.
    ss.setdefault("h4_enabled", True)
    ss.setdefault("h4_gap", 3)
    ss.setdefault("h5_enabled", True)
    ss.setdefault("h6_enabled", True)
    ss.setdefault("h7_enabled", True)
    ss.setdefault("h8_enabled", True)
    ss.setdefault("h9_enabled", True)
    ss.setdefault("h11_enabled", True)
    # Misc.
    ss.setdefault("weekend_am_pm", False)
    ss.setdefault("time_limit", 60)
    ss.setdefault("num_workers", 8)
    ss.setdefault("feasibility_only", False)


# ========================================================== Instance build
def _coerce_date(v):
    if v is None or (hasattr(v, "__class__") and pd.isna(v)):
        return None
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        try:
            return date.fromisoformat(v)
        except ValueError:
            return None
    return None


def _build_inst():
    ss = st.session_state
    block_entries: list[tuple[str, date, date | None, str]] = []
    for _, row in ss.blocks_df.iterrows():
        doctor = row.get("doctor")
        d_start = _coerce_date(row.get("date"))
        d_end = _coerce_date(row.get("end_date"))
        kind = row.get("type") or "Leave"
        if doctor is None or d_start is None:
            continue
        if pd.isna(doctor):
            continue
        name = str(doctor).strip()
        if not name:
            continue
        block_entries.append((name, d_start, d_end, str(kind)))

    override_entries: list[tuple[str, date, str]] = []
    for _, row in ss.overrides_df.iterrows():
        doctor = row.get("doctor")
        d = _coerce_date(row.get("date"))
        role = row.get("role")
        if doctor is None or d is None or not role:
            continue
        if pd.isna(doctor) or pd.isna(role):
            continue
        name = str(doctor).strip()
        if not name:
            continue
        override_entries.append((name, d, str(role)))

    return build_instance(
        start_date=ss.start_date,
        n_days=int(ss.n_days),
        doctors_df=ss.doctors_df,
        stations_df=ss.stations_df,
        block_entries=block_entries,
        override_entries=override_entries,
        public_holidays=list(ss.public_holidays or []),
        weekend_am_pm_enabled=bool(ss.weekend_am_pm),
        subspecs=list(ss.subspecs or DEFAULT_SUBSPECS),
    )


def _current_weights() -> Weights:
    ss = st.session_state
    return Weights(
        balance_sessions=int(ss.w_sessions),
        balance_oncall=int(ss.w_oncall),
        balance_weekend=int(ss.w_weekend),
        reporting_spread=int(ss.w_report),
        balance_workload=int(ss.w_workload),
        idle_weekday=int(ss.w_idle),
        preference=int(ss.get("w_pref", 5)),
    )


def _current_workload_weights() -> WorkloadWeights:
    ss = st.session_state
    return WorkloadWeights(
        weekday_session=int(ss.wl_wd_session),
        weekend_session=int(ss.wl_we_session),
        weekday_oncall=int(ss.wl_wd_oncall),
        weekend_oncall=int(ss.wl_we_oncall),
        weekend_ext=int(ss.wl_ext),
        weekend_consult=int(ss.wl_wconsult),
    )


def _current_constraints() -> ConstraintConfig:
    ss = st.session_state
    return ConstraintConfig(
        h4_oncall_cap_enabled=bool(ss.h4_enabled),
        h4_oncall_gap_days=int(ss.h4_gap),
        h5_post_call_off_enabled=bool(ss.h5_enabled),
        h6_senior_oncall_full_off_enabled=bool(ss.h6_enabled),
        h7_junior_oncall_pm_enabled=bool(ss.h7_enabled),
        h8_weekend_coverage_enabled=bool(ss.h8_enabled),
        h9_lieu_day_enabled=bool(ss.h9_enabled),
        h11_mandatory_weekday_enabled=bool(ss.h11_enabled),
    )


def _current_hours() -> HoursConfig:
    ss = st.session_state
    return HoursConfig(
        weekday_am=float(ss.h_weekday_am),
        weekday_pm=float(ss.h_weekday_pm),
        weekend_am=float(ss.h_weekend_am),
        weekend_pm=float(ss.h_weekend_pm),
        weekday_oncall=float(ss.h_weekday_oncall),
        weekend_oncall=float(ss.h_weekend_oncall),
        weekend_ext=float(ss.h_weekend_ext),
        weekend_consult=float(ss.h_weekend_consult),
    )


# ========================================================== Roster render
def _snapshot_to_role_grid(inst, assignments: dict, names: dict[int, str]) -> pd.DataFrame:
    """Row per doctor, column per date. Cell = role string."""
    start_date = st.session_state.start_date
    dates = [start_date + timedelta(days=t) for t in range(inst.n_days)]
    date_labels = [format_date(d) for d in dates]

    doc_order = [names.get(d.id, f"Dr #{d.id}") for d in inst.doctors]
    grid = {name: [""] * inst.n_days for name in doc_order}

    for did, days in inst.leave.items():
        nm = names.get(did, f"Dr #{did}")
        for t in days:
            if 0 <= t < inst.n_days:
                grid[nm][t] = ROLE_CODES["leave"]

    stations = assignments.get("stations", {})
    per_cell: dict[tuple[int, int], list[str]] = {}
    for key in stations:
        if not stations.get(key):
            continue
        did, day, sname, sess = key
        per_cell.setdefault((did, day), []).append(f"{sess}:{sname}")
    for (did, day), labels in per_cell.items():
        nm = names.get(did, f"Dr #{did}")
        grid[nm][day] = " / ".join(sorted(labels))

    for (did, day), v in assignments.get("oncall", {}).items():
        if not v:
            continue
        nm = names.get(did, f"Dr #{did}")
        cur = grid[nm][day]
        grid[nm][day] = (cur + " " if cur else "") + ROLE_CODES["oncall"]
    for (did, day), v in assignments.get("ext", {}).items():
        if not v:
            continue
        nm = names.get(did, f"Dr #{did}")
        cur = grid[nm][day]
        grid[nm][day] = (cur + " " if cur else "") + ROLE_CODES["ext"]
    for (did, day), v in assignments.get("wconsult", {}).items():
        if not v:
            continue
        nm = names.get(did, f"Dr #{did}")
        cur = grid[nm][day]
        grid[nm][day] = (cur + " " if cur else "") + ROLE_CODES["wconsult"]

    df = pd.DataFrame({date_labels[t]: [grid[nm][t] for nm in doc_order]
                       for t in range(inst.n_days)}, index=doc_order)
    df.index.name = "Doctor"
    return df


def _tier_label(tier: str) -> str:
    return st.session_state.get("tier_labels", DEFAULT_TIER_LABELS).get(
        tier, tier.capitalize())


def _workload_tables(inst, assignments: dict, names: dict[int, str],
                     wl_weights: WorkloadWeights,
                     hours: HoursConfig) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return (headline_df, breakdown_df).

    Headline: the numbers that matter at a glance — workload score, distance
    from tier median, hours per week, leave days, unassigned days.
    Breakdown: the full per-role counts for users who want to dig in.
    """
    breakdown = workload_breakdown(inst, assignments, wl_weights)
    idle_counts = count_idle_weekdays(inst, assignments)
    hours_by_did = hours_per_doctor(inst, assignments, hours)

    headline_rows: list[dict] = []
    breakdown_rows: list[dict] = []
    for d in inst.doctors:
        b = breakdown[d.id]
        nm = names.get(d.id, f"Dr #{d.id}")
        subspec = d.subspec or ""
        hrs = hours_by_did.get(d.id, {}).get("hours_per_week", 0.0)
        idle = idle_counts.get(d.id, 0)
        headline_rows.append({
            "Doctor": nm,
            "Tier": _tier_label(d.tier),
            "Sub-spec": subspec,
            "Workload score": b["score"],
            "Δ vs. tier median": 0.0,   # filled below
            "Hours / week": hrs,
            "Leave days": b["leave_days"],
            "Days without duty": idle,
        })
        breakdown_rows.append({
            "Doctor": nm,
            "Tier": _tier_label(d.tier),
            "Sub-spec": subspec,
            "Weekday sessions": b["weekday_sessions"],
            "Weekend sessions": b["weekend_sessions"],
            "Weekday on-call": b["weekday_oncall"],
            "Weekend on-call": b["weekend_oncall"],
            "Weekend extended": b["ext"],
            "Weekend consultant": b["wconsult"],
            "Leave days": b["leave_days"],
            "Prev-period score": b["prev_workload"],
            "This-period score": b["score"] - b["prev_workload"],
            "Total (with carry-in)": b["score"],
        })

    headline = pd.DataFrame(headline_rows)
    if not headline.empty:
        for tier in ("junior", "senior", "consultant"):
            label = _tier_label(tier)
            mask = headline["Tier"] == label
            if mask.sum() < 2:
                continue
            med = headline.loc[mask, "Workload score"].median()
            headline.loc[mask, "Δ vs. tier median"] = \
                headline.loc[mask, "Workload score"] - med
    return headline, pd.DataFrame(breakdown_rows)


def _station_view(inst, assignments: dict, names: dict[int, str]) -> pd.DataFrame:
    """Rows = station × session; columns = dates; cells = comma-joined doctor names."""
    start_date = st.session_state.start_date
    dates = [start_date + timedelta(days=t) for t in range(inst.n_days)]
    date_labels = [format_date(d) for d in dates]
    rows_by_label: dict[str, list[list[str]]] = {}

    def _ensure_row(label: str):
        if label not in rows_by_label:
            rows_by_label[label] = [[] for _ in range(inst.n_days)]
        return rows_by_label[label]

    for (did, day, st_name, sess), v in assignments.get("stations", {}).items():
        if not v:
            continue
        row = _ensure_row(f"{st_name} · {sess}")
        row[day].append(names.get(did, f"Dr #{did}"))
    for (did, day), v in assignments.get("oncall", {}).items():
        if not v:
            continue
        row = _ensure_row("ON-CALL (night)")
        row[day].append(names.get(did, f"Dr #{did}"))
    for (did, day), v in assignments.get("ext", {}).items():
        if not v:
            continue
        row = _ensure_row("Weekend EXT")
        row[day].append(names.get(did, f"Dr #{did}"))
    for (did, day), v in assignments.get("wconsult", {}).items():
        if not v:
            continue
        row = _ensure_row("Weekend consultant")
        row[day].append(names.get(did, f"Dr #{did}"))

    if not rows_by_label:
        return pd.DataFrame({label: [""] * len(date_labels) for label in date_labels})

    df = pd.DataFrame(
        {date_labels[t]: [", ".join(rows_by_label[label][t])
                          for label in sorted(rows_by_label.keys())]
         for t in range(inst.n_days)},
        index=sorted(rows_by_label.keys()),
    )
    df.index.name = "Role / station"
    return df


def _today_summary(inst, assignments: dict, names: dict[int, str],
                   target_date: date) -> pd.DataFrame:
    """Single-day summary: who's doing what on `target_date`."""
    start_date = st.session_state.start_date
    day = (target_date - start_date).days
    if day < 0 or day >= inst.n_days:
        return pd.DataFrame()
    rows: list[dict] = []
    for (did, d, st_name, sess), v in assignments.get("stations", {}).items():
        if d == day and v:
            rows.append({"Doctor": names.get(did, f"Dr #{did}"),
                         "Role": f"{sess} · {st_name}"})
    for (did, d), v in assignments.get("oncall", {}).items():
        if d == day and v:
            rows.append({"Doctor": names.get(did, f"Dr #{did}"),
                         "Role": "On-call (night)"})
    for (did, d), v in assignments.get("ext", {}).items():
        if d == day and v:
            rows.append({"Doctor": names.get(did, f"Dr #{did}"),
                         "Role": "Weekend extended"})
    for (did, d), v in assignments.get("wconsult", {}).items():
        if d == day and v:
            rows.append({"Doctor": names.get(did, f"Dr #{did}"),
                         "Role": "Weekend consultant"})
    for did, leave_days in inst.leave.items():
        if day in leave_days:
            rows.append({"Doctor": names.get(did, f"Dr #{did}"), "Role": "LEAVE"})
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values(["Role", "Doctor"]).reset_index(drop=True)


def _per_doctor_calendar(inst, assignments: dict, names: dict[int, str],
                         doctor_name: str) -> pd.DataFrame:
    """Week rows × day-of-week columns for a single doctor."""
    start_date = st.session_state.start_date
    did = None
    for d in inst.doctors:
        if names.get(d.id) == doctor_name:
            did = d.id
            break
    if did is None:
        return pd.DataFrame()

    full_grid = _snapshot_to_role_grid(inst, assignments, names)
    if doctor_name not in full_grid.index:
        return pd.DataFrame()
    row = full_grid.loc[doctor_name]

    # Pad to start on Monday.
    first_day_weekday = start_date.weekday()  # 0=Mon
    # Figure out how many weeks to show.
    total_days = first_day_weekday + inst.n_days
    n_weeks = (total_days + 6) // 7

    day_names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    week_rows = []
    week_index: list[str] = []
    for w in range(n_weeks):
        week_start = start_date + timedelta(days=w * 7 - first_day_weekday)
        week_index.append(f"Week of {format_date(week_start)}")
        cells: list[str] = []
        for dow in range(7):
            d = week_start + timedelta(days=dow)
            day_idx = (d - start_date).days
            if 0 <= day_idx < inst.n_days:
                cells.append(str(row.iloc[day_idx]))
            else:
                cells.append("—")  # outside horizon
        week_rows.append(cells)
    df = pd.DataFrame(week_rows, columns=day_names, index=week_index)
    return df


def _diff_snapshots(inst, a: dict, b: dict, names: dict[int, str]) -> pd.DataFrame:
    """Doctor × date grid where cells show changes from snapshot `a` to `b`."""
    ga = _snapshot_to_role_grid(inst, a, names)
    gb = _snapshot_to_role_grid(inst, b, names)
    if ga.empty or gb.empty:
        return pd.DataFrame()
    # Align rows/columns.
    cols = ga.columns.intersection(gb.columns)
    idx = ga.index.intersection(gb.index)
    ga2, gb2 = ga.loc[idx, cols], gb.loc[idx, cols]
    diff = ga2.copy()
    for row_label in idx:
        for c in cols:
            va = str(ga2.loc[row_label, c]).strip()
            vb = str(gb2.loc[row_label, c]).strip()
            if va == vb:
                diff.loc[row_label, c] = ""
            else:
                diff.loc[row_label, c] = f"{va or '—'} → {vb or '—'}"
    return diff


def _style_diff(df: pd.DataFrame):
    if df.empty:
        return df

    def _color(val):
        v = str(val) if val else ""
        if v and "→" in v:
            return "background-color: rgba(255, 220, 120, 0.5); color: #5a3a00"
        return ""

    styler = df.style
    mapfn = getattr(styler, "map", None) or styler.applymap
    return mapfn(_color)


def _style_roster_grid(grid_df: pd.DataFrame):
    """Colour cells by role so leave / on-call / station / idle are at-a-glance."""
    if grid_df.empty:
        return grid_df

    def _cell_css(val):
        v = str(val).strip() if val else ""
        if not v:
            # No duty — amber so it stands out as "something to fix".
            return "background-color: rgba(255, 215, 130, 0.35); color: #8a5a00"
        # Leave — muted grey.
        if v == "LV":
            return "background-color: rgba(180, 180, 180, 0.35); color: #555"
        has_oc = "OC" in v.split()
        has_ext = "EXT" in v.split()
        has_wc = "WC" in v.split()
        has_stations = ("AM:" in v) or ("PM:" in v)
        # Weekend EXT / WC — teal.
        if has_ext or has_wc:
            return "background-color: rgba(120, 200, 220, 0.4); color: #0a3a4a"
        # On-call (possibly + PM station for juniors) — purple.
        if has_oc:
            return "background-color: rgba(190, 140, 220, 0.4); color: #2a1040"
        # Station work (AM and/or PM) — green; darker if both.
        if has_stations:
            both = ("AM:" in v) and ("PM:" in v)
            alpha = 0.45 if both else 0.3
            return f"background-color: rgba(130, 210, 150, {alpha}); color: #0a3a1a"
        return ""

    styler = grid_df.style
    mapfn = getattr(styler, "map", None) or styler.applymap
    return mapfn(_cell_css)


def _style_headline(df: pd.DataFrame):
    """Colour Δ-vs-median red (over) / blue (under), and format numbers."""
    if df.empty or "Δ vs. tier median" not in df.columns:
        return df
    col = df["Δ vs. tier median"]
    max_abs = max(col.abs().max(), 1)

    def _color(val):
        try:
            v = float(val)
        except (TypeError, ValueError):
            return ""
        intensity = min(1.0, abs(v) / max_abs)
        if v > 0.5:
            return f"background-color: rgba(220, 50, 50, {0.15 + 0.35*intensity:.2f})"
        if v < -0.5:
            return f"background-color: rgba(50, 120, 220, {0.15 + 0.35*intensity:.2f})"
        return ""

    styler = df.style
    mapfn = getattr(styler, "map", None) or styler.applymap
    return mapfn(_color, subset=["Δ vs. tier median"]).format({
        "Δ vs. tier median": "{:+.1f}",
        "Workload score": "{:.0f}",
        "Hours / week": "{:.1f}",
    })


def _verdict(result, events, idle_total: int, has_coverage_viol: bool,
             tier_hours: dict[str, float] | None = None) -> tuple[str, str]:
    """Returns (severity, message) where severity ∈ {'success','info','warning','error'}."""
    status = result.status
    gap_pct = None
    if result.objective and result.best_bound is not None and result.objective > 0:
        gap_pct = max(0.0, (result.objective - result.best_bound) / result.objective * 100)

    if status == "INFEASIBLE":
        return "error", ("**INFEASIBLE.** No roster satisfies your hard constraints. "
                         "Use the **Diagnose** button in the sidebar to see which "
                         "constraints are conflicting.")
    if status in ("UNKNOWN", "MODEL_INVALID"):
        return "error", f"**{status}** — solver could not complete. Raise the time limit and retry."
    # OPTIMAL or FEASIBLE.
    issues: list[str] = []
    if idle_total > 0:
        issues.append(f"{idle_total} doctor-weekday(s) with no duty — capacity is "
                      "tight. Add more stations, raise required_per_session, or "
                      "raise the 'no-duty' penalty.")
    if has_coverage_viol:
        issues.append("coverage violations detected (solver bug — report this)")
    if tier_hours:
        non_zero = {t: h for t, h in tier_hours.items() if h > 0}
        if len(non_zero) >= 2:
            lo_t, lo = min(non_zero.items(), key=lambda kv: kv[1])
            hi_t, hi = max(non_zero.items(), key=lambda kv: kv[1])
            if hi > 0 and lo / hi < 0.6:
                labels = st.session_state.get("tier_labels", DEFAULT_TIER_LABELS)
                hi_lab = labels.get(hi_t, hi_t) + "s"
                lo_lab = labels.get(lo_t, lo_t) + "s"
                issues.append(
                    f"**Cross-tier gap**: {hi_lab} average {hi:.0f}h/week but "
                    f"{lo_lab} only {lo:.0f}h/week. Usually means your stations "
                    "give one tier far fewer eligible slots — check the Stations "
                    "editor (required_per_session, eligible_tiers)."
                )
    if status == "OPTIMAL":
        head = "**OPTIMAL.** Solver proved this is the best possible roster under your constraints."
    else:
        if gap_pct is not None and gap_pct < 5:
            head = f"**FEASIBLE, gap {gap_pct:.1f}%** — probably good enough; raise the time limit to try to prove optimal."
        elif gap_pct is not None:
            head = f"**FEASIBLE, gap {gap_pct:.1f}%** — solver ran out of time before proving optimality."
        else:
            head = "**FEASIBLE.**"
    if issues:
        return ("warning", head + "\n\n" + "\n\n".join(f"• {i}" for i in issues))
    return ("success", head)


# ========================================================== App shell
st.set_page_config(page_title="Healthcare Roster Scheduler", layout="wide")
_ensure_defaults()

st.title("Healthcare Roster Scheduler")
st.caption("Configure, solve, review. Constraint spec: `docs/CONSTRAINTS.md`.")

# --------------------------------------------------------------------- Sidebar
with st.sidebar:
    st.subheader("Save / Load configuration")
    st.caption("Hugging Face storage is ephemeral. Use these buttons to save "
               "your whole setup (doctors, stations, blocks, weights) to a "
               "YAML file on your computer, and re-upload it later to pick up "
               "where you left off.")
    try:
        yaml_text = dump_state(st.session_state)
    except Exception as exc:  # pragma: no cover
        yaml_text = f"# error: {exc}"
    today_tag = date.today().isoformat()
    st.download_button(
        "💾 Save YAML",
        data=yaml_text, file_name=f"roster_config_{today_tag}.yaml",
        mime="application/x-yaml", use_container_width=True,
    )
    uploaded = st.file_uploader(
        "Load YAML", type=["yaml", "yml"], key="yaml_uploader",
        help="Replaces your current configuration.")
    if uploaded is not None and not st.session_state.get("_yaml_loaded_once"):
        try:
            updates = load_state(uploaded.read().decode("utf-8"))
            for k, v in updates.items():
                st.session_state[k] = v
            st.session_state["_yaml_loaded_once"] = True
            st.success("Configuration loaded. Switching to the Configure tab.")
            st.rerun()
        except Exception as exc:  # pragma: no cover
            st.error(f"Could not load YAML: {exc}")
    elif uploaded is None:
        st.session_state.pop("_yaml_loaded_once", None)

    with st.expander("Import prior-period workload"):
        st.caption("Upload last month's JSON export (from the Export tab) to "
                   "auto-fill the **Previous workload** column in the Doctors "
                   "table.")
        prev_roster = st.file_uploader(
            "Previous roster JSON", type=["json"], key="prev_roster_uploader")
        if prev_roster is not None and not st.session_state.get("_prev_loaded_once"):
            try:
                prev_data = json.loads(prev_roster.read().decode("utf-8"))
                ww = {
                    "weekday_session": st.session_state.wl_wd_session,
                    "weekend_session": st.session_state.wl_we_session,
                    "weekday_oncall": st.session_state.wl_wd_oncall,
                    "weekend_oncall": st.session_state.wl_we_oncall,
                    "weekend_ext": st.session_state.wl_ext,
                    "weekend_consult": st.session_state.wl_wconsult,
                }
                scores = prev_workload_from_roster_json(prev_data, ww)
                if scores:
                    df = st.session_state.doctors_df.copy()
                    if "prev_workload" not in df.columns:
                        df["prev_workload"] = 0
                    for i, row in df.iterrows():
                        nm = str(row.get("name", "")).strip()
                        if nm in scores:
                            df.at[i, "prev_workload"] = int(scores[nm])
                    st.session_state.doctors_df = df
                    st.session_state["_prev_loaded_once"] = True
                    st.success(f"Filled prev_workload for {len(scores)} doctors.")
                    st.rerun()
                else:
                    st.warning("JSON had no recognisable assignments.")
            except Exception as exc:  # pragma: no cover
                st.error(f"Could not parse: {exc}")
        elif prev_roster is None:
            st.session_state.pop("_prev_loaded_once", None)

    st.divider()
    st.subheader("Solver settings")
    st.slider("Time limit (s)", 5, 3600, key="time_limit",
              help="Max wall time for the solver. Longer = potentially better "
                   "solutions.")
    st.slider("CP-SAT workers", 1, 16, key="num_workers")
    st.checkbox("Feasibility only (skip objective)", key="feasibility_only")

    st.divider()
    st.subheader("Diagnostics")
    if st.button("Diagnose (L1 pre-solve)", use_container_width=True):
        try:
            inst = _build_inst()
            issues = presolve_feasibility(inst)
            if not issues:
                st.success("All L1 checks pass.")
            else:
                errs = [i for i in issues if i.severity == "error"]
                warns = [i for i in issues if i.severity == "warning"]
                for i in errs:
                    st.error(f"**{i.code}** — {i.message}")
                for i in warns:
                    st.warning(f"**{i.code}** — {i.message}")
        except BuildError as e:
            st.error(f"Setup issue: {e}")

    if st.button("Explain infeasibility (L3)", use_container_width=True,
                 help="Soft-relax H1 & H8 and report which constraints had to break."):
        try:
            inst = _build_inst()
        except BuildError as e:
            st.error(f"Setup issue: {e}")
        else:
            with st.spinner("Running relaxed solve…"):
                rep = explain_infeasibility(inst, time_limit_s=30)
            st.write(f"**{rep.status}** · total slack = {rep.total_slack}")
            if rep.note:
                st.caption(rep.note)
            if rep.violations:
                st.dataframe(pd.DataFrame([
                    {"code": v.code, "location": v.location,
                     "amount": v.amount, "message": v.message}
                    for v in rep.violations
                ]), use_container_width=True, hide_index=True)

    st.divider()
    st.caption("Role codes: **AM:X**=AM at station X, **PM:X**=PM, "
               "**OC**=on-call, **EXT**=weekend extended, **WC**=weekend "
               "consultant, **LV**=leave.")


tab_configure, tab_solve, tab_export = st.tabs(
    ["Configure", "Solve & Roster", "Export"]
)

# ================================================================ Configure
with tab_configure:
    ss = st.session_state
    st.subheader("1. When")
    c1, c2 = st.columns(2)
    ss.start_date = c1.date_input("Roster start date", ss.start_date)
    ss.n_days = c2.number_input(
        "Number of days to roster", min_value=1, max_value=90,
        value=int(ss.n_days), step=1)
    end_date = ss.start_date + timedelta(days=int(ss.n_days) - 1)
    st.caption(f"Covers **{format_date(ss.start_date)}** → "
               f"**{format_date(end_date)}** ({ss.n_days} days, "
               f"{ss.n_days/7:.1f} weeks)")
    horizon_dates = dates_for_horizon(ss.start_date, int(ss.n_days))
    kept = [d for d in ss.public_holidays if d in horizon_dates]
    ss.public_holidays = st.multiselect(
        "Public holidays in this period (treated like Sundays)",
        options=horizon_dates, default=kept, format_func=format_date,
    )

    st.divider()
    st.subheader("2. Tier labels & sub-specialties")
    st.caption("Rename the three tiers to match your hospital (e.g. "
               "Registrar / Fellow / Consultant). Internal rules still apply "
               "to the three semantic tiers.")
    tl1, tl2, tl3 = st.columns(3)
    ss.tier_labels["junior"] = tl1.text_input(
        "Label for 'junior' tier", value=ss.tier_labels.get("junior", "Junior"))
    ss.tier_labels["senior"] = tl2.text_input(
        "Label for 'senior' tier", value=ss.tier_labels.get("senior", "Senior"))
    ss.tier_labels["consultant"] = tl3.text_input(
        "Label for 'consultant' tier",
        value=ss.tier_labels.get("consultant", "Consultant"))
    subspecs_text = st.text_input(
        "Sub-specialties (comma-separated, consultants pick one)",
        value=", ".join(ss.subspecs or DEFAULT_SUBSPECS),
        help="Weekend coverage rule (H8) requires 1 consultant per sub-spec.")
    new_subs = [s.strip() for s in subspecs_text.split(",") if s.strip()]
    if new_subs:
        ss.subspecs = new_subs

    st.divider()
    st.subheader("3. Doctors")
    st.caption("Each row = one doctor. **Tier** drives which stations they "
               "can work. **Sub-spec** is required for consultants only. "
               "**Eligible stations** = comma-separated names from the "
               "Stations table. **Previous workload** is the carry-in score "
               "from last month. **FTE** is full-time equivalent (0.5 = "
               "half-time). **Max on-calls** caps their night calls for the "
               "period (leave blank for no cap).")
    current_subspec_options = [""] + list(ss.subspecs or DEFAULT_SUBSPECS)
    edited_doctors = st.data_editor(
        ss.doctors_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("Name", required=True),
            "tier": st.column_config.SelectboxColumn(
                "Tier", options=list(TIERS), required=True),
            "subspec": st.column_config.SelectboxColumn(
                "Sub-spec", options=current_subspec_options,
                help="Required for consultants; leave blank otherwise."),
            "eligible_stations": st.column_config.TextColumn(
                "Eligible stations (comma-separated)",
                help="Station names must match the Stations list below."),
            "prev_workload": st.column_config.NumberColumn(
                "Previous workload",
                min_value=-9999, max_value=9999, step=5, default=0,
                help="Carry-in from prior period."),
            "fte": st.column_config.NumberColumn(
                "FTE", min_value=0.1, max_value=1.0, step=0.1, default=1.0,
                help="Full-time equivalent. 0.5 = half-time doctor who "
                     "should carry roughly half the workload."),
            "max_oncalls": st.column_config.NumberColumn(
                "Max on-calls", min_value=0, max_value=99, step=1,
                help="Hard cap on night calls in this period. Leave blank "
                     "for no cap."),
        },
        key="_editor_doctors",
    )

    st.divider()
    st.subheader("4. Stations")
    with st.expander("Edit stations (defaults cover a typical radiology dept)"):
        st.caption("Sessions: AM, PM, or both. **Required** = how many doctors "
                   "must be assigned to this station per session. "
                   "**Reporting** stations are rotated to avoid back-to-back days.")
        edited_stations = st.data_editor(
            ss.stations_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "name": st.column_config.TextColumn("Name", required=True),
                "sessions": st.column_config.TextColumn(
                    "Sessions", help="AM, PM, or AM,PM"),
                "required_per_session": st.column_config.NumberColumn(
                    "Required", min_value=1),
                "eligible_tiers": st.column_config.TextColumn(
                    "Eligible tiers",
                    help="Comma-separated: junior, senior, consultant"),
                "is_reporting": st.column_config.CheckboxColumn(
                    "Reporting?",
                    help="Reporting desks are spread out to avoid back-to-back."),
            },
            key="_editor_stations",
        )

    st.divider()
    st.subheader("5. Leave, blocks, and preferences")
    known_names_display = [str(n).strip() for n in
                           edited_doctors["name"].dropna().tolist()
                           if str(n).strip()]
    st.caption("One row per block. **Date** is the first day; **End date** "
               "is optional — fill it in for multi-day leave (inclusive range). "
               "**Type**: *Leave* = whole day off. *No on-call* = call block "
               "(doctor can still do AM/PM). *No AM / No PM* = session opt-out. "
               "*Prefer AM / Prefer PM* = soft preference the solver will "
               "honour if it doesn't conflict with harder goals.")
    if known_names_display:
        st.caption(f"Known doctors: {', '.join(known_names_display)}")
    edited_blocks = st.data_editor(
        ss.blocks_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "doctor": st.column_config.TextColumn(
                "Doctor", help="Type the name as it appears in the Doctors table."),
            "date": st.column_config.DateColumn("Date (first day)"),
            "end_date": st.column_config.DateColumn(
                "End date (optional)",
                help="Leave blank for a single day. Range is inclusive."),
            "type": st.column_config.SelectboxColumn(
                "Type", options=list(BLOCK_TYPES), default="Leave"),
        },
        key="_editor_blocks",
    )

    with st.expander("Bulk-add blocks from CSV"):
        st.caption("Paste lines like `Dr A,2026-05-03,2026-05-07,Leave` or "
                   "`Dr B,2026-05-10,,No on-call` (empty end-date = single "
                   "day). One row per line. Headers optional.")
        csv_text = st.text_area("CSV", key="blocks_csv_text",
                                placeholder="Dr A,2026-05-03,2026-05-07,Leave")
        if st.button("Append rows", key="blocks_csv_apply"):
            added = 0
            rows: list[dict] = []
            for line in csv_text.strip().splitlines():
                line = line.strip()
                if not line or line.lower().startswith("doctor,"):
                    continue
                parts = [p.strip() for p in line.split(",")]
                if len(parts) < 3:
                    continue
                name = parts[0]
                try:
                    d_start = date.fromisoformat(parts[1])
                except ValueError:
                    continue
                if len(parts) == 3:
                    d_end = None
                    kind = parts[2] or "Leave"
                else:
                    d_end = date.fromisoformat(parts[2]) if parts[2] else None
                    kind = parts[3] if len(parts) >= 4 and parts[3] else "Leave"
                rows.append({"doctor": name, "date": d_start,
                             "end_date": d_end, "type": kind})
                added += 1
            if rows:
                new_df = pd.concat(
                    [ss.blocks_df, pd.DataFrame(rows)], ignore_index=True)
                ss.blocks_df = new_df
                st.session_state["blocks_csv_text"] = ""
                st.success(f"Appended {added} row(s). Scroll up to verify.")
                st.rerun()
            elif csv_text.strip():
                st.warning("No valid rows parsed. Format: "
                           "`doctor,start_date,end_date_or_empty,type`.")

    st.divider()
    st.subheader("6. Manual overrides (lock specific assignments)")
    st.caption("Force a specific role on a specific day. Treated as a **hard** "
               "constraint — the solver must honour it. Use this to lock parts "
               "of the roster and re-solve around them. " + OVERRIDE_ROLES_HELP)
    edited_overrides = st.data_editor(
        ss.overrides_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "doctor": st.column_config.TextColumn("Doctor"),
            "date": st.column_config.DateColumn("Date"),
            "role": st.column_config.TextColumn(
                "Role", help=OVERRIDE_ROLES_HELP),
        },
        key="_editor_overrides",
    )

    st.divider()
    st.subheader("7. Rules for the roster")
    st.caption("Turn these on or off to change what the solver is allowed to do. "
               "Each rule's help text explains what it means.")
    cc1, cc2 = st.columns(2)
    with cc1:
        st.checkbox(
            "Cap on-call frequency (no more than once every N days)",
            key="h4_enabled",
            help="Any N-day window has at most one on-call per doctor."
        )
        st.number_input(
            "N (days) for the on-call cap",
            min_value=2, max_value=14, key="h4_gap",
            help="3 = 'no more than one on-call every 3 days'.")
        st.checkbox(
            "Day off after a night on-call (post-call off)",
            key="h5_enabled",
            help="A doctor who is on call overnight is off the following day.")
        st.checkbox(
            "Seniors on-call get the whole day off",
            key="h6_enabled",
            help="On their on-call day, seniors do no AM or PM station work.")
    with cc2:
        st.checkbox(
            "Juniors on-call work the PM session",
            key="h7_enabled",
            help="Juniors cover a PM station on their on-call day.")
        st.checkbox(
            "Weekend coverage (extended-duty + on-call + consultant-on-call)",
            key="h8_enabled",
            help="Saturdays and Sundays must have: 1 junior EXT, 1 senior EXT, "
                 "1 junior on-call, 1 senior on-call, 1 consultant per sub-spec.")
        st.checkbox(
            "Day off in lieu after weekend extended-duty",
            key="h9_enabled",
            help="If a doctor works weekend EXT, they get a Friday-before or "
                 "Monday-after off.")
        st.checkbox(
            "Every doctor has a duty every weekday (unless excused)",
            key="h11_enabled",
            help="Excuses: leave, post-call, day-in-lieu. Soft constraint — "
                 "penalty per day a doctor has no duty. Controls idle time.")
    st.checkbox(
        "Also roster AM/PM stations on weekends",
        key="weekend_am_pm",
        help="Off by default. Weekends are usually covered by EXT + on-call + "
             "weekend-consultant only.")

    st.divider()
    st.subheader("8. Hours per shift")
    st.caption("Used to compute each doctor's **hours per week** in the results. "
               "Does **not** affect the solver — only the report. Adjust these "
               "to match your hospital's shift lengths.")
    h1, h2, h3, h4 = st.columns(4)
    h1.number_input("Weekday AM (hours)", min_value=0.0, max_value=24.0,
                    step=0.5, key="h_weekday_am")
    h1.number_input("Weekday PM (hours)", min_value=0.0, max_value=24.0,
                    step=0.5, key="h_weekday_pm")
    h2.number_input("Weekend AM (hours)", min_value=0.0, max_value=24.0,
                    step=0.5, key="h_weekend_am")
    h2.number_input("Weekend PM (hours)", min_value=0.0, max_value=24.0,
                    step=0.5, key="h_weekend_pm")
    h3.number_input("Weekday on-call (hours)", min_value=0.0, max_value=24.0,
                    step=1.0, key="h_weekday_oncall")
    h3.number_input("Weekend on-call (hours)", min_value=0.0, max_value=24.0,
                    step=1.0, key="h_weekend_oncall")
    h4.number_input("Weekend extended (hours)", min_value=0.0, max_value=24.0,
                    step=1.0, key="h_weekend_ext")
    h4.number_input("Weekend consultant (hours)", min_value=0.0, max_value=24.0,
                    step=1.0, key="h_weekend_consult")

    st.divider()
    st.subheader("9. How 'fairness' is measured")
    st.caption("These are the **workload weights** — they turn each assignment "
               "into a number, which is then summed into a workload score per "
               "doctor. The solver tries to spread this score evenly across "
               "doctors in the same tier. Weekend roles are weighted more so "
               "weekend call counts as more work than weekday call.")
    ww1, ww2, ww3 = st.columns(3)
    ww1.number_input("Weekday session", min_value=0, max_value=100,
                     key="wl_wd_session")
    ww1.number_input("Weekend session", min_value=0, max_value=100,
                     key="wl_we_session")
    ww2.number_input("Weekday on-call", min_value=0, max_value=100,
                     key="wl_wd_oncall")
    ww2.number_input("Weekend on-call", min_value=0, max_value=100,
                     key="wl_we_oncall")
    ww3.number_input("Weekend extended", min_value=0, max_value=100,
                     key="wl_ext")
    ww3.number_input("Weekend consultant", min_value=0, max_value=100,
                     key="wl_wconsult")

    st.divider()
    st.subheader("10. Solver priorities (advanced)")
    st.caption("How hard the solver tries to achieve each goal. Higher = more "
               "important. Set to 0 to turn a goal off entirely. The defaults "
               "are tuned; you rarely need to touch these.")
    sc1, sc2 = st.columns(2)
    sc1.number_input(
        "Fairness: balance weighted workload across each tier",
        min_value=0, max_value=1000, key="w_workload",
        help="The primary fairness term — uses the weights from section 6.")
    sc1.number_input(
        "Penalty per day a doctor has no duty",
        min_value=0, max_value=1000, key="w_idle",
        help="Drives the 'every doctor has a duty every weekday' rule. "
             "High value = forces full utilisation.")
    sc1.number_input(
        "Balance raw session counts (secondary)",
        min_value=0, max_value=1000, key="w_sessions")
    sc2.number_input(
        "Balance on-call counts (secondary)",
        min_value=0, max_value=1000, key="w_oncall")
    sc2.number_input(
        "Balance weekend-duty counts (secondary)",
        min_value=0, max_value=1000, key="w_weekend")
    sc2.number_input(
        "Spread out reporting-desk duty (no back-to-back days)",
        min_value=0, max_value=1000, key="w_report")
    sc2.number_input(
        "Honour positive session preferences",
        min_value=0, max_value=1000, key="w_pref",
        help="Cost per unmet 'Prefer AM/Prefer PM' wish.")

    # END of Configure tab — single commit point for editable tables.
    ss.doctors_df = edited_doctors
    ss.stations_df = edited_stations
    ss.blocks_df = edited_blocks
    ss.overrides_df = edited_overrides


# ============================================================ Solve & Roster
def _solve_worker(inst, time_limit_s, weights, wl_weights, cfg,
                  num_workers, feasibility_only, q, stop_event):
    def on_event(e):
        q.put(("event", e))
    try:
        result = solve(
            inst,
            time_limit_s=time_limit_s,
            weights=weights,
            workload_weights=wl_weights,
            constraints=cfg,
            num_workers=num_workers,
            feasibility_only=feasibility_only,
            on_intermediate=on_event,
            snapshot_assignments=True,
            stop_event=stop_event,
        )
        q.put(("done", result))
    except Exception as exc:  # pragma: no cover
        q.put(("error", exc))


def _drain_solve_queue() -> None:
    """Pull every event currently on the queue into session_state."""
    ss = st.session_state
    q: Queue = ss.solve_queue
    while True:
        try:
            kind, payload = q.get_nowait()
        except Empty:
            return
        if kind == "event":
            ss.solve_events.append(payload)
        elif kind == "done":
            ss.last_result = payload
            ss.last_events = list(ss.solve_events)
            ss.solving = False
        elif kind == "error":
            ss.solve_error = payload
            ss.solving = False


with tab_solve:
    ss = st.session_state
    ss.setdefault("solving", False)
    ss.setdefault("solve_events", [])
    ss.setdefault("solve_error", None)

    # -------------------------------------------------------- Buttons row
    if ss.solving:
        bc1, bc2 = st.columns([1, 3])
        stop_btn = bc1.button(
            "⏹ Stop solve (accept current best)", type="primary",
            use_container_width=True,
            help="Signals the solver to exit after its current solution. "
                 "Returns with FEASIBLE status if any solution was found.")
        if stop_btn:
            if "solve_stop" in ss:
                ss.solve_stop.set()
            bc2.info("Stop signal sent — waiting for solver to exit…")
    else:
        bc1, bc2 = st.columns([1, 1])
        solve_btn = bc1.button("▶ Solve", type="primary", use_container_width=True)
        clear_btn = bc2.button("Clear last result", use_container_width=True)

        if clear_btn:
            for k in ("last_result", "last_inst", "last_events",
                      "last_doctor_names", "last_wl_weights",
                      "solve_events", "solve_error"):
                ss.pop(k, None)
            st.rerun()

        if solve_btn:
            try:
                inst = _build_inst()
                names = doctor_name_map(ss.doctors_df, inst)
            except BuildError as e:
                st.error(f"Setup issue: {e}")
            else:
                ss.solve_queue = Queue()
                ss.solve_stop = threading.Event()
                ss.solve_events = []
                ss.solve_error = None
                ss.last_inst = inst
                ss.last_doctor_names = names
                ss.last_wl_weights = _current_workload_weights()
                ss.last_hours = _current_hours()
                ss.last_result = None
                worker = threading.Thread(
                    target=_solve_worker,
                    args=(inst, float(ss.time_limit),
                          _current_weights(), _current_workload_weights(),
                          _current_constraints(),
                          int(ss.num_workers),
                          bool(ss.feasibility_only),
                          ss.solve_queue, ss.solve_stop),
                    daemon=True,
                )
                worker.start()
                ss.solve_thread = worker
                ss.solving = True
                st.rerun()

    # -------------------------------------------------------- Live progress
    if ss.solving:
        _drain_solve_queue()
        events = ss.solve_events
        if events:
            latest = events[-1]
            obj = latest.get("objective")
            bnd = latest.get("best_bound")
            gap = None
            if obj and bnd is not None and obj > 0:
                gap = max(0.0, (obj - bnd) / obj * 100)
            st.info(
                f"Solving… {latest['wall_s']:.1f}s — "
                f"**{len(events)}** improving solution(s), obj **{obj}** "
                f"(bound {bnd})"
                + (f", gap **{gap:.1f}%**" if gap is not None else "")
            )

            fig, _ = plots.convergence(events)
            st.plotly_chart(fig, use_container_width=True)

            # --- LIVE ROSTER: render the latest snapshot's doctor × date grid.
            if latest.get("assignments") and "last_inst" in ss:
                st.subheader(f"Current best roster — #{len(events)} (live)")
                st.caption("🟢 station work  ·  🟣 on-call  ·  🔵 weekend EXT/WC  "
                           "·  ⚪ leave  ·  🟡 no duty. "
                           "Updates each time the solver finds an improving "
                           "solution. Click **Stop** above to accept this one.")
                grid = _snapshot_to_role_grid(
                    ss.last_inst, latest["assignments"], ss.last_doctor_names)
                st.dataframe(_style_roster_grid(grid), use_container_width=True,
                             height=min(500, 40 + 28 * len(grid)))

                # Live fairness peek — headline table only (breakdown skipped
                # during solve to save render time).
                hours = ss.get("last_hours", HoursConfig())
                head_df, _ = _workload_tables(
                    ss.last_inst, latest["assignments"],
                    ss.last_doctor_names, ss.last_wl_weights, hours)
                with st.expander("Workload peek (current best)"):
                    st.dataframe(_style_headline(head_df),
                                 use_container_width=True, hide_index=True)

            with st.expander("Intermediate solutions log"):
                sol_rows = []
                for i, e in enumerate(events):
                    row = {"#": i + 1, "t (s)": round(e["wall_s"], 2),
                           "objective": e["objective"], "bound": e["best_bound"]}
                    for k, v in (e.get("components") or {}).items():
                        row[k] = v
                    sol_rows.append(row)
                st.dataframe(pd.DataFrame(sol_rows),
                             use_container_width=True, hide_index=True)
        else:
            st.info("Solving… waiting for first solution.")

        # Schedule the next rerun so the UI keeps updating. The sleep gives
        # the user a chance to click Stop between reruns (Streamlit buttons
        # only fire on rerun boundaries).
        if ss.solving:
            if ss.solve_thread.is_alive():
                time.sleep(POLL_INTERVAL_S)
                st.rerun()
            else:
                # Thread exited; one more drain to collect any tail events.
                _drain_solve_queue()
                ss.solving = False
                st.rerun()

    # -------------------------------------------------------- Final display
    if (not ss.solving) and ss.get("solve_error") is not None:
        st.error(f"Solve raised: {ss.solve_error!r}")

    if (not ss.solving) and "last_result" in ss and ss.last_result is not None:
        result = st.session_state.last_result
        inst = st.session_state.last_inst
        events = st.session_state.last_events
        names = st.session_state.last_doctor_names
        wl_weights = st.session_state.last_wl_weights
        hours = st.session_state.get("last_hours", HoursConfig())

        has_sol = result.status in ("OPTIMAL", "FEASIBLE")
        idle_total = 0
        has_cov_viol = False
        tier_hours_avg: dict[str, float] = {}
        if has_sol:
            idle_total = sum(
                count_idle_weekdays(inst, result.assignments).values())
            sm = solution_metrics(inst, result)
            has_cov_viol = bool(sm.get("coverage_violations"))
            hrs = hours_per_doctor(inst, result.assignments, hours)
            for tier in ("junior", "senior", "consultant"):
                tier_doctors = [d.id for d in inst.doctors if d.tier == tier]
                if tier_doctors:
                    avg = sum(hrs.get(did, {}).get("hours_per_week", 0.0)
                              for did in tier_doctors) / len(tier_doctors)
                    tier_hours_avg[tier] = avg

        severity, message = _verdict(result, events, idle_total, has_cov_viol,
                                     tier_hours_avg)
        banner = {"success": st.success, "warning": st.warning,
                  "error": st.error, "info": st.info}[severity]
        banner(message)

        # Metric strip — labels use plain English.
        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Status", result.status)
        mc2.metric("Solve time", f"{result.wall_time_s:.2f}s")
        mc3.metric("Days without duty",
                   idle_total if has_sol else "—",
                   help="Total doctor-weekdays where the doctor had no role "
                        "and was not on leave / post-call / lieu.")
        tier_label_map = ss.get("tier_labels", DEFAULT_TIER_LABELS)
        mc4.metric(
            "Avg hours / week (by tier)",
            (" · ".join(
                f"{tier_label_map.get(t, t)[:3]} {h:.0f}h"
                for t, h in tier_hours_avg.items())
             if tier_hours_avg else "—"),
            help="First three letters of each tier label + average hours per "
                 "week. A big gap across tiers usually means station "
                 "eligibility or required_per_session needs tuning."
        )
        mc5.metric("Penalty score (lower = better)",
                   f"{result.objective:.0f}" if result.objective is not None else "—")

        if has_sol:
            snap_options = ["Final (best)"]
            for i, e in enumerate(events):
                if e.get("assignments"):
                    snap_options.append(f"#{i+1} — t={e['wall_s']:.1f}s, obj={e['objective']}")
            pick = st.selectbox(
                "Which roster to view", snap_options, index=0,
                help="Pick any improving solution the solver found during search.")
            if pick == "Final (best)":
                snap = result.assignments
            else:
                idx = int(pick.split("—", 1)[0].strip().lstrip("#")) - 1
                snap = events[idx]["assignments"]

            st.subheader("Roster — doctor × date")
            st.caption("🟢 station work  ·  🟣 on-call  ·  🔵 weekend EXT/WC  "
                       "·  ⚪ leave  ·  🟡 no duty")
            grid_df = _snapshot_to_role_grid(inst, snap, names)
            st.dataframe(_style_roster_grid(grid_df),
                         use_container_width=True,
                         height=min(600, 40 + 28 * len(grid_df)))

            lock_col, _ = st.columns([1, 3])
            if lock_col.button(
                "📌 Copy this roster to overrides",
                help="Pre-fills the 'Manual overrides' table in Configure "
                     "with every current assignment, so you can delete the "
                     "specific rows you want to change and re-solve.",
            ):
                override_rows: list[dict] = []
                d_start = st.session_state.start_date
                for (did, day, st_name, sess), v in snap.get("stations", {}).items():
                    if v:
                        override_rows.append({
                            "doctor": names.get(did, f"Dr #{did}"),
                            "date": d_start + timedelta(days=day),
                            "role": f"STATION_{st_name}_{sess}",
                        })
                for (did, day), v in snap.get("oncall", {}).items():
                    if v:
                        override_rows.append({
                            "doctor": names.get(did, f"Dr #{did}"),
                            "date": d_start + timedelta(days=day),
                            "role": "ONCALL",
                        })
                for (did, day), v in snap.get("ext", {}).items():
                    if v:
                        override_rows.append({
                            "doctor": names.get(did, f"Dr #{did}"),
                            "date": d_start + timedelta(days=day),
                            "role": "EXT",
                        })
                for (did, day), v in snap.get("wconsult", {}).items():
                    if v:
                        override_rows.append({
                            "doctor": names.get(did, f"Dr #{did}"),
                            "date": d_start + timedelta(days=day),
                            "role": "WCONSULT",
                        })
                st.session_state.overrides_df = pd.DataFrame(override_rows)
                st.success(f"Copied {len(override_rows)} rows to overrides. "
                           "Go to Configure → section 6 to edit, then re-solve.")

            with st.expander("Alternative views"):
                view_cols = st.columns(3)
                if view_cols[0].toggle("Station × date", value=False, key="toggle_station_view"):
                    st.caption("Rows are role / station · session; cells list "
                               "doctors covering that slot.")
                    sv = _station_view(inst, snap, names)
                    st.dataframe(sv, use_container_width=True,
                                 height=min(500, 40 + 28 * len(sv)))
                if view_cols[1].toggle("Per-doctor calendar", value=False, key="toggle_doc_cal"):
                    doc_pick = st.selectbox(
                        "Doctor", sorted(names.values()),
                        key="doc_cal_pick")
                    if doc_pick:
                        cal = _per_doctor_calendar(inst, snap, names, doc_pick)
                        st.dataframe(_style_roster_grid(cal),
                                     use_container_width=True)
                if view_cols[2].toggle("Today's roster", value=False, key="toggle_today"):
                    default_day = st.session_state.start_date
                    picked = st.date_input(
                        "Date", default_day,
                        min_value=st.session_state.start_date,
                        max_value=(st.session_state.start_date
                                   + timedelta(days=int(st.session_state.n_days) - 1)),
                        key="today_pick")
                    tdf = _today_summary(inst, snap, names, picked)
                    if tdf.empty:
                        st.info("No assignments on that day.")
                    else:
                        st.dataframe(tdf, use_container_width=True, hide_index=True)

            with st.expander("Diff this snapshot against another"):
                other_options = ["(none)"]
                for i, e in enumerate(events):
                    if e.get("assignments"):
                        other_options.append(f"#{i+1} — t={e['wall_s']:.1f}s, obj={e['objective']}")
                other_options.append("Final")
                other_pick = st.selectbox(
                    "Compare against",
                    [o for o in other_options if o != pick],
                    key="diff_pick")
                if other_pick and other_pick != "(none)":
                    if other_pick == "Final":
                        other_snap = result.assignments
                    else:
                        oi = int(other_pick.split("—", 1)[0].strip().lstrip("#")) - 1
                        other_snap = events[oi]["assignments"]
                    diff = _diff_snapshots(inst, snap, other_snap, names)
                    changed = int((diff != "").sum().sum())
                    st.caption(f"{changed} cell(s) differ. Yellow = changed.")
                    st.dataframe(_style_diff(diff), use_container_width=True,
                                 height=min(500, 40 + 28 * len(diff)))

            head_df, break_df = _workload_tables(
                inst, snap, names, wl_weights, hours)

            st.subheader("Per-doctor workload — headline")
            st.caption(
                "**Workload score** = weighted sum of this doctor's "
                "assignments + their previous-period carry-in. "
                "**Δ vs. tier median** highlights fairness: red means this "
                "doctor is doing more than the tier median; blue means less. "
                "**Hours / week** is computed from the shift-length settings "
                "in the Configure tab."
            )
            st.dataframe(_style_headline(head_df),
                         use_container_width=True, hide_index=True)

            with st.expander("Workload — full breakdown by shift type"):
                st.caption("All the raw counts. 'Total (with carry-in)' should "
                           "match the headline **Workload score**.")
                st.dataframe(break_df, use_container_width=True, hide_index=True)

            with st.expander("Advanced analytics (convergence, penalty breakdown, heatmaps)"):
                fig, md = plots.convergence(events, objective=result.objective)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(md)

                fig, md = plots.penalty_breakdown(events)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(md)

                fig, md = plots.workload_histogram(inst, result)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(md)

                fig, md = plots.oncall_spacing(inst, result)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(md)

                fig, md = plots.coverage_heatmap(inst, result)
                st.plotly_chart(fig, use_container_width=True)
                st.caption(md)
    elif (not ss.solving) and ss.get("solve_error") is None \
            and ss.get("last_result") is None:
        st.info("Configure on the Configure tab, then click ▶ Solve above.")

# ================================================================ Export
with tab_export:
    if "last_result" not in st.session_state:
        st.info("Run a solve first.")
    else:
        result = st.session_state.last_result
        inst = st.session_state.last_inst
        names = st.session_state.last_doctor_names

        if result.status not in ("OPTIMAL", "FEASIBLE"):
            st.info("No roster to export.")
        else:
            start_date = st.session_state.start_date
            def _d(day): return (start_date + timedelta(days=day)).isoformat()

            payload_rows: list[dict] = []
            for key, v in result.assignments.get("stations", {}).items():
                if not v:
                    continue
                did, day, sname, sess = key
                payload_rows.append({
                    "doctor": names.get(did, f"Dr #{did}"),
                    "date": _d(day),
                    "role": f"STATION_{sname}_{sess}",
                })
            for (did, day), v in result.assignments.get("oncall", {}).items():
                if v:
                    payload_rows.append({"doctor": names.get(did, f"Dr #{did}"),
                                         "date": _d(day), "role": "ONCALL"})
            for (did, day), v in result.assignments.get("ext", {}).items():
                if v:
                    payload_rows.append({"doctor": names.get(did, f"Dr #{did}"),
                                         "date": _d(day), "role": "WEEKEND_EXT"})
            for (did, day), v in result.assignments.get("wconsult", {}).items():
                if v:
                    payload_rows.append({"doctor": names.get(did, f"Dr #{did}"),
                                         "date": _d(day), "role": "WEEKEND_CONSULT"})

            meta = {
                "status": result.status,
                "objective": result.objective,
                "wall_time_s": round(result.wall_time_s, 2),
                "first_feasible_s": (round(result.first_feasible_s, 2)
                                     if result.first_feasible_s is not None else None),
                "start_date": start_date.isoformat(),
                "n_days": inst.n_days,
                "penalty_components": result.penalty_components,
            }

            st.download_button(
                "Download roster (JSON)",
                data=json.dumps({"meta": meta, "assignments": payload_rows}, indent=2),
                file_name="roster.json",
                mime="application/json",
            )

            csv_buf = io.StringIO()
            pd.DataFrame(payload_rows).to_csv(csv_buf, index=False)
            st.download_button("Download roster (CSV)",
                               data=csv_buf.getvalue(),
                               file_name="roster.csv", mime="text/csv")

            # Print-friendly HTML: browser "Save as PDF" from the preview.
            st.divider()
            st.subheader("Print-friendly HTML")
            st.caption("Download the HTML, open it in your browser, and use "
                       "**File → Print → Save as PDF** for a paper-ready roster.")
            grid_df = _snapshot_to_role_grid(inst, result.assignments, names)
            meta_html = (
                f"<h1>Roster — {format_date(start_date)} to "
                f"{format_date(start_date + timedelta(days=inst.n_days-1))}</h1>"
                f"<p><b>Status:</b> {result.status} · "
                f"<b>Penalty:</b> {result.objective or 0:.0f}</p>"
            )
            style = """
<style>
body { font-family: -apple-system, 'Segoe UI', Arial, sans-serif; margin: 24px; color: #111; }
h1 { margin-bottom: 4px; }
table { border-collapse: collapse; width: 100%; font-size: 10pt; }
th, td { border: 1px solid #ccc; padding: 4px 6px; text-align: left; }
th { background: #f2f2f2; }
td.lv { background: #e6e6e6; color: #666; }
td.oc { background: #e6d0f5; }
td.ext, td.wc { background: #cfe9f3; }
td.work { background: #d7f0dd; }
td.idle { background: #ffe6b3; }
@media print { body { margin: 0; } table { page-break-inside: auto; } }
</style>
"""
            rows_html = []
            for doctor_name in grid_df.index:
                cells = [f"<td><b>{doctor_name}</b></td>"]
                for col in grid_df.columns:
                    val = str(grid_df.at[doctor_name, col]).strip()
                    cls = "idle"
                    if val == "LV":
                        cls = "lv"
                    elif "OC" in val.split():
                        cls = "oc"
                    elif ("EXT" in val.split()) or ("WC" in val.split()):
                        cls = "ext"
                    elif "AM:" in val or "PM:" in val:
                        cls = "work"
                    cells.append(f'<td class="{cls}">{val}</td>')
                rows_html.append("<tr>" + "".join(cells) + "</tr>")
            header_row = (
                "<tr><th>Doctor</th>"
                + "".join(f"<th>{c}</th>" for c in grid_df.columns)
                + "</tr>"
            )
            table = f"<table>{header_row}{''.join(rows_html)}</table>"
            html = f"<!doctype html><html><head><meta charset='utf-8'>" \
                   f"<title>Roster</title>{style}</head><body>" \
                   f"{meta_html}{table}</body></html>"
            st.download_button(
                "📄 Download print-friendly HTML",
                data=html, file_name=f"roster_{start_date.isoformat()}.html",
                mime="text/html",
            )
