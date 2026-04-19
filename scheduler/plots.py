"""Plotly figure builders for the UI and the static dashboard.

Every builder returns a tuple (figure, explanation_md). The explanation is
the canonical docstring for that plot — shown inline in the UI under the
chart and also copied into `docs/plots/*.md` at repo level.

The .md files under docs/plots/ are the source of truth; this module loads
them at call time so edits to a .md file are reflected immediately.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from scheduler.instance import Instance
from scheduler.model import SolveResult

_DOCS_DIR = Path(__file__).resolve().parent.parent / "docs" / "plots"


def _load_explanation(name: str) -> str:
    p = _DOCS_DIR / f"{name}.md"
    if not p.exists():
        return f"(explanation doc `{p}` not found)"
    return p.read_text()


# ---------------------------------------------------------- convergence

def convergence(events: list[dict], *, objective: float | None = None,
                bound: float | None = None) -> tuple[go.Figure, str]:
    """Objective and best-bound over wall time. Step plot."""
    if not events:
        fig = go.Figure()
        fig.update_layout(title="No intermediate solutions yet")
        return fig, _load_explanation("convergence")

    df = pd.DataFrame(events)
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=df["wall_s"], y=df["objective"], mode="lines+markers",
        name="Objective (upper)", line=dict(shape="hv")))
    fig.add_trace(go.Scatter(
        x=df["wall_s"], y=df["best_bound"], mode="lines+markers",
        name="Best bound (lower)", line=dict(shape="hv", dash="dot")))
    if objective is not None:
        fig.add_hline(y=objective, line=dict(dash="dash", color="green"),
                      annotation_text=f"final obj={objective}")
    fig.update_layout(
        xaxis_title="Wall time (s)",
        yaxis_title="Objective value",
        hovermode="x unified",
        height=350,
        margin=dict(l=40, r=20, t=30, b=40),
    )
    return fig, _load_explanation("convergence")


# ---------------------------------------------------------- penalty breakdown

def penalty_breakdown(events: list[dict]) -> tuple[go.Figure, str]:
    """Stacked-area chart of each penalty component over wall time."""
    if not events or not events[0].get("components"):
        fig = go.Figure()
        fig.update_layout(title="No component data")
        return fig, _load_explanation("penalty_breakdown")

    rows = []
    for e in events:
        for name, val in e["components"].items():
            rows.append({"wall_s": e["wall_s"], "component": name, "value": val})
    df = pd.DataFrame(rows)
    fig = px.area(df, x="wall_s", y="value", color="component",
                  line_shape="hv",
                  labels={"wall_s": "Wall time (s)", "value": "Weighted penalty"})
    fig.update_layout(height=350, margin=dict(l=40, r=20, t=30, b=40))
    return fig, _load_explanation("penalty_breakdown")


# ---------------------------------------------------------- workload histogram

def workload_histogram(inst: Instance, result: SolveResult) -> tuple[go.Figure, str]:
    """Per-doctor AM/PM / oncall / weekend count, faceted by tier."""
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        return go.Figure(), _load_explanation("workload_histogram")
    from scheduler.metrics import solution_metrics
    m = solution_metrics(inst, result)
    rows = []
    for did, info in m["per_doctor"].items():
        for metric, val in (
            ("am_pm", info["am_pm"]),
            ("oncall", info["oncall"]),
            ("weekend_ext", info["weekend_ext"]),
            ("weekend_consult", info["weekend_consult"]),
        ):
            rows.append({"doctor": did, "tier": info["tier"],
                         "metric": metric, "value": val})
    df = pd.DataFrame(rows)
    fig = px.histogram(df, x="value", color="tier", facet_col="metric",
                       barmode="group", nbins=12)
    fig.update_layout(height=350, margin=dict(l=40, r=20, t=40, b=40))
    return fig, _load_explanation("workload_histogram")


# ---------------------------------------------------------- oncall spacing

def oncall_spacing(inst: Instance, result: SolveResult) -> tuple[go.Figure, str]:
    """Histogram of inter-oncall gaps (days) across all doctors."""
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        return go.Figure(), _load_explanation("oncall_spacing")
    oncall = result.assignments.get("oncall", {})
    by_doc: dict[int, list[int]] = {}
    for (did, day) in oncall:
        by_doc.setdefault(did, []).append(day)
    spacings = []
    for days in by_doc.values():
        days.sort()
        for i in range(1, len(days)):
            spacings.append(days[i] - days[i - 1])
    if not spacings:
        return go.Figure(), _load_explanation("oncall_spacing")
    fig = px.histogram(pd.DataFrame({"gap_days": spacings}), x="gap_days",
                       nbins=max(spacings) - 2)
    fig.add_vline(x=3, line=dict(dash="dash", color="red"),
                  annotation_text="1-in-3 floor")
    fig.update_layout(height=300, margin=dict(l=40, r=20, t=30, b=40),
                      xaxis_title="Days between successive on-calls for the same doctor",
                      yaxis_title="Count")
    return fig, _load_explanation("oncall_spacing")


# ---------------------------------------------------------- roster heatmap

def roster_heatmap(inst: Instance, result: SolveResult) -> tuple[go.Figure, str]:
    """Doctor × day grid, color = role (AM=1, PM=2, AM+PM=3, oncall=4, ext=5,
    wconsult=6, leave=-1)."""
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        return go.Figure(), _load_explanation("roster_heatmap")
    doc_ids = [d.id for d in inst.doctors]
    doc_id_to_idx = {did: i for i, did in enumerate(doc_ids)}
    n_rows = len(doc_ids)
    grid = [[0] * inst.n_days for _ in range(n_rows)]

    # Leave
    for did, days in inst.leave.items():
        if did in doc_id_to_idx:
            i = doc_id_to_idx[did]
            for t in days:
                if 0 <= t < inst.n_days:
                    grid[i][t] = -1

    for (did, day, _, sess) in result.assignments["stations"]:
        i = doc_id_to_idx[did]
        cur = grid[i][day]
        # 1 = AM only, 2 = PM only, 3 = both
        add = 1 if sess == "AM" else 2
        grid[i][day] = max(cur, 0) | add if cur != -1 else -1
    # Sanitize bitmask collisions: -1 stays -1
    for (did, day) in result.assignments["oncall"]:
        grid[doc_id_to_idx[did]][day] = 4
    for (did, day) in result.assignments["ext"]:
        grid[doc_id_to_idx[did]][day] = 5
    for (did, day) in result.assignments["wconsult"]:
        grid[doc_id_to_idx[did]][day] = 6

    fig = go.Figure(data=go.Heatmap(
        z=grid,
        x=[f"d{t:02d}" for t in range(inst.n_days)],
        y=[f"D{did}" for did in doc_ids],
        colorscale=[
            [0.00, "#eeeeee"],  # 0 off
            [0.10, "#cfe8ff"],  # 1 AM
            [0.30, "#9fc9ff"],  # 2 PM
            [0.45, "#4a90e2"],  # 3 AM+PM
            [0.60, "#ffcc66"],  # 4 oncall
            [0.80, "#ff8855"],  # 5 ext
            [1.00, "#aa66cc"],  # 6 wconsult
        ],
        zmin=-1, zmax=6,
        showscale=False,
    ))
    fig.update_layout(height=max(350, 14 * n_rows),
                      margin=dict(l=40, r=20, t=30, b=40))
    return fig, _load_explanation("roster_heatmap")


# ---------------------------------------------------------- coverage heatmap

def coverage_heatmap(inst: Instance, result: SolveResult) -> tuple[go.Figure, str]:
    """Days (y) × station×session (x). Cell = number of doctors assigned."""
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        return go.Figure(), _load_explanation("coverage_heatmap")
    cols = [f"{st.name}/{sess}" for st in inst.stations for sess in st.sessions]
    col_to_idx = {c: i for i, c in enumerate(cols)}
    grid = [[0] * len(cols) for _ in range(inst.n_days)]
    for (_, day, sname, sess) in result.assignments["stations"]:
        key = f"{sname}/{sess}"
        grid[day][col_to_idx[key]] += 1
    fig = go.Figure(data=go.Heatmap(
        z=grid,
        x=cols,
        y=[f"d{t:02d}" for t in range(inst.n_days)],
        colorscale="Blues",
        showscale=True,
    ))
    fig.update_layout(height=max(350, 14 * inst.n_days),
                      margin=dict(l=40, r=20, t=30, b=40))
    return fig, _load_explanation("coverage_heatmap")


# ---------------------------------------------------------- time-size heatmap

def time_size_heatmap(sweep_df: pd.DataFrame) -> tuple[go.Figure, str]:
    """Heatmap of median wall-time by (N_doctors, N_days). For the dashboard."""
    if sweep_df.empty:
        return go.Figure(), _load_explanation("time_size_heatmap")
    pivot = (sweep_df.groupby(["n_doctors", "n_days"])["wall_time_s"]
             .median().reset_index()
             .pivot(index="n_doctors", columns="n_days", values="wall_time_s"))
    fig = go.Figure(data=go.Heatmap(
        z=pivot.values,
        x=[str(c) for c in pivot.columns],
        y=[str(r) for r in pivot.index],
        colorscale="YlOrRd",
        colorbar=dict(title="Median s"),
        text=[[f"{v:.1f}" for v in row] for row in pivot.values],
        texttemplate="%{text}",
    ))
    fig.update_layout(xaxis_title="Days", yaxis_title="Doctors",
                      height=350, margin=dict(l=40, r=20, t=30, b=40))
    return fig, _load_explanation("time_size_heatmap")


# ---------------------------------------------------------- first-feasible bar

def first_feasible_vs_optimal(sweep_df: pd.DataFrame) -> tuple[go.Figure, str]:
    """Time to first feasible vs time to final status, per problem size."""
    if sweep_df.empty:
        return go.Figure(), _load_explanation("first_feasible_vs_optimal")
    df = sweep_df.copy()
    df["label"] = df.apply(lambda r: f"{int(r['n_doctors'])}×{int(r['n_days'])}", axis=1)
    fig = go.Figure()
    fig.add_trace(go.Bar(x=df["label"], y=df["first_feasible_s"],
                         name="First feasible"))
    fig.add_trace(go.Bar(x=df["label"], y=df["wall_time_s"],
                         name="Total wall time"))
    fig.update_layout(barmode="group",
                      xaxis_title="Problem size (doctors × days)",
                      yaxis_title="Seconds",
                      height=350, margin=dict(l=40, r=20, t=30, b=40))
    return fig, _load_explanation("first_feasible_vs_optimal")


# ---------------------------------------------------------- complexity scaling

def complexity_scaling(sweep_df: pd.DataFrame) -> tuple[go.Figure, str]:
    """Log-log scatter of variable count vs N×D, colored by status."""
    if sweep_df.empty:
        return go.Figure(), _load_explanation("complexity_scaling")
    df = sweep_df.copy()
    df["n_d_times_days"] = df["n_doctors"] * df["n_days"]
    fig = px.scatter(df, x="n_d_times_days", y="n_vars",
                     color="status", size="wall_time_s",
                     hover_data=["n_doctors", "n_days", "wall_time_s", "objective"],
                     log_x=True, log_y=True,
                     labels={"n_d_times_days": "N_doctors × N_days",
                             "n_vars": "Variable count"})
    fig.update_layout(height=350, margin=dict(l=40, r=20, t=30, b=40))
    return fig, _load_explanation("complexity_scaling")


# ---------------------------------------------------------- coverage slack

def coverage_slack(inst: Instance) -> tuple[go.Figure, str]:
    """Per-day `available_sessions / required_sessions` bar chart."""
    from scheduler.metrics import problem_metrics
    pm = problem_metrics(inst)
    by_day = pm["coverage_slack_by_day"]
    if not by_day:
        return go.Figure(), _load_explanation("coverage_slack")
    xs = sorted(by_day.keys())
    ys = [by_day[t] for t in xs]
    fig = go.Figure(go.Bar(x=[f"d{t:02d}" for t in xs], y=ys))
    fig.add_hline(y=1.0, line=dict(color="red", dash="dash"),
                  annotation_text="infeasible below this line")
    fig.update_layout(xaxis_title="Day",
                      yaxis_title="available / required sessions",
                      height=300, margin=dict(l=40, r=20, t=30, b=40))
    return fig, _load_explanation("coverage_slack")
