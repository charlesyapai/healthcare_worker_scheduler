"""Streamlit UI for the healthcare roster scheduler.

Entry point used by Hugging Face Spaces (see README.md frontmatter).
Run locally with:
    streamlit run app.py
"""

from __future__ import annotations

import io
import json
from dataclasses import asdict

import pandas as pd
import streamlit as st

from scheduler import make_synthetic, solve
from scheduler.instance import SESSIONS
from scheduler.model import Weights

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _day_label(inst, day: int) -> str:
    """Column label for day `day` in the roster grid."""
    wd = WEEKDAY_NAMES[inst.weekday_of(day)]
    return f"d{day:02d}-{wd}"


st.set_page_config(
    page_title="Healthcare Roster Scheduler",
    layout="wide",
)

st.title("Healthcare Roster Scheduler")
st.caption(
    "CP-SAT baseline (Phase 1). Generates a monthly roster and reports how long "
    "the solver took. See `docs/CONSTRAINTS.md` in the repo for the constraint spec."
)

# ------------------------------------------------------------------ Sidebar
with st.sidebar:
    st.header("Instance")
    n_doctors = st.slider("Doctors", 15, 200, 30, step=5)
    n_days = st.slider("Days in horizon", 3, 42, 28, step=1)
    start_weekday = st.selectbox(
        "Day 0 is a…", options=list(range(7)),
        format_func=lambda i: WEEKDAY_NAMES[i], index=0,
    )
    seed = st.number_input("Seed", min_value=0, value=0, step=1)
    leave_rate = st.slider("Leave rate", 0.0, 0.3, 0.03, step=0.01,
                           help="Expected fraction of doctor-days spent on leave.")

    holidays_str = st.text_input(
        "Public holidays (day indices, comma-sep)", value="",
        help="E.g. '10,11' treats days 10 and 11 as Sundays.",
    )

    st.header("Solve")
    time_limit = st.slider("Time limit (s)", 5, 600, 60, step=5)
    num_workers = st.slider("CP-SAT workers", 1, 16, 8, step=1)
    feasibility_only = st.checkbox(
        "Feasibility only (no objective)", value=False,
        help="Skip soft objective — fastest way to check if the instance is solvable.",
    )

    with st.expander("Objective weights"):
        w_sessions = st.number_input("Balance AM/PM sessions", 0, 1000, 10)
        w_oncall = st.number_input("Balance on-call", 0, 1000, 20)
        w_weekend = st.number_input("Balance weekend", 0, 1000, 20)
        w_report = st.number_input("Reporting spread penalty", 0, 1000, 5)

    solve_btn = st.button("Solve", type="primary", use_container_width=True)

# ------------------------------------------------------------- Build instance
try:
    public_holidays = {int(x.strip()) for x in holidays_str.split(",") if x.strip()}
except ValueError:
    st.sidebar.error("Public holidays must be integers.")
    public_holidays = set()

inst = make_synthetic(
    n_doctors=n_doctors,
    n_days=n_days,
    seed=int(seed),
    start_weekday=int(start_weekday),
    leave_rate=float(leave_rate),
)
inst.public_holidays = public_holidays

# ------------------------------------------------------------------ Overview
col1, col2, col3, col4 = st.columns(4)
tier_counts = {"junior": 0, "senior": 0, "consultant": 0}
for d in inst.doctors:
    tier_counts[d.tier] += 1
col1.metric("Doctors", n_doctors,
            f"J {tier_counts['junior']} / S {tier_counts['senior']} / C {tier_counts['consultant']}")
col2.metric("Days", n_days)
weekends = sum(1 for t in range(n_days) if inst.is_weekend(t))
col3.metric("Weekend days", weekends)
leave_total = sum(len(v) for v in inst.leave.values())
col4.metric("Leave days (generated)", leave_total)

