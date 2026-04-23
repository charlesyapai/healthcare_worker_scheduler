"""Systematic tuning sweep across every bundled scenario × variant × seed.

Purpose: answer "does <tuning toggle> actually improve CP-SAT on our
scenarios?" with real numbers, not hand-waving. Writes a Markdown
report to `docs/TUNING_RESULTS.md` (local only — not deployed to HF).

Variants swept:
  baseline         — no tuning toggles, default CP-SAT
  symmetry_break   — lex-order on interchangeable doctors
  oncall_first     — decision_strategy = oncall_first
  redundant        — redundant_aggregates = True
  all_three        — all of the above

Each (scenario × variant × seed) cell runs CP-SAT with a fixed time
budget + single worker for determinism. Reports status, objective,
best-bound, headroom, time-to-first-feasible, and wall time.

Run from repo root:
    python scripts/benchmark_tuning.py
    python scripts/benchmark_tuning.py --budget 20 --seeds 0,1,2
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, pstdev
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api.models.session import SessionState  # noqa: E402
from api.sessions import (  # noqa: E402
    session_to_instance,
    session_to_solver_configs,
)
from scheduler.model import solve as cpsat_solve  # noqa: E402
from scheduler.persistence import load_state  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
SCENARIOS_DIR = REPO_ROOT / "configs" / "scenarios"
RESULTS_DIR = REPO_ROOT / "results" / "tuning_sweep"


VARIANTS: dict[str, dict[str, Any]] = {
    "baseline":       {},
    "symmetry":       {"symmetry_break": True},
    "oncall_first":   {"decision_strategy": "oncall_first"},
    "redundant":      {"redundant_aggregates": True},
    "all_three":      {
        "symmetry_break": True,
        "decision_strategy": "oncall_first",
        "redundant_aggregates": True,
    },
}


@dataclass
class Cell:
    scenario: str
    variant: str
    seed: int
    status: str
    objective: float | None
    best_bound: float | None
    headroom: float | None
    first_feasible_s: float | None
    wall_s: float


@dataclass
class VariantSummary:
    scenario: str
    variant: str
    n_seeds: int
    mean_obj: float | None = None
    std_obj: float | None = None
    mean_bound: float | None = None
    mean_headroom: float | None = None
    mean_first_feasible: float | None = None
    n_optimal: int = 0
    n_feasible: int = 0
    n_infeasible: int = 0


def _load_scenarios() -> dict[str, SessionState]:
    """Return {scenario_id: SessionState} for every YAML in configs/scenarios/."""
    from api.sessions import v1_dict_to_session

    out: dict[str, SessionState] = {}
    for yaml_path in sorted(SCENARIOS_DIR.glob("*.yaml")):
        scenario_id = yaml_path.stem
        updates = load_state(yaml_path.read_text())
        out[scenario_id] = v1_dict_to_session(updates, base=SessionState())
    return out


def _run_cell(
    state: SessionState,
    scenario: str,
    variant: str,
    seed: int,
    time_limit_s: float,
) -> Cell:
    kwargs = {**VARIANTS[variant]}
    inst = session_to_instance(state)
    weights, wl, cfg = session_to_solver_configs(state)
    t0 = time.perf_counter()
    result = cpsat_solve(
        inst,
        time_limit_s=time_limit_s,
        weights=weights,
        workload_weights=wl,
        constraints=cfg,
        num_workers=1,
        random_seed=seed,
        **kwargs,
    )
    elapsed = time.perf_counter() - t0
    headroom = None
    if result.objective is not None and result.best_bound is not None:
        headroom = max(0.0, float(result.objective) - float(result.best_bound))
    return Cell(
        scenario=scenario,
        variant=variant,
        seed=seed,
        status=result.status,
        objective=result.objective,
        best_bound=result.best_bound,
        headroom=headroom,
        first_feasible_s=result.first_feasible_s,
        wall_s=round(elapsed, 3),
    )


def _summarise(cells: list[Cell]) -> VariantSummary:
    if not cells:
        raise ValueError("no cells")
    s = cells[0].scenario
    v = cells[0].variant
    objectives = [c.objective for c in cells if c.objective is not None]
    bounds = [c.best_bound for c in cells if c.best_bound is not None]
    headrooms = [c.headroom for c in cells if c.headroom is not None]
    ttf = [c.first_feasible_s for c in cells if c.first_feasible_s is not None]
    return VariantSummary(
        scenario=s,
        variant=v,
        n_seeds=len(cells),
        mean_obj=round(mean(objectives), 1) if objectives else None,
        std_obj=round(pstdev(objectives), 1) if len(objectives) > 1 else 0.0,
        mean_bound=round(mean(bounds), 1) if bounds else None,
        mean_headroom=round(mean(headrooms), 1) if headrooms else None,
        mean_first_feasible=round(mean(ttf), 3) if ttf else None,
        n_optimal=sum(1 for c in cells if c.status == "OPTIMAL"),
        n_feasible=sum(1 for c in cells if c.status == "FEASIBLE"),
        n_infeasible=sum(1 for c in cells if c.status in ("INFEASIBLE", "UNKNOWN")),
    )


def _markdown_report(
    cells: list[Cell],
    summaries: list[VariantSummary],
    *,
    time_budget: float,
    seeds: list[int],
) -> str:
    lines: list[str] = []
    from datetime import date as _date

    lines.append(f"# Tuning sweep — {_date.today().isoformat()}")
    lines.append("")
    lines.append(
        f"**Budget**: {time_budget}s · **Seeds**: {seeds} · "
        f"**num_workers**: 1 (deterministic) · **Variants**: "
        f"{', '.join(VARIANTS.keys())}"
    )
    lines.append("")
    lines.append("Each cell reports mean across seeds. Lower objective = better.")
    lines.append("")

    by_scenario: dict[str, list[VariantSummary]] = {}
    for s in summaries:
        by_scenario.setdefault(s.scenario, []).append(s)

    for scenario, rows in by_scenario.items():
        lines.append(f"## {scenario}")
        lines.append("")
        lines.append(
            "| Variant | Mean obj | Std obj | Mean bound | Mean headroom "
            "| Time-to-first-feasible | Status counts |"
        )
        lines.append(
            "|---|---:|---:|---:|---:|---:|---|"
        )
        baseline = next((r for r in rows if r.variant == "baseline"), None)
        for r in rows:
            delta = ""
            if baseline and r.mean_obj is not None and baseline.mean_obj is not None:
                diff = r.mean_obj - baseline.mean_obj
                if r.variant != "baseline" and diff != 0:
                    sign = "+" if diff > 0 else ""
                    pct = (100.0 * diff / baseline.mean_obj) if baseline.mean_obj else 0
                    delta = f" ({sign}{diff:.0f} / {sign}{pct:.1f}%)"
            lines.append(
                f"| {r.variant} | {r.mean_obj}{delta} | {r.std_obj} | "
                f"{r.mean_bound} | {r.mean_headroom} | "
                f"{r.mean_first_feasible}s | "
                f"O={r.n_optimal} F={r.n_feasible} ¬={r.n_infeasible} |"
            )
        lines.append("")

    lines.append("## How to read this")
    lines.append("")
    lines.append(
        "- **Mean obj**: average final objective across seeds. Negative delta "
        "vs baseline = improvement (lower is better)."
    )
    lines.append(
        "- **Mean bound**: CP-SAT's best-proved lower bound on the objective. "
        "Higher = more honest feasibility gap. A tuning toggle that raises the "
        "bound *without changing the objective* still helps — researchers can "
        "cite tighter optimality claims."
    )
    lines.append(
        "- **Mean headroom**: `objective - bound`. When it reaches zero the "
        "solver has proven optimality. Lower is better."
    )
    lines.append(
        "- **Time-to-first-feasible**: seconds to find any feasible solution. "
        "Important for UI responsiveness."
    )
    lines.append("")
    lines.append(
        "⚠ Every cell ran under a fixed time budget. The reported gap between "
        "CP-SAT and tuned variants is often more about **where the solver was "
        "in its search at the time limit** than about the tuning's long-run "
        "quality. For publication-grade claims, re-run with a longer budget "
        "(≥ 5 minutes per cell) and ≥ 30 seeds."
    )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--budget", type=float, default=30.0,
                        help="time limit per cell, seconds")
    parser.add_argument("--seeds", type=str, default="0,1,2",
                        help="comma-separated seeds")
    parser.add_argument("--scenarios", type=str, default="all",
                        help="comma-separated scenario IDs, or 'all'")
    parser.add_argument("--out", type=str,
                        default=str(REPO_ROOT / "docs" / "TUNING_RESULTS.md"))
    args = parser.parse_args()

    seeds = [int(s) for s in args.seeds.split(",") if s.strip()]
    scenarios = _load_scenarios()
    if args.scenarios != "all":
        wanted = {s.strip() for s in args.scenarios.split(",") if s.strip()}
        scenarios = {k: v for k, v in scenarios.items() if k in wanted}

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    cells: list[Cell] = []
    total = len(scenarios) * len(VARIANTS) * len(seeds)
    i = 0
    for scenario_id, state in scenarios.items():
        for variant in VARIANTS:
            for seed in seeds:
                i += 1
                print(f"[{i}/{total}] {scenario_id} · {variant} · seed={seed} "
                      f"budget={args.budget}s … ", end="", flush=True)
                c = _run_cell(state, scenario_id, variant, seed, args.budget)
                cells.append(c)
                print(f"{c.status} obj={c.objective} bound={c.best_bound} "
                      f"t={c.wall_s:.1f}s")

    summaries: list[VariantSummary] = []
    for scenario_id in scenarios:
        for variant in VARIANTS:
            cells_for_cell = [
                c for c in cells
                if c.scenario == scenario_id and c.variant == variant
            ]
            if cells_for_cell:
                summaries.append(_summarise(cells_for_cell))

    # Write raw data too, so the report is auditable and researchers can
    # re-aggregate under different statistics.
    (RESULTS_DIR / "cells.json").write_text(
        json.dumps([c.__dict__ for c in cells], indent=2, default=str)
    )

    report = _markdown_report(cells, summaries, time_budget=args.budget, seeds=seeds)
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report)
    print(f"\nWrote report → {out_path}")
    print(f"Wrote raw cells → {RESULTS_DIR / 'cells.json'}")


if __name__ == "__main__":
    main()
