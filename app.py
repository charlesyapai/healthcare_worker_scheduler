"""Streamlit UI for the healthcare roster scheduler (v0.4).

Configure real doctors, a real calendar, and constraints in the UI.
Watch intermediate solutions stream in. Pick any snapshot to view its
roster keyed by name × date.

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
from scheduler.metrics import problem_metrics, solution_metrics, solve_metrics
from scheduler.model import Weights, solve
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
    ss.setdefault("w_sessions", 10)
    ss.setdefault("w_oncall", 20)
    ss.setdefault("w_weekend", 20)
    ss.setdefault("w_report", 5)
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


# ========================================================== Roster render
def _snapshot_to_role_grid(inst, assignments: dict, names: dict[int, str]) -> pd.DataFrame:
    """Row per doctor, column per date. Cell = role string."""
    dates = dates_for_horizon(inst.start_weekday_date(), inst.n_days) \
        if hasattr(inst, "start_weekday_date") else None
    # We don't store start_date on Instance; pass it separately via session.
    start_date = st.session_state.start_date
    dates = [start_date + timedelta(days=t) for t in range(inst.n_days)]
    date_labels = [format_date(d) for d in dates]

    # Init grid with empty strings.
    doc_order = [names.get(d.id, f"Dr #{d.id}") for d in inst.doctors]
    grid = {name: [""] * inst.n_days for name in doc_order}

    # Leave first (so station assignments can overwrite if there's a model bug).
    for did, days in inst.leave.items():
        nm = names.get(did, f"Dr #{did}")
        for t in days:
            if 0 <= t < inst.n_days:
                grid[nm][t] = ROLE_CODES["leave"]

    stations = assignments.get("stations", {})
    # Key format: (did, day, station_name, session). Value presence = assigned.
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


def _snapshot_workload(inst, assignments: dict, names: dict[int, str]) -> pd.DataFrame:
    rows = []
    stations = assignments.get("stations", {})
    sess_by_doc: dict[int, int] = {}
    for key, v in stations.items():
        if v:
            did = key[0]
            sess_by_doc[did] = sess_by_doc.get(did, 0) + 1
    oc_by_doc: dict[int, int] = {}
    for (did, _), v in assignments.get("oncall", {}).items():
        if v:
            oc_by_doc[did] = oc_by_doc.get(did, 0) + 1
    wk_by_doc: dict[int, int] = {}
    for key_set in ("ext", "wconsult"):
        for (did, _), v in assignments.get(key_set, {}).items():
            if v:
                wk_by_doc[did] = wk_by_doc.get(did, 0) + 1
    for (did, day), v in assignments.get("oncall", {}).items():
        if v and inst.is_weekend(day):
            wk_by_doc[did] = wk_by_doc.get(did, 0) + 1

    for d in inst.doctors:
        rows.append({
            "Doctor": names.get(d.id, f"Dr #{d.id}"),
            "Tier": d.tier,
            "Sub-spec": d.subspec or "",
            "Sessions": sess_by_doc.get(d.id, 0),
            "On-call": oc_by_doc.get(d.id, 0),
            "Weekend": wk_by_doc.get(d.id, 0),
            "Leave days": len(inst.leave.get(d.id, set())),
        })
    return pd.DataFrame(rows)


# ========================================================== App shell
st.set_page_config(page_title="Healthcare Roster Scheduler", layout="wide")
_ensure_defaults()

st.title("Healthcare Roster Scheduler")
st.caption("Configure doctors, dates, and constraints; stream solutions in real time. "
           "Constraint spec: `docs/CONSTRAINTS.md`.")

tab_setup, tab_constraints, tab_solve, tab_roster, tab_analytics, tab_diag, tab_export = st.tabs(
    ["Setup", "Constraints", "Solve", "Roster", "Analytics", "Diagnostics", "Export"]
)

# ==================================================================== Setup
with tab_setup:
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

    st.subheader("Doctors")
    st.caption("Edit names, tiers, sub-specialty, and the stations each is eligible for. "
               "Add/remove rows via the table controls.")
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

# ============================================================== Constraints
with tab_constraints:
    st.subheader("Hard constraints")
    st.checkbox(
        "Weekend AM/PM station coverage (off by default — weekends are covered by "
        "extended-duty + on-call + weekend-consultant only)",
        key="weekend_am_pm",
    )

    st.subheader("Soft objective weights")
    st.caption("Higher weight = solver tries harder to minimise that term. Set to 0 to ignore.")
    c1, c2 = st.columns(2)
    c1.number_input("S1 — balance weekday sessions across each tier", min_value=0, max_value=1000,
                    key="w_sessions")
    c1.number_input("S2 — balance on-call across juniors/seniors", min_value=0, max_value=1000,
                    key="w_oncall")
    c2.number_input("S3 — balance weekend duty across each tier", min_value=0, max_value=1000,
                    key="w_weekend")
    c2.number_input("S4 — penalise same doctor on reporting desk two days in a row",
                    min_value=0, max_value=1000, key="w_report")

    st.subheader("Solver")
    c1, c2 = st.columns(2)
    c1.slider("Time limit (s)", 5, 600, key="time_limit")
    c2.slider("CP-SAT workers", 1, 16, key="num_workers")
    st.checkbox("Feasibility only (skip objective — fastest 'any valid roster')",
                key="feasibility_only")

# ================================================================== Solve
def _solve_worker(inst, time_limit_s, weights, num_workers, feasibility_only, q):
    def on_event(e):
        q.put(("event", e))
    try:
        result = solve(
            inst,
            time_limit_s=time_limit_s,
            weights=weights,
            num_workers=num_workers,
            feasibility_only=feasibility_only,
            on_intermediate=on_event,
            snapshot_assignments=True,
        )
        q.put(("done", result))
    except Exception as exc:  # pragma: no cover
        q.put(("error", exc))


with tab_solve:
    bc1, bc2, bc3 = st.columns([1, 1, 1])
    diagnose_btn = bc1.button("Diagnose (L1)", use_container_width=True)
    solve_btn = bc2.button("Solve", type="primary", use_container_width=True)
    clear_btn = bc3.button("Clear last result", use_container_width=True)

    if clear_btn:
        for k in ("last_result", "last_inst", "last_events", "last_doctor_names"):
            st.session_state.pop(k, None)
        st.rerun()

    if diagnose_btn:
        try:
            inst = _build_inst()
            issues = presolve_feasibility(inst)
            if not issues:
                st.success("No pre-solve issues — necessary-condition checks pass.")
            else:
                errors = [i for i in issues if i.severity == "error"]
                warnings_ = [i for i in issues if i.severity == "warning"]
                if errors:
                    st.error(f"{len(errors)} blocking issue(s):")
                    for i in errors:
                        st.write(f"• **{i.code}** — {i.message}")
                if warnings_:
                    st.warning(f"{len(warnings_)} warning(s):")
                    for i in warnings_:
                        st.write(f"• **{i.code}** — {i.message}")
        except BuildError as e:
            st.error(f"Setup issue: {e}")

    if solve_btn:
        try:
            inst = _build_inst()
            names = doctor_name_map(st.session_state.doctors_df, inst)
        except BuildError as e:
            st.error(f"Setup issue: {e}")
        else:
            weights = Weights(
                balance_sessions=int(st.session_state.w_sessions),
                balance_oncall=int(st.session_state.w_oncall),
                balance_weekend=int(st.session_state.w_weekend),
                reporting_spread=int(st.session_state.w_report),
            )
            q: Queue = Queue()
            worker = threading.Thread(
                target=_solve_worker,
                args=(inst, float(st.session_state.time_limit), weights,
                      int(st.session_state.num_workers),
                      bool(st.session_state.feasibility_only), q),
                daemon=True,
            )
            worker.start()

            st.subheader("Live solve")
            status_slot = st.empty()
            chart_slot = st.empty()
            list_slot = st.empty()

            events: list[dict] = []
            final = None
            error = None
            t0 = time.perf_counter()

            while True:
                try:
                    kind, payload = q.get(timeout=POLL_INTERVAL_S)
                except Empty:
                    status_slot.info(f"Solving… {time.perf_counter()-t0:.1f}s, "
                                     f"{len(events)} solutions so far.")
                    if not worker.is_alive() and q.empty():
                        break
                    continue

                if kind == "event":
                    events.append(payload)
                    obj = payload.get("objective")
                    bnd = payload.get("best_bound")
                    gap = None
                    if obj and bnd is not None and obj > 0:
                        gap = max(0.0, (obj - bnd) / obj * 100)
                    status_slot.info(
                        f"Solving… {payload['wall_s']:.1f}s — "
                        f"**#{len(events)}** obj **{obj}** "
                        f"(bound {bnd})"
                        + (f", gap **{gap:.1f}%**" if gap is not None else "")
                    )
                    fig, _ = plots.convergence(events)
                    chart_slot.plotly_chart(fig, use_container_width=True)

                    sol_rows = []
                    for i, e in enumerate(events):
                        row = {"#": i + 1,
                               "t (s)": round(e["wall_s"], 2),
                               "objective": e["objective"],
                               "bound": e["best_bound"]}
                        for k, v in (e.get("components") or {}).items():
                            row[k] = v
                        sol_rows.append(row)
                    list_slot.dataframe(pd.DataFrame(sol_rows),
                                        use_container_width=True, hide_index=True)
                elif kind == "done":
                    final = payload
                    break
                elif kind == "error":
                    error = payload
                    break

            if error is not None:
                st.error(f"Solve raised: {error!r}")
            elif final is not None:
                if final.status in ("OPTIMAL", "FEASIBLE"):
                    status_slot.success(
                        f"**{final.status}** in {final.wall_time_s:.2f}s — "
                        f"obj **{final.objective}**, first feasible at "
                        f"{(final.first_feasible_s or 0):.2f}s, "
                        f"{len(events)} improving solutions."
                    )
                else:
                    status_slot.error(f"**{final.status}** after "
                                      f"{final.wall_time_s:.2f}s — no roster produced.")
                st.session_state.last_result = final
                st.session_state.last_inst = inst
                st.session_state.last_events = events
                st.session_state.last_doctor_names = names

    if "last_result" in st.session_state and not solve_btn:
        r = st.session_state.last_result
        st.info(f"Last run: **{r.status}** · obj **{r.objective}** · "
                f"{r.wall_time_s:.2f}s · "
                f"{len(st.session_state.last_events)} snapshots available — "
                "see the **Roster** tab.")

# ================================================================ Roster
with tab_roster:
    if "last_result" not in st.session_state:
        st.info("Run a solve first (Solve tab).")
    else:
        result = st.session_state.last_result
        inst = st.session_state.last_inst
        events = st.session_state.last_events
        names = st.session_state.last_doctor_names

        if result.status not in ("OPTIMAL", "FEASIBLE"):
            st.warning(f"No roster to display — status {result.status}.")
        else:
            options = ["Final"]
            for i, e in enumerate(events):
                if e.get("assignments"):
                    options.append(f"#{i+1} — t={e['wall_s']:.1f}s, obj={e['objective']}")

            pick = st.selectbox("Snapshot", options, index=0,
                                help="Any improving solution CP-SAT found during search.")
            if pick == "Final":
                snap = result.assignments
                label = f"Final ({result.status}, obj {result.objective})"
            else:
                idx = int(pick.split("—", 1)[0].strip().lstrip("#")) - 1
                snap = events[idx]["assignments"]
                label = pick

            st.caption(f"Showing: **{label}**")

            st.subheader("Doctor × date grid")
            st.caption("Cells show the assigned roles. `AM:CT` = AM at CT station. "
                       "`OC` = on-call. `EXT` = weekend extended duty. "
                       "`WC` = weekend consultant. `LV` = leave.")
            grid_df = _snapshot_to_role_grid(inst, snap, names)
            st.dataframe(grid_df, use_container_width=True, height=min(600, 40 + 28 * len(grid_df)))

            st.subheader("Per-doctor workload")
            wl_df = _snapshot_workload(inst, snap, names)
            st.dataframe(wl_df, use_container_width=True, hide_index=True)

# ============================================================== Analytics
def _explanation(md: str) -> None:
    with st.expander("How to read this chart", expanded=False):
        st.markdown(md)


with tab_analytics:
    if "last_result" not in st.session_state:
        st.info("Run a solve first (Solve tab).")
    else:
        result = st.session_state.last_result
        inst = st.session_state.last_inst
        events = st.session_state.last_events

        if result.status not in ("OPTIMAL", "FEASIBLE"):
            st.warning("No solution to analyse.")
        else:
            sm = solve_metrics(result, events)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("Status", result.status)
            c2.metric("Wall time", f"{result.wall_time_s:.2f} s")
            c3.metric("First feasible",
                      f"{(result.first_feasible_s or 0):.2f} s")
            c4.metric("Objective", result.objective)
            c5, c6, c7, c8 = st.columns(4)
            c5.metric("Optimality gap",
                      f"{sm['optimality_gap']*100:.1f} %" if sm["optimality_gap"] is not None else "—")
            c6.metric("Variables", f"{result.n_vars:,}")
            c7.metric("Constraints", f"{result.n_constraints:,}")
            c8.metric("Snapshots", sm["n_intermediate_solutions"])

            st.subheader("Convergence")
            fig, md = plots.convergence(events, objective=result.objective)
            st.plotly_chart(fig, use_container_width=True)
            _explanation(md)

            st.subheader("Penalty breakdown over time")
            fig, md = plots.penalty_breakdown(events)
            st.plotly_chart(fig, use_container_width=True)
            _explanation(md)

            st.subheader("Workload histogram")
            fig, md = plots.workload_histogram(inst, result)
            st.plotly_chart(fig, use_container_width=True)
            _explanation(md)

            st.subheader("On-call spacing")
            fig, md = plots.oncall_spacing(inst, result)
            st.plotly_chart(fig, use_container_width=True)
            _explanation(md)

            st.subheader("Coverage heatmap")
            fig, md = plots.coverage_heatmap(inst, result)
            st.plotly_chart(fig, use_container_width=True)
            _explanation(md)

            st.subheader("Coverage slack (pre-solve)")
            fig, md = plots.coverage_slack(inst)
            st.plotly_chart(fig, use_container_width=True)
            _explanation(md)

# ============================================================ Diagnostics
with tab_diag:
    st.subheader("L1 — pre-solve feasibility sniff")
    st.caption("Millisecond necessary-condition checks. Won't catch every "
               "infeasibility, but catches the obvious ones instantly.")
    if st.button("Run L1 checks"):
        try:
            inst = _build_inst()
            issues = presolve_feasibility(inst)
            if not issues:
                st.success("All L1 checks pass.")
            else:
                errors = [i for i in issues if i.severity == "error"]
                warnings_ = [i for i in issues if i.severity == "warning"]
                if errors:
                    st.error(f"{len(errors)} blocking issue(s):")
                    for i in errors:
                        st.write(f"• **{i.code}** — {i.message}")
                if warnings_:
                    st.warning(f"{len(warnings_)} warning(s):")
                    for i in warnings_:
                        st.write(f"• **{i.code}** — {i.message}")
        except BuildError as e:
            st.error(f"Setup issue: {e}")

    st.divider()
    st.subheader("L3 — soft-relax explainer")
    st.caption("Relaxes H1 (station coverage) and H8 (weekend coverage) "
               "with slack, minimises total slack, and reports which "
               "constraints had to be broken and by how much.")
    if st.button("Run L3 explainer (may take ~30 s)"):
        try:
            inst = _build_inst()
        except BuildError as e:
            st.error(f"Setup issue: {e}")
        else:
            with st.spinner("Running relaxed solve…"):
                rep = explain_infeasibility(inst, time_limit_s=30)
            st.write(f"**Status:** `{rep.status}` · "
                     f"wall time {rep.wall_time_s:.2f}s · "
                     f"total slack = {rep.total_slack}")
            if rep.note:
                st.info(rep.note)
            if rep.violations:
                df = pd.DataFrame([
                    {"code": v.code, "location": v.location,
                     "amount": v.amount, "message": v.message}
                    for v in rep.violations
                ])
                st.dataframe(df, use_container_width=True, hide_index=True)
            else:
                st.success("No constraint violations in the relaxed model.")

# ================================================================ Export
with tab_export:
    if "last_result" not in st.session_state:
        st.info("Run a solve first (Solve tab).")
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
