"""Generate a gallery of all 10 plots for offline viewing.

Runs a real solve on a realistic instance (20 doctors × 21 days) while
capturing intermediate events, then runs a small sweep for the three
dashboard-style plots, then renders every figure to an HTML file plus
a single index.html that embeds them all with their explanations.

Usage:
    PYTHONPATH=. python scripts/generate_plots.py
Output:
    plots_preview/index.html and plots_preview/*.html
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import pandas as pd
import plotly.io as pio

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scheduler import make_synthetic, solve
from scheduler import plots
from scheduler.metrics import problem_metrics, solution_metrics, solve_metrics

OUT = ROOT / "plots_preview"
OUT.mkdir(exist_ok=True)


def markdown_to_html(md: str) -> str:
    """Tiny markdown-to-HTML: handles the three features our docs use —
    headings, **bold**, and bullet lists. No external dep."""
    lines = md.splitlines()
    html_lines: list[str] = []
    in_list = False
    for raw in lines:
        line = raw.rstrip()
        if line.startswith("## "):
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<h3>{line[3:]}</h3>")
        elif line.startswith("- "):
            if not in_list:
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{_inline(line[2:])}</li>")
        elif line.strip() == "":
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append("<br/>")
        else:
            if in_list:
                html_lines.append("</ul>")
                in_list = False
            html_lines.append(f"<p>{_inline(line)}</p>")
    if in_list:
        html_lines.append("</ul>")
    return "\n".join(html_lines)


def _inline(s: str) -> str:
    import re
    s = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"`(.+?)`", r"<code>\1</code>", s)
    return s


def run_primary_solve():
    print(">>> building instance: 20 doctors × 21 days")
    inst = make_synthetic(n_doctors=20, n_days=21, seed=0)

    events: list[dict] = []
    t0 = time.time()

    def cb(ev):
        # model's own callback populates most of this; we just record
        ev2 = dict(ev)
        ev2["wall_s"] = time.time() - t0
        events.append(ev2)

    print(">>> solving (time_limit=45 s)")
    result = solve(inst, time_limit_s=45, on_intermediate=cb)
    print(f"    status={result.status} obj={result.objective} wall={result.wall_time_s:.2f}s")
    print(f"    captured {len(events)} intermediate events")

    # The model already exposes structured events on result. Use those if
    # they're richer; fall back to our timer-based events otherwise.
    model_events = getattr(result, "events", None) or events
    return inst, result, model_events


def run_mini_sweep() -> pd.DataFrame:
    print(">>> mini sweep for dashboard plots")
    rows = []
    for n_doctors, n_days in [(15, 14), (20, 14), (20, 21), (30, 14), (30, 21)]:
        inst = make_synthetic(n_doctors=n_doctors, n_days=n_days, seed=0)
        evs: list[dict] = []
        t0 = time.time()

        def cb(ev, _evs=evs, _t0=t0):
            e = dict(ev)
            e["wall_s"] = time.time() - _t0
            _evs.append(e)

        r = solve(inst, time_limit_s=30, on_intermediate=cb)
        first = getattr(r, "first_feasible_s", None) or (
            evs[0]["wall_s"] if evs else r.wall_time_s
        )
        rows.append(dict(
            n_doctors=n_doctors, n_days=n_days,
            status=r.status, wall_time_s=r.wall_time_s,
            first_feasible_s=first,
            n_vars=r.n_vars, n_constraints=r.n_constraints,
            objective=r.objective, best_bound=r.best_bound,
        ))
        print(f"    {n_doctors:>3}x{n_days:<2} {r.status:<10} wall={r.wall_time_s:5.2f}s "
              f"first_feas={first:5.2f}s obj={r.objective}")
    return pd.DataFrame(rows)


def render_figure(name: str, fig, explanation: str) -> Path:
    """Write one plot to a standalone HTML file."""
    path = OUT / f"{name}.html"
    explanation_html = markdown_to_html(explanation)
    fig_html = pio.to_html(fig, include_plotlyjs="cdn", full_html=False,
                           default_height="380px")
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{name}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 900px;
         margin: 2em auto; color: #222; padding: 0 1em; }}
  h1 {{ border-bottom: 1px solid #ddd; padding-bottom: 0.3em; }}
  h3 {{ color: #355; margin-top: 1.4em; }}
  code {{ background: #f4f4f4; padding: 0 3px; border-radius: 3px; }}
  ul {{ padding-left: 1.2em; }}
  .explanation {{ background: #f9f9f9; border-left: 3px solid #4a90e2;
                 padding: 0.6em 1em; margin-top: 1.5em; }}
</style></head><body>
<h1>{name}</h1>
{fig_html}
<div class="explanation">{explanation_html}</div>
<p><a href="index.html">← back to index</a></p>
</body></html>"""
    path.write_text(html)
    return path


def write_index(names: list[str], meta: dict) -> None:
    items = "\n".join(f'<li><a href="{n}.html">{n}</a></li>' for n in names)
    meta_rows = "\n".join(
        f"<tr><td>{k}</td><td>{v}</td></tr>" for k, v in meta.items()
    )
    html = f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Plot preview</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 900px;
         margin: 2em auto; padding: 0 1em; }}
  table {{ border-collapse: collapse; margin: 1em 0; }}
  td {{ border: 1px solid #ddd; padding: 4px 10px; }}
  td:first-child {{ font-weight: 600; background: #f6f6f6; }}
</style></head><body>
<h1>Plot preview</h1>
<p>Rendered offline from a real solve on a 20-doctor × 21-day instance
   (primary plots) plus a small size sweep (dashboard plots).</p>
<h3>Primary solve</h3>
<table>{meta_rows}</table>
<h3>Plots</h3>
<ul>{items}</ul>
</body></html>"""
    (OUT / "index.html").write_text(html)


def main():
    inst, result, events = run_primary_solve()
    sweep_df = run_mini_sweep()

    pm = problem_metrics(inst)
    sm = solve_metrics(result, events)

    meta = {
        "status": result.status,
        "objective": result.objective,
        "best_bound": result.best_bound,
        "wall_time_s": f"{result.wall_time_s:.2f}",
        "first_feasible_s": f"{getattr(result, 'first_feasible_s', 0) or 0:.2f}",
        "n_vars": result.n_vars,
        "n_constraints": result.n_constraints,
        "intermediate_solutions": len(events),
        "n_doctors": pm["n_doctors"],
        "n_days": pm["n_days"],
        "coverage_slack_min": f"{pm['coverage_slack_min']:.2f}",
    }

    print(">>> rendering plots")
    rendered: list[str] = []

    def add(name: str, tup):
        fig, expl = tup
        render_figure(name, fig, expl)
        rendered.append(name)
        print(f"    wrote {name}.html")

    add("convergence", plots.convergence(events,
                                          objective=result.objective,
                                          bound=result.best_bound))
    add("penalty_breakdown", plots.penalty_breakdown(events))
    add("workload_histogram", plots.workload_histogram(inst, result))
    add("oncall_spacing", plots.oncall_spacing(inst, result))
    add("roster_heatmap", plots.roster_heatmap(inst, result))
    add("coverage_heatmap", plots.coverage_heatmap(inst, result))
    add("coverage_slack", plots.coverage_slack(inst))
    add("time_size_heatmap", plots.time_size_heatmap(sweep_df))
    add("first_feasible_vs_optimal", plots.first_feasible_vs_optimal(sweep_df))
    add("complexity_scaling", plots.complexity_scaling(sweep_df))

    write_index(rendered, meta)
    print(f">>> done. open {OUT / 'index.html'}")


if __name__ == "__main__":
    main()
