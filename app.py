"""Streamlit UI for the healthcare roster scheduler.

Entry point used by Hugging Face Spaces. Run locally with:
    streamlit run app.py

Features
--------
- Real-time streaming: the solver runs in a background thread; each new
  intermediate solution appears in the UI as CP-SAT finds it.
- Pre-solve feasibility sniff (L1) with specific error/warning messages.
- On INFEASIBLE / UNKNOWN, "Explain infeasibility" button runs the L3
  soft-relax diagnostic and reports exactly which constraints had to be
  broken.
- Analytics tab with interactive Plotly charts (convergence, penalty
  breakdown, workload, on-call spacing, roster heatmap, coverage heatmap).
- Every chart is accompanied by a collapsible explanation (from
  `docs/plots/*.md`).
"""

from __future__ import annotations

import io
import json
import threading
import time
from queue import Empty, Queue

import pandas as pd
import streamlit as st

from scheduler import make_synthetic, solve
from scheduler.diagnostics import (
    FeasibilityIssue,
    explain_infeasibility,
    presolve_feasibility,
)
from scheduler.metrics import problem_metrics, solution_metrics, solve_metrics
from scheduler.model import Weights
from scheduler import plots

WEEKDAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
POLL_INTERVAL_S = 0.2


def _day_label(inst, day: int) -> str:
    wd = WEEKDAY_NAMES[inst.weekday_of(day)]
    return f"d{day:02d}-{wd}"


def _explanation(md_text: str) -> None:
    with st.expander("How to read this chart", expanded=False):
        st.markdown(md_text)


st.set_page_config(
    page_title="Healthcare Roster Scheduler",
    layout="wide",
)
st.title("Healthcare Roster Scheduler")
st.caption(
    "CP-SAT baseline (Phase 1). Spec in `docs/CONSTRAINTS.md`; "
    "plot guides under `docs/plots/`."
)

# =========================================================== Sidebar
with st.sidebar:
    st.header("Instance")
    n_doctors = st.slider("Doctors", 10, 200, 30, step=5)
    n_days = st.slider("Days in horizon", 3, 42, 28, step=1)
    start_weekday = st.selectbox(
        "Day 0 is a…",
        options=list(range(7)),
        format_func=lambda i: WEEKDAY_NAMES[i], index=0,
    )
    seed = st.number_input("Seed", min_value=0, value=0, step=1)
    leave_rate = st.slider("Leave rate", 0.0, 0.3, 0.03, step=0.01)
    holidays_str = st.text_input(
        "Public holidays (day indices, comma-sep)", value="",
        help="E.g. '10,11' treats days 10 and 11 as Sundays.",
    )

    st.header("Solve")
    time_limit = st.slider("Time limit (s)", 5, 600, 60, step=5)
    num_workers = st.slider("CP-SAT workers", 1, 16, 8, step=1)
    feasibility_only = st.checkbox("Feasibility only (skip objective)", value=False)

    with st.expander("Objective weights"):
        w_sessions = st.number_input("Balance AM/PM sessions", 0, 1000, 10)
        w_oncall = st.number_input("Balance on-call", 0, 1000, 20)
        w_weekend = st.number_input("Balance weekend", 0, 1000, 20)
        w_report = st.number_input("Reporting spread penalty", 0, 1000, 5)

    c1, c2 = st.columns(2)
    diagnose_btn = c1.button("Diagnose", use_container_width=True)
    solve_btn = c2.button("Solve", type="primary", use_container_width=True)

# ------------------------------------------------------ Build instance
try:
    public_holidays = {int(x.strip()) for x in holidays_str.split(",") if x.strip()}
except ValueError:
    st.sidebar.error("Public holidays must be integers.")
    public_holidays = set()

inst = make_synthetic(
    n_doctors=int(n_doctors),
    n_days=int(n_days),
    seed=int(seed),
    start_weekday=int(start_weekday),
    leave_rate=float(leave_rate),
)
inst.public_holidays = public_holidays

