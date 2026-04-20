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
    problem_metrics,
    solution_metrics,
    solve_metrics,
    workload_breakdown,
)
from scheduler.model import ConstraintConfig, Weights, WorkloadWeights, solve
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


def _ensure_defaults() -> None:
    ss = st.session_state
    if "doctors_df" not in ss:
        ss.doctors_df = default_doctors_df(20)
    if "stations_df" not in ss:
        ss.stations_df = default_stations_df()
    if "leave_df" not in ss:
        ss.leave_df = pd.DataFrame({"doctor": pd.Series(dtype="object"),
                                    "date": pd.Series(dtype="object")})
    ss.setdefault("start_date", _next_monday(date.today()))
    ss.setdefault("n_days", 21)
    ss.setdefault("public_holidays", [])
    # Objective weights (Weights dataclass).
    ss.setdefault("w_workload", 40)
    ss.setdefault("w_sessions", 5)
    ss.setdefault("w_oncall", 10)
    ss.setdefault("w_weekend", 10)
    ss.setdefault("w_report", 5)
    ss.setdefault("w_idle", 100)
    # Workload weights (WorkloadWeights dataclass).
    ss.setdefault("wl_wd_session", 10)
    ss.setdefault("wl_we_session", 15)
    ss.setdefault("wl_wd_oncall", 20)
    ss.setdefault("wl_we_oncall", 35)
    ss.setdefault("wl_ext", 20)
    ss.setdefault("wl_wconsult", 25)
    # Constraint toggles (ConstraintConfig).
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
    leave_entries: list[tuple[str, date]] = []
    for _, row in ss.leave_df.iterrows():
        doctor = row.get("doctor")
        d = row.get("date")
        if doctor is None or d is None:
            continue
        if pd.isna(doctor) or (hasattr(d, "__class__") and pd.isna(d)):
            continue
        if isinstance(d, str):
            try:
                d = date.fromisoformat(d)
            except ValueError:
                continue
        leave_entries.append((str(doctor), d))

    return build_instance(
        start_date=ss.start_date,
        n_days=int(ss.n_days),
        doctors_df=ss.doctors_df,
        stations_df=ss.stations_df,
        leave_entries=leave_entries,
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


def _workload_table(inst, assignments: dict, names: dict[int, str],
                    wl_weights: WorkloadWeights) -> pd.DataFrame:
    """Rich per-doctor workload table with weighted score + distance from tier median."""
    breakdown = workload_breakdown(inst, assignments, wl_weights)
    idle_counts = count_idle_weekdays(inst, assignments)
    rows: list[dict] = []
    for d in inst.doctors:
        b = breakdown[d.id]
        rows.append({
            "Doctor": names.get(d.id, f"Dr #{d.id}"),
            "Tier": d.tier,
            "Sub-spec": d.subspec or "",
            "Wd sess": b["weekday_sessions"],
            "We sess": b["weekend_sessions"],
            "Wd call": b["weekday_oncall"],
            "We call": b["weekend_oncall"],
            "EXT": b["ext"],
            "WC": b["wconsult"],
            "Leave": b["leave_days"],
            "Idle wd": idle_counts.get(d.id, 0),
            "Prev": b["prev_workload"],
            "Score": b["score"],
        })
    df = pd.DataFrame(rows)
    # Distance from tier median: colour the "Score" column.
    if not df.empty:
        df["Δ median"] = 0.0
        for tier in ("junior", "senior", "consultant"):
            mask = df["Tier"] == tier
            if mask.sum() < 2:
                continue
            median_score = df.loc[mask, "Score"].median()
            df.loc[mask, "Δ median"] = df.loc[mask, "Score"] - median_score
    return df


def _style_workload(df: pd.DataFrame):
    if df.empty or "Δ median" not in df.columns:
        return df
    max_abs = max(df["Δ median"].abs().max(), 1)

    def _color(val):
        try:
            v = float(val)
        except (TypeError, ValueError):
            return ""
        # Red = over median (overworked), Blue = under median (underworked).
        intensity = min(1.0, abs(v) / max_abs)
        if v > 0:
            return f"background-color: rgba(220, 50, 50, {0.15 + 0.35*intensity:.2f})"
        if v < 0:
            return f"background-color: rgba(50, 120, 220, {0.15 + 0.35*intensity:.2f})"
        return ""

    styler = df.style
    # pandas ≥ 2.1 renamed Styler.applymap to Styler.map.
    mapfn = getattr(styler, "map", None) or styler.applymap
    return mapfn(_color, subset=["Δ median"]).format({
        "Δ median": "{:+.1f}", "Score": "{:.0f}",
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
    st.subheader("When")
    c1, c2 = st.columns(2)
    st.session_state.start_date = c1.date_input("Start date", st.session_state.start_date)
    st.session_state.n_days = c2.number_input(
        "Horizon (days)", min_value=1, max_value=90, value=int(st.session_state.n_days), step=1)
    end_date = st.session_state.start_date + timedelta(days=int(st.session_state.n_days) - 1)
    st.caption(f"Covers **{format_date(st.session_state.start_date)}** → "
               f"**{format_date(end_date)}** ({st.session_state.n_days} days)")
    horizon_dates = dates_for_horizon(st.session_state.start_date, int(st.session_state.n_days))
    kept = [d for d in st.session_state.public_holidays if d in horizon_dates]
    st.session_state.public_holidays = st.multiselect(
        "Public holidays (treated as weekends)",
        options=horizon_dates, default=kept, format_func=format_date,
    )

    st.divider()
    st.subheader("Doctors")
    st.caption("Name, tier, sub-spec (consultants only), eligible stations, "
               "and **prev_workload** (weighted score from last period — "
               "doctors with higher numbers get less work this period).")
    st.session_state.doctors_df = st.data_editor(
        st.session_state.doctors_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "name": st.column_config.TextColumn("Name", required=True),
            "tier": st.column_config.SelectboxColumn("Tier", options=list(TIERS), required=True),
            "subspec": st.column_config.SelectboxColumn(
                "Sub-spec (consultants only)", options=list(SUBSPEC_CHOICES)),
            "eligible_stations": st.column_config.TextColumn(
                "Eligible stations (comma-sep)",
                help="Names must match the Stations table below."),
            "prev_workload": st.column_config.NumberColumn(
                "Prev workload",
                min_value=-9999, max_value=9999, step=5, default=0,
                help="Carry-in from the prior period. Defaults 0. "
                     "Same units as the workload score in the Roster tab."),
        },
        key="_editor_doctors",
    )

    with st.expander("Stations (advanced — defaults cover the CGH-style setup)"):
        st.session_state.stations_df = st.data_editor(
            st.session_state.stations_df,
            num_rows="dynamic",
            use_container_width=True,
            column_config={
                "name": st.column_config.TextColumn("Name", required=True),
                "sessions": st.column_config.TextColumn("Sessions", help="AM, PM, or AM,PM"),
                "required_per_session": st.column_config.NumberColumn("Required", min_value=1),
                "eligible_tiers": st.column_config.TextColumn(
                    "Eligible tiers", help="Comma-sep: junior, senior, consultant"),
                "is_reporting": st.column_config.CheckboxColumn("Reporting"),
            },
            key="_editor_stations",
        )

    st.divider()
    st.subheader("Leave")
    st.caption("One row per doctor × leave date. Dates outside the horizon are ignored.")
    known_names = [n for n in st.session_state.doctors_df["name"].dropna().tolist() if str(n).strip()]
    st.session_state.leave_df = st.data_editor(
        st.session_state.leave_df,
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "doctor": st.column_config.SelectboxColumn("Doctor", options=known_names),
            "date": st.column_config.DateColumn("Date"),
        },
        key="_editor_leave",
    )

    st.divider()
    st.subheader("Hard constraints")
    st.caption("Each H-rule is toggleable. Defaults match `docs/CONSTRAINTS.md`.")
    cc1, cc2 = st.columns(2)
    with cc1:
        st.checkbox("**H4** — On-call cap (1-in-N rolling)", key="h4_enabled")
        st.number_input("H4 — N (days)", min_value=2, max_value=14, key="h4_gap",
                        help="At most one on-call in any N-day window.")
        st.checkbox("**H5** — Post-call day off", key="h5_enabled")
        st.checkbox("**H6** — Senior on-call = full day off", key="h6_enabled")
    with cc2:
        st.checkbox("**H7** — Junior on-call works PM", key="h7_enabled")
        st.checkbox("**H8** — Weekend coverage (EXT/OC/WC)", key="h8_enabled")
        st.checkbox("**H9** — Lieu day after weekend EXT", key="h9_enabled")
        st.checkbox(
            "**H11** — Mandatory weekday assignment (soft, penalised)",
            key="h11_enabled",
            help="Penalises any doctor who is idle on a weekday without a valid "
                 "excuse (leave / post-call / lieu). Weight set below."
        )
    st.checkbox(
        "Weekend AM/PM station coverage (off by default — weekends are "
        "covered by EXT + on-call + weekend-consultant only)",
        key="weekend_am_pm",
    )

    st.divider()
    st.subheader("Workload weighting")
    st.caption("Turns each assignment into a number. Drives the per-doctor "
               "'workload score' in the Roster tab AND the solver's fairness "
               "objective (S0). Weekend roles default to higher weights.")
    ww1, ww2, ww3 = st.columns(3)
    ww1.number_input("Weekday session", min_value=0, max_value=100, key="wl_wd_session")
    ww1.number_input("Weekend session", min_value=0, max_value=100, key="wl_we_session")
    ww2.number_input("Weekday on-call", min_value=0, max_value=100, key="wl_wd_oncall")
    ww2.number_input("Weekend on-call", min_value=0, max_value=100, key="wl_we_oncall")
    ww3.number_input("Weekend EXT", min_value=0, max_value=100, key="wl_ext")
    ww3.number_input("Weekend consultant", min_value=0, max_value=100, key="wl_wconsult")

    st.divider()
    st.subheader("Soft-objective weights")
    st.caption("How hard the solver tries to minimise each term. Set to 0 to ignore.")
    sc1, sc2 = st.columns(2)
    sc1.number_input("S0 — weighted workload balance (primary fairness term)",
                     min_value=0, max_value=1000, key="w_workload")
    sc1.number_input("S1 — raw sessions balance (per tier)",
                     min_value=0, max_value=1000, key="w_sessions")
    sc1.number_input("S2 — on-call balance (per tier)",
                     min_value=0, max_value=1000, key="w_oncall")
    sc2.number_input("S3 — weekend-duty balance (per tier)",
                     min_value=0, max_value=1000, key="w_weekend")
    sc2.number_input("S4 — reporting-desk spread",
                     min_value=0, max_value=1000, key="w_report")
    sc2.number_input("S5 — idle-weekday penalty (H11)",
                     min_value=0, max_value=1000, key="w_idle",
                     help="Per-doctor-per-weekday cost when a doctor is idle "
                          "without an excuse. High = forces full utilisation.")


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

                # Brief workload peek — just Score + Δ median so the user can
                # judge fairness at a glance without leaving the solve tab.
                wl_df = _workload_table(
                    ss.last_inst, latest["assignments"],
                    ss.last_doctor_names, ss.last_wl_weights)
                with st.expander("Workload peek (current best)"):
                    st.dataframe(_style_workload(wl_df),
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

        # Metric strip.
        mc1, mc2, mc3, mc4, mc5 = st.columns(5)
        mc1.metric("Status", result.status)
        mc2.metric("Wall", f"{result.wall_time_s:.2f}s")
        mc3.metric("First feasible",
                   f"{(result.first_feasible_s or 0):.2f}s" if result.first_feasible_s else "—")
        mc4.metric("Objective",
                   f"{result.objective:.0f}" if result.objective is not None else "—")
        mc5.metric("Idle weekdays", idle_total if has_sol else "—")

        if has_sol:
            snap_options = ["Final"]
            for i, e in enumerate(events):
                if e.get("assignments"):
                    snap_options.append(f"#{i+1} — t={e['wall_s']:.1f}s, obj={e['objective']}")
            pick = st.selectbox("Snapshot", snap_options, index=0,
                                help="Any improving solution CP-SAT found during search.")
            if pick == "Final":
                snap = result.assignments
            else:
                idx = int(pick.split("—", 1)[0].strip().lstrip("#")) - 1
                snap = events[idx]["assignments"]

            st.subheader("Roster — doctor × date")
            grid_df = _snapshot_to_role_grid(inst, snap, names)
            st.dataframe(grid_df, use_container_width=True,
                         height=min(600, 40 + 28 * len(grid_df)))

            st.subheader("Per-doctor workload")
            st.caption("**Score** = weighted sum of assignments + prev_workload. "
                       "**Δ median** = how far this doctor is from the tier median "
                       "(red = over-worked, blue = under-worked).")
            wl_df = _workload_table(inst, snap, names, wl_weights)
            st.dataframe(_style_workload(wl_df),
                         use_container_width=True, hide_index=True)

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
