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


BLOCK_TYPES = ("Leave", "No on-call", "No AM", "No PM")


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
            "type": pd.Series(dtype="object"),
        })
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
def _build_inst():
    ss = st.session_state
    block_entries: list[tuple[str, date, str]] = []
    for _, row in ss.blocks_df.iterrows():
        doctor = row.get("doctor")
        d = row.get("date")
        kind = row.get("type") or "Leave"
        if doctor is None or d is None:
            continue
        if pd.isna(doctor) or (hasattr(d, "__class__") and pd.isna(d)):
            continue
        if isinstance(d, str):
            try:
                d = date.fromisoformat(d)
            except ValueError:
                continue
        name = str(doctor).strip()
        if not name:
            continue
        block_entries.append((name, d, str(kind)))

    return build_instance(
        start_date=ss.start_date,
        n_days=int(ss.n_days),
        doctors_df=ss.doctors_df,
        stations_df=ss.stations_df,
        block_entries=block_entries,
        public_holidays=list(ss.public_holidays or []),
        weekend_am_pm_enabled=bool(ss.weekend_am_pm),
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
            "Tier": d.tier,
            "Sub-spec": subspec,
            "Workload score": b["score"],
            "Δ vs. tier median": 0.0,   # filled below
            "Hours / week": hrs,
            "Leave days": b["leave_days"],
            "Days without duty": idle,
        })
        breakdown_rows.append({
            "Doctor": nm,
            "Tier": d.tier,
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
            mask = headline["Tier"] == tier
            if mask.sum() < 2:
                continue
            med = headline.loc[mask, "Workload score"].median()
            headline.loc[mask, "Δ vs. tier median"] = \
                headline.loc[mask, "Workload score"] - med
    return headline, pd.DataFrame(breakdown_rows)


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


def _verdict(result, events, idle_total: int, has_coverage_viol: bool) -> tuple[str, str]:
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
        issues.append(f"{idle_total} idle doctor-weekday(s) — capacity may be tight "
                      "(or raise the 'Idle weekday' penalty if you want zero).")
    if has_coverage_viol:
        issues.append("coverage violations detected (solver bug — report this)")
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
        return ("warning", head + " " + " · ".join(issues))
    return ("success", head)


# ========================================================== App shell
st.set_page_config(page_title="Healthcare Roster Scheduler", layout="wide")
_ensure_defaults()

st.title("Healthcare Roster Scheduler")
st.caption("Configure, solve, review. Constraint spec: `docs/CONSTRAINTS.md`.")

# --------------------------------------------------------------------- Sidebar
with st.sidebar:
    st.subheader("Solver settings")
    st.slider("Time limit (s)", 5, 600, key="time_limit")
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
    st.subheader("2. Doctors")
    st.caption("Each row = one doctor. **Tier** drives which stations they can "
               "work. **Sub-spec** is required for consultants only. "
               "**Eligible stations** are comma-separated names from the "
               "Stations table. **Previous workload** is their carry-in "
               "score from last month — higher means they did more last "
               "period, so they'll get less this period.")
    edited_doctors = st.data_editor(
        ss.doctors_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("Name", required=True),
            "tier": st.column_config.SelectboxColumn(
                "Tier", options=list(TIERS), required=True),
            "subspec": st.column_config.SelectboxColumn(
                "Sub-spec", options=list(SUBSPEC_CHOICES),
                help="Required for consultants; leave blank for juniors/seniors."),
            "eligible_stations": st.column_config.TextColumn(
                "Eligible stations (comma-separated)",
                help="Station names must match the Stations list below."),
            "prev_workload": st.column_config.NumberColumn(
                "Previous workload",
                min_value=-9999, max_value=9999, step=5, default=0,
                help="Carry-in from prior period. Defaults 0. Higher = "
                     "already did more last period → gets less this period."),
        },
        key="_editor_doctors",
    )

    with st.expander("Stations (advanced — the default list covers a typical "
                     "radiology department)"):
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
    st.subheader("3. Leave, blocks, and preferences")
    known_names_display = [str(n).strip() for n in
                           edited_doctors["name"].dropna().tolist()
                           if str(n).strip()]
    st.caption("One row per block. **Leave** = full day off (no work at all). "
               "**No on-call** = doctor can still do AM/PM work but won't get "
               "night call. **No AM / No PM** = doctor opts out of that "
               "session only. Type the doctor's name exactly as it appears "
               "above.")
    if known_names_display:
        st.caption(f"Known doctors: {', '.join(known_names_display)}")
    edited_blocks = st.data_editor(
        ss.blocks_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "doctor": st.column_config.TextColumn(
                "Doctor", help="Type the name as it appears in the Doctors table."),
            "date": st.column_config.DateColumn("Date"),
            "type": st.column_config.SelectboxColumn(
                "Type", options=list(BLOCK_TYPES), default="Leave",
                help="Leave = whole day off. No on-call = call block. "
                     "No AM / No PM = session block."),
        },
        key="_editor_blocks",
    )

    st.divider()
    st.subheader("4. Rules for the roster")
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
    st.subheader("5. Hours per shift")
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
    st.subheader("6. How 'fairness' is measured")
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
    st.subheader("7. Solver priorities (advanced)")
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

    # END of Configure tab — single commit point for editable tables.
    # This is the fix for the "edit two cells, only one saves" bug: we
    # reassign to session_state ONCE per rerun, after all editors rendered,
    # so no editor is mid-render when another's state updates.
    ss.doctors_df = edited_doctors
    ss.stations_df = edited_stations
    ss.blocks_df = edited_blocks


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
                st.caption("Updates each time the solver finds an improving "
                           "solution. Click **Stop** above to accept this one.")
                grid = _snapshot_to_role_grid(
                    ss.last_inst, latest["assignments"], ss.last_doctor_names)
                st.dataframe(grid, use_container_width=True,
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
        if has_sol:
            idle_total = sum(
                count_idle_weekdays(inst, result.assignments).values())
            sm = solution_metrics(inst, result)
            has_cov_viol = bool(sm.get("coverage_violations"))

        severity, message = _verdict(result, events, idle_total, has_cov_viol)
        banner = {"success": st.success, "warning": st.warning,
                  "error": st.error, "info": st.info}[severity]
        banner(message)

        # Metric strip — labels use plain English.
        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Status", result.status)
        mc2.metric("Solve time", f"{result.wall_time_s:.2f}s")
        mc3.metric("First valid roster found at",
                   f"{(result.first_feasible_s or 0):.2f}s" if result.first_feasible_s else "—")
        mc4.metric("Penalty score (lower = better)",
                   f"{result.objective:.0f}" if result.objective is not None else "—")
        mc5.metric("Days without duty",
                   idle_total if has_sol else "—",
                   help="Total doctor-weekdays where the doctor had no role "
                        "and was not on leave / post-call / lieu.")

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
            grid_df = _snapshot_to_role_grid(inst, snap, names)
            st.dataframe(grid_df, use_container_width=True,
                         height=min(600, 40 + 28 * len(grid_df)))

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