# ------------------------------------------------------ Overview
pm = problem_metrics(inst)
c1, c2, c3, c4 = st.columns(4)
c1.metric(
    "Doctors", n_doctors,
    f"J {pm['tier_counts'].get('junior', 0)} / "
    f"S {pm['tier_counts'].get('senior', 0)} / "
    f"C {pm['tier_counts'].get('consultant', 0)}",
)
c2.metric("Days (weekend)", f"{n_days} ({pm['weekend_days']})")
c3.metric("Leave doctor-days", pm["leave_doctor_days"])
c4.metric("Min coverage slack",
          f"{pm['coverage_slack_min']:.2f}" if pm["coverage_slack_min"] else "—")

# ------------------------------------------------------ Diagnose button
if diagnose_btn:
    issues = presolve_feasibility(inst)
    st.session_state["last_diagnosis"] = issues

if "last_diagnosis" in st.session_state:
    issues = st.session_state["last_diagnosis"]
    st.subheader("Pre-solve diagnosis (L1)")
    if not issues:
        st.success("No pre-solve issues found — the instance passes all "
                   "necessary-condition checks.")
    else:
        errors = [i for i in issues if i.severity == "error"]
        warnings = [i for i in issues if i.severity == "warning"]
        if errors:
            st.error(f"{len(errors)} blocking issue(s):")
            for i in errors:
                st.write(f"  • **{i.code}** — {i.message}")
        if warnings:
            st.warning(f"{len(warnings)} warning(s):")
            for i in warnings:
                st.write(f"  • **{i.code}** — {i.message}")

    fig, md = plots.coverage_slack(inst)
    st.plotly_chart(fig, use_container_width=True)
    _explanation(md)

# ======================================================= Solve (streaming)
def _solve_worker(
    inst, time_limit_s: float, weights: Weights, num_workers: int,
    feasibility_only: bool, q: Queue,
) -> None:
    def on_event(e):
        q.put(("event", e))
    try:
        result = solve(
            inst, time_limit_s=time_limit_s, weights=weights,
            num_workers=num_workers, feasibility_only=feasibility_only,
            on_intermediate=on_event,
        )
        q.put(("done", result))
    except Exception as exc:  # pragma: no cover
        q.put(("error", exc))


if solve_btn:
    weights = Weights(
        balance_sessions=int(w_sessions),
        balance_oncall=int(w_oncall),
        balance_weekend=int(w_weekend),
        reporting_spread=int(w_report),
    )

    q: Queue = Queue()
    worker = threading.Thread(
        target=_solve_worker,
        args=(inst, float(time_limit), weights, int(num_workers),
              feasibility_only, q),
        daemon=True,
    )
    worker.start()

    st.subheader("Live solve")
    status_slot = st.empty()
    chart_slot = st.empty()
    components_slot = st.empty()

    events: list[dict] = []
    final = None
    error = None
    t_start = time.perf_counter()

    while True:
        try:
            kind, payload = q.get(timeout=POLL_INTERVAL_S)
        except Empty:
            # No event yet — refresh the "elapsed" label so the user sees activity.
            elapsed = time.perf_counter() - t_start
            status_slot.info(f"Solving… {elapsed:.1f}s, "
                             f"{len(events)} solutions so far.")
            if not worker.is_alive() and q.empty():
                # Worker exited without sending 'done' — should be unreachable.
                break
            continue

        if kind == "event":
            events.append(payload)
            with status_slot.container():
                st.info(
                    f"Solving… {payload['wall_s']:.1f}s elapsed, "
                    f"**{len(events)} solutions**, "
                    f"best obj = **{payload['objective']}** "
                    f"(bound {payload['best_bound']})."
                )
            fig, _ = plots.convergence(events)
            chart_slot.plotly_chart(fig, use_container_width=True)

            if payload.get("components"):
                comp_df = (pd.DataFrame([
                    {"component": k, "value": v}
                    for k, v in payload["components"].items()
                ]).sort_values("value", ascending=False))
                components_slot.dataframe(comp_df, use_container_width=True,
                                          hide_index=True)
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
                f"objective **{final.objective}** "
                f"(first feasible at {final.first_feasible_s:.2f}s, "
                f"{len(events)} improving solutions)."
            )
        else:
            status_slot.error(
                f"**{final.status}** after {final.wall_time_s:.2f}s — "
                "no roster returned."
            )

        st.session_state["last_result"] = final
        st.session_state["last_inst"] = inst
        st.session_state["last_events"] = events