# --------------------------------------------------------------------- Solve
if solve_btn:
    events: list[dict] = []
    weights = Weights(
        balance_sessions=int(w_sessions),
        balance_oncall=int(w_oncall),
        balance_weekend=int(w_weekend),
        reporting_spread=int(w_report),
    )
    with st.status(f"Solving {n_doctors} doctors × {n_days} days "
                   f"(limit {time_limit}s)…", expanded=True) as status:
        result = solve(
            inst,
            time_limit_s=float(time_limit),
            weights=weights,
            num_workers=int(num_workers),
            feasibility_only=feasibility_only,
            on_intermediate=events.append,
        )
        if result.status in ("OPTIMAL", "FEASIBLE"):
            status.update(label=f"{result.status} in {result.wall_time_s:.2f}s "
                                f"(objective={result.objective})",
                          state="complete")
        else:
            status.update(label=f"{result.status} after {result.wall_time_s:.2f}s",
                          state="error")
    st.session_state["last_result"] = result
    st.session_state["last_inst"] = inst
    st.session_state["last_events"] = events

# ---------------------------------------------------------------- Result UI
if "last_result" in st.session_state:
    result = st.session_state["last_result"]
    inst = st.session_state["last_inst"]
    events = st.session_state["last_events"]

    tab_summary, tab_roster, tab_workload, tab_export = st.tabs(
        ["Summary", "Roster", "Workload", "Export"]
    )

    # ---- Summary
    with tab_summary:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status", result.status)
        c2.metric("Wall time", f"{result.wall_time_s:.2f} s")
        c3.metric("Objective", result.objective if result.objective is not None else "—")
        c4.metric("Vars / Constraints", f"{result.n_vars:,} / {result.n_constraints:,}")

        if events:
            st.subheader("Intermediate solutions")
            st.caption("Each point is a new improving solution found during search.")
            df_events = pd.DataFrame(events)
            st.line_chart(df_events, x="wall_s", y=["objective", "best_bound"])
            st.dataframe(df_events, use_container_width=True)
        elif result.status in ("OPTIMAL", "FEASIBLE"):
            st.info("No intermediate solutions recorded "
                    "(feasibility-only, or solved in one shot).")

    # ---- Roster (calendar grid)
    with tab_roster:
        if result.status not in ("OPTIMAL", "FEASIBLE"):
            st.warning(f"No roster to display (status={result.status}).")
        else:
            station_names = [s.name for s in inst.stations]
            # One row per (station, session); columns are days.
            rows: list[dict] = []
            st_assigns = result.assignments["stations"]
            oncall = result.assignments["oncall"]
            ext = result.assignments["ext"]
            wconsult = result.assignments["wconsult"]
            by_cell: dict[tuple[int, str, str], list[int]] = {}
            for (did, day, sname, sess), _ in st_assigns.items():
                by_cell.setdefault((day, sname, sess), []).append(did)

            for st_obj in inst.stations:
                for sess in st_obj.sessions:
                    row: dict = {"station": st_obj.name, "session": sess}
                    for day in range(inst.n_days):
                        if inst.is_weekend(day) and not inst.weekend_am_pm_enabled:
                            row[_day_label(inst, day)] = ""
                        else:
                            ids = by_cell.get((day, st_obj.name, sess), [])
                            row[_day_label(inst, day)] = ",".join(f"D{i}" for i in ids)
                    rows.append(row)

            # Weekend / oncall rows.
            oc_row_j = {"station": "ONCALL", "session": "junior"}
            oc_row_s = {"station": "ONCALL", "session": "senior"}
            ext_row_j = {"station": "WKND_EXT", "session": "junior"}
            ext_row_s = {"station": "WKND_EXT", "session": "senior"}
            wc_row = {"station": "WKND_CONSULT", "session": "per-subspec"}
            doc_by_id = {d.id: d for d in inst.doctors}
            for day in range(inst.n_days):
                label = _day_label(inst, day)
                j_oc = [did for (did, dy) in oncall if dy == day and doc_by_id[did].tier == "junior"]
                s_oc = [did for (did, dy) in oncall if dy == day and doc_by_id[did].tier == "senior"]
                j_ex = [did for (did, dy) in ext if dy == day and doc_by_id[did].tier == "junior"]
                s_ex = [did for (did, dy) in ext if dy == day and doc_by_id[did].tier == "senior"]
                wc = [(did, doc_by_id[did].subspec) for (did, dy) in wconsult if dy == day]
                oc_row_j[label] = ",".join(f"D{i}" for i in j_oc)
                oc_row_s[label] = ",".join(f"D{i}" for i in s_oc)
                ext_row_j[label] = ",".join(f"D{i}" for i in j_ex)
                ext_row_s[label] = ",".join(f"D{i}" for i in s_ex)
                wc_row[label] = ",".join(f"D{i}({ss})" for i, ss in wc)
            rows += [oc_row_j, oc_row_s, ext_row_j, ext_row_s, wc_row]

            df = pd.DataFrame(rows)
            st.dataframe(df, use_container_width=True, height=500)

    # ---- Workload
    with tab_workload:
        if result.status not in ("OPTIMAL", "FEASIBLE"):
            st.warning(f"No workload to display (status={result.status}).")
        else:
            st_assigns = result.assignments["stations"]
            oncall = result.assignments["oncall"]
            ext = result.assignments["ext"]
            wconsult = result.assignments["wconsult"]
            per: dict[int, dict] = {
                d.id: {
                    "id": d.id, "tier": d.tier, "subspec": d.subspec or "",
                    "am_pm": 0, "oncall": 0, "weekend_ext": 0, "weekend_consult": 0,
                }
                for d in inst.doctors
            }
            for (did, _, _, _) in st_assigns:
                per[did]["am_pm"] += 1
            for (did, _) in oncall:
                per[did]["oncall"] += 1
            for (did, _) in ext:
                per[did]["weekend_ext"] += 1
            for (did, _) in wconsult:
                per[did]["weekend_consult"] += 1
            df = pd.DataFrame(per.values())
            st.dataframe(df, use_container_width=True, height=500)

            st.subheader("Balance per tier")
            summary = df.groupby("tier")[["am_pm", "oncall", "weekend_ext", "weekend_consult"]]\
                        .agg(["min", "max", "mean"]).round(2)
            st.dataframe(summary, use_container_width=True)

    # ---- Export
    with tab_export:
        if result.status in ("OPTIMAL", "FEASIBLE"):
            # JSON dump
            payload = {
                "meta": {
                    "status": result.status,
                    "wall_time_s": result.wall_time_s,
                    "objective": result.objective,
                    "best_bound": result.best_bound,
                    "n_vars": result.n_vars,
                    "n_constraints": result.n_constraints,
                    "n_doctors": len(inst.doctors),
                    "n_days": inst.n_days,
                    "start_weekday": inst.start_weekday,
                },
                "stations": [
                    {"doctor": d, "day": t, "station": s, "session": sess}
                    for (d, t, s, sess) in result.assignments["stations"]
                ],
                "oncall":   [{"doctor": d, "day": t} for (d, t) in result.assignments["oncall"]],
                "ext":      [{"doctor": d, "day": t} for (d, t) in result.assignments["ext"]],
                "wconsult": [{"doctor": d, "day": t} for (d, t) in result.assignments["wconsult"]],
            }
            st.download_button(
                "Download roster (JSON)",
                data=json.dumps(payload, indent=2),
                file_name="roster.json",
                mime="application/json",
            )

            # CSV: flatten every role into one long table.
            rows: list[dict] = []
            for (d, t, s, sess) in result.assignments["stations"]:
                rows.append({"doctor": d, "day": t, "role": f"STATION_{s}_{sess}"})
            for (d, t) in result.assignments["oncall"]:
                rows.append({"doctor": d, "day": t, "role": "ONCALL"})
            for (d, t) in result.assignments["ext"]:
                rows.append({"doctor": d, "day": t, "role": "WEEKEND_EXT"})
            for (d, t) in result.assignments["wconsult"]:
                rows.append({"doctor": d, "day": t, "role": "WEEKEND_CONSULT"})
            csv_buf = io.StringIO()
            pd.DataFrame(rows).to_csv(csv_buf, index=False)
            st.download_button(
                "Download roster (CSV)",
                data=csv_buf.getvalue(),
                file_name="roster.csv",
                mime="text/csv",
            )
        else:
            st.info("No roster to export — solver did not return a feasible solution.")
else:
    st.info("Configure the instance in the sidebar and click **Solve**.")