# ======================================================= Result display
if "last_result" in st.session_state:
    result = st.session_state["last_result"]
    inst = st.session_state["last_inst"]
    events = st.session_state["last_events"]

    tab_summary, tab_analytics, tab_roster, tab_workload, tab_why, tab_export = st.tabs(
        ["Summary", "Analytics", "Roster", "Workload", "Why infeasible?", "Export"]
    )

    sm = solve_metrics(result, events)
    qm = solution_metrics(inst, result) if result.status in ("OPTIMAL", "FEASIBLE") else {}

    # ------------------ Summary
    with tab_summary:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Status", result.status)
        c2.metric("Wall time", f"{result.wall_time_s:.2f} s")
        c3.metric("First feasible",
                  f"{result.first_feasible_s:.2f} s"
                  if result.first_feasible_s is not None else "—")
        c4.metric("Objective", result.objective if result.objective is not None else "—")

        c5, c6, c7, c8 = st.columns(4)
        c5.metric("Optimality gap",
                  f"{sm['optimality_gap']*100:.1f} %"
                  if sm["optimality_gap"] is not None else "—")
        c6.metric("Variables", f"{result.n_vars:,}")
        c7.metric("Constraints", f"{result.n_constraints:,}")
        c8.metric("Intermediate", f"{sm['n_intermediate_solutions']}")

        if result.penalty_components:
            st.subheader("Final penalty breakdown")
            df_comp = (pd.DataFrame([
                {"component": k, "value": v}
                for k, v in result.penalty_components.items()
            ]).sort_values("value", ascending=False))
            st.dataframe(df_comp, use_container_width=True, hide_index=True)

    # ------------------ Analytics (charts + explanations)
    with tab_analytics:
        if result.status not in ("OPTIMAL", "FEASIBLE"):
            st.warning("No solution to analyze.")
        else:
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

    # ------------------ Roster (both calendar heatmap + text grid)
    with tab_roster:
        if result.status not in ("OPTIMAL", "FEASIBLE"):
            st.warning("No roster to display.")
        else:
            st.subheader("Calendar heatmap")
            fig, md = plots.roster_heatmap(inst, result)
            st.plotly_chart(fig, use_container_width=True)
            _explanation(md)

            st.subheader("Text roster (stations × days)")
            st_assigns = result.assignments["stations"]
            by_cell: dict = {}
            for (did, day, sname, sess) in st_assigns:
                by_cell.setdefault((day, sname, sess), []).append(did)
            oncall = result.assignments["oncall"]
            ext = result.assignments["ext"]
            wconsult = result.assignments["wconsult"]
            doc_by_id = {d.id: d for d in inst.doctors}

            rows = []
            for st_obj in inst.stations:
                for sess in st_obj.sessions:
                    row = {"station": st_obj.name, "session": sess}
                    for day in range(inst.n_days):
                        if inst.is_weekend(day) and not inst.weekend_am_pm_enabled:
                            row[_day_label(inst, day)] = ""
                        else:
                            ids = by_cell.get((day, st_obj.name, sess), [])
                            row[_day_label(inst, day)] = ",".join(f"D{i}" for i in ids)
                    rows.append(row)
            for row_name, filter_fn in (
                ("ONCALL-J", lambda did, day: (did, day) in oncall and doc_by_id[did].tier == "junior"),
                ("ONCALL-S", lambda did, day: (did, day) in oncall and doc_by_id[did].tier == "senior"),
                ("EXT-J", lambda did, day: (did, day) in ext and doc_by_id[did].tier == "junior"),
                ("EXT-S", lambda did, day: (did, day) in ext and doc_by_id[did].tier == "senior"),
                ("WKND-CONSULT", lambda did, day: (did, day) in wconsult),
            ):
                row = {"station": row_name, "session": ""}
                for day in range(inst.n_days):
                    matches = [did for did in doc_by_id if filter_fn(did, day)]
                    label = ",".join(
                        f"D{i}({doc_by_id[i].subspec})" if row_name == "WKND-CONSULT" else f"D{i}"
                        for i in matches
                    )
                    row[_day_label(inst, day)] = label
                rows.append(row)

            st.dataframe(pd.DataFrame(rows), use_container_width=True, height=400)

    # ------------------ Workload
    with tab_workload:
        if not qm:
            st.warning("No workload to display.")
        else:
            st.subheader("Per-doctor counts")
            rows = []
            for did, info in qm["per_doctor"].items():
                rows.append({"id": did, **info})
            st.dataframe(pd.DataFrame(rows), use_container_width=True, height=400)

            st.subheader("Balance gap per tier")
            st.dataframe(pd.DataFrame(qm["tier_balance"]).T, use_container_width=True)

            st.subheader("On-call spacing")
            st.json(qm["oncall_spacing"])

            if qm["coverage_violations"]:
                st.error("Coverage violations detected — this is a model bug:")
                for v in qm["coverage_violations"]:
                    st.write(f"  • {v}")
            else:
                st.success("All station coverage requirements (H1) satisfied.")

    # ------------------ Why infeasible?
    with tab_why:
        st.caption(
            "L3 soft-relax explainer. Relaxes H1 (station coverage) and H8 "
            "(weekend coverage) with slack variables, minimizes total slack, "
            "and reports which constraints had to be broken."
        )
        if result.status in ("OPTIMAL", "FEASIBLE"):
            st.info("Primary solve succeeded. If you still want to see the "
                    "relaxed-model output, press the button below.")
        elif result.status == "INFEASIBLE":
            st.error("Primary solve proved the instance INFEASIBLE. "
                     "Run the L3 explainer to see exactly which constraints "
                     "cannot be satisfied simultaneously.")
        else:
            st.warning("Primary solve returned status "
                       f"`{result.status}` — no guarantee of infeasibility, "
                       "but the L3 explainer may still surface structural "
                       "issues.")

        if st.button("Run L3 explainer"):
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

    # ------------------ Export
    with tab_export:
        if result.status in ("OPTIMAL", "FEASIBLE"):
            payload = {
                "meta": {
                    **{k: v for k, v in sm.items()
                       if k not in {"convergence_timeline", "penalty_components"}},
                    "n_doctors": len(inst.doctors),
                    "n_days": inst.n_days,
                    "start_weekday": inst.start_weekday,
                },
                "penalty_components": result.penalty_components,
                "stations": [
                    {"doctor": d, "day": t, "station": s, "session": sess}
                    for (d, t, s, sess) in result.assignments["stations"]
                ],
                "oncall":   [{"doctor": d, "day": t} for (d, t) in result.assignments["oncall"]],
                "ext":      [{"doctor": d, "day": t} for (d, t) in result.assignments["ext"]],
                "wconsult": [{"doctor": d, "day": t} for (d, t) in result.assignments["wconsult"]],
            }
            st.download_button("Download roster (JSON)",
                               data=json.dumps(payload, indent=2),
                               file_name="roster.json",
                               mime="application/json")

            rows = []
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
            st.download_button("Download roster (CSV)",
                               data=csv_buf.getvalue(),
                               file_name="roster.csv", mime="text/csv")
        else:
            st.info("No roster to export.")
else:
    st.info("Configure the instance in the sidebar, then click **Diagnose** "
            "or **Solve**.")
