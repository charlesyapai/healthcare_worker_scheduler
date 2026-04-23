"""Batch runner: execute a cross-product of (solver × seed) on one
instance and aggregate comparative metrics.

Single-process, serial execution. The caller's request is blocking;
that's fine for Phase 2 benchmarks at 3 solvers × a few seeds. Long
sweeps (30+ seeds × 30s budgets) belong on a dedicated thread or a
background job — tracked as a Phase 3 polish per
`docs/LAB_TAB_SPEC.md §9.1`.
"""

from __future__ import annotations

import time
import uuid
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Any

from api.metrics.coverage import compute_coverage
from api.metrics.fairness import compute_fairness
from api.models.events import AssignmentRow
from api.models.lab import (
    BatchRunRequest,
    BatchSummary,
    RunConfig,
    RunHistoryEntry,
    SingleRun,
    SingleRunDetail,
    SolverKey,
)
from api.models.session import SessionState
from api.sessions import (
    assignments_to_rows,
    build_self_check,
    session_to_instance,
    session_to_solver_configs,
)
from scheduler.baselines import greedy_baseline, random_repair_baseline
from scheduler.model import solve as cpsat_solve, SolveResult


# ------------------------------------------------------------- LRU store

_MAX_BATCHES = 50
_BATCH_STORE: "OrderedDict[str, _StoredBatch]" = OrderedDict()


class _StoredBatch:
    __slots__ = ("summary", "details")

    def __init__(self, summary: BatchSummary, details: dict[str, SingleRunDetail]) -> None:
        self.summary = summary
        self.details = details


def _remember(batch: _StoredBatch) -> None:
    _BATCH_STORE[batch.summary.batch_id] = batch
    _BATCH_STORE.move_to_end(batch.summary.batch_id)
    while len(_BATCH_STORE) > _MAX_BATCHES:
        _BATCH_STORE.popitem(last=False)


def list_batches() -> list[RunHistoryEntry]:
    """Return recent batches, most-recent first."""
    out: list[RunHistoryEntry] = []
    for b in reversed(_BATCH_STORE.values()):
        s = b.summary
        out.append(RunHistoryEntry(
            batch_id=s.batch_id,
            created_at=s.created_at,
            instance_label=s.instance_label,
            n_runs=len(s.runs),
            solvers=sorted({r.solver for r in s.runs}),
            n_seeds=len({r.seed for r in s.runs}),
        ))
    return out


def get_batch(batch_id: str) -> _StoredBatch | None:
    return _BATCH_STORE.get(batch_id)


def reset_store() -> None:
    """Test helper."""
    _BATCH_STORE.clear()


# ------------------------------------------------------------- one run

def _run_one(
    state: SessionState,
    solver: SolverKey,
    seed: int,
    run_config: RunConfig,
) -> tuple[SolveResult, list[AssignmentRow]]:
    """Execute one (solver, seed) cell. Returns the SolveResult plus the
    flattened assignment rows (used by coverage/fairness metrics)."""
    inst = session_to_instance(state)
    if solver == "cpsat":
        weights, wl_weights, cfg = session_to_solver_configs(state)
        # Inst has no per-solve seed field; CP-SAT parameters are threaded
        # through scheduler.solve() directly. For Phase 2 we only vary the
        # num_workers + time_limit + feasibility_only; `random_seed` hook
        # lands with Phase 3's RunConfig expansion.
        result = cpsat_solve(
            inst,
            time_limit_s=float(run_config.time_limit_s),
            weights=weights,
            workload_weights=wl_weights,
            constraints=cfg,
            num_workers=int(run_config.num_workers),
            feasibility_only=bool(run_config.feasibility_only),
        )
    elif solver == "greedy":
        result = greedy_baseline(inst)
    elif solver == "random_repair":
        result = random_repair_baseline(inst, seed=seed)
    else:
        raise ValueError(f"Unknown solver: {solver}")
    rows = assignments_to_rows(state, result.assignments or {})
    return result, rows


# ------------------------------------------------------------- batch

def run_batch(
    state: SessionState,
    req: BatchRunRequest,
    *,
    instance_label: str | None = None,
) -> BatchSummary:
    """Run a batch of (solver × seed) cells, aggregate metrics, store."""
    batch_id = uuid.uuid4().hex[:12]
    now = datetime.now(timezone.utc)
    runs: list[SingleRun] = []
    details: dict[str, SingleRunDetail] = {}

    # One instance-shape fingerprint so the UI knows what was solved.
    label = instance_label or _default_label(state)

    for solver in req.solvers:
        for seed in req.seeds:
            run_id = uuid.uuid4().hex[:10]
            t0 = time.perf_counter()
            try:
                result, rows = _run_one(state, solver, seed, req.run_config)
            except Exception as e:
                runs.append(SingleRun(
                    run_id=run_id,
                    solver=solver,
                    seed=seed,
                    status="ERROR",
                    wall_time_s=round(time.perf_counter() - t0, 3),
                    objective=None,
                    best_bound=None,
                    headroom=None,
                    first_feasible_s=None,
                    self_check_ok=None,
                    violation_count=None,
                    coverage_shortfall=0,
                    coverage_over=0,
                    n_assignments=0,
                    notes=f"{type(e).__name__}: {e}",
                ))
                continue

            # Self-check (validator-in-the-loop) — defensive so baselines
            # which legitimately leave gaps still flow through.
            self_check_ok: bool | None = None
            violation_count: int | None = None
            try:
                sc = build_self_check(state, rows)
                self_check_ok = sc.ok
                violation_count = sc.violation_count
            except Exception:
                pass

            coverage = compute_coverage(state, rows)
            fairness = compute_fairness(state, rows)

            headroom: float | None = None
            if result.objective is not None and result.best_bound is not None:
                headroom = max(0.0, float(result.objective) - float(result.best_bound))

            runs.append(SingleRun(
                run_id=run_id,
                solver=solver,
                seed=seed,
                status=result.status,
                wall_time_s=float(result.wall_time_s),
                objective=result.objective,
                best_bound=result.best_bound,
                headroom=headroom,
                first_feasible_s=result.first_feasible_s,
                self_check_ok=self_check_ok,
                violation_count=violation_count,
                coverage_shortfall=int(coverage.get("shortfall_total", 0)),
                coverage_over=int(coverage.get("over_total", 0)),
                n_assignments=len(rows),
            ))

            # Full detail stored separately (fat payload, lazy-fetched).
            from api.sessions import solve_result_to_payload
            detail_payload = solve_result_to_payload(state, result)
            details[run_id] = SingleRunDetail(
                run_id=run_id,
                batch_id=batch_id,
                solver=solver,
                seed=seed,
                result=detail_payload,
                coverage=coverage,
                fairness=fairness,
            )

    summary = BatchSummary(
        batch_id=batch_id,
        created_at=now,
        instance_label=label,
        n_doctors=len(state.doctors),
        n_stations=len(state.stations),
        n_days=state.horizon.n_days,
        run_config=req.run_config,
        runs=runs,
    )
    _populate_aggregates(summary)
    _remember(_StoredBatch(summary=summary, details=details))
    return summary


def _default_label(state: SessionState) -> str:
    return (
        f"{len(state.doctors)}p × {state.horizon.n_days}d"
        + (f" from {state.horizon.start_date.isoformat()}"
           if state.horizon.start_date else "")
    )


def _populate_aggregates(summary: BatchSummary) -> None:
    """Fill feasibility_rate / mean_objective / mean_shortfall /
    quality_ratios from the SingleRun list. Feasibility here means the
    self-check passed — a tighter standard than "solver returned some
    roster" because baselines often return partial rosters that break H1.
    """
    by_solver: dict[str, list[SingleRun]] = {}
    for r in summary.runs:
        by_solver.setdefault(r.solver, []).append(r)

    feasibility_rate = {}
    mean_objective: dict[str, float | None] = {}
    mean_shortfall = {}
    for solver, runs in by_solver.items():
        feas = [r for r in runs if r.self_check_ok]
        feasibility_rate[solver] = round(len(feas) / len(runs), 3) if runs else 0.0
        objectives = [r.objective for r in runs if r.objective is not None]
        mean_objective[solver] = (
            round(sum(objectives) / len(objectives), 2) if objectives else None
        )
        shortfalls = [r.coverage_shortfall for r in runs]
        mean_shortfall[solver] = (
            round(sum(shortfalls) / len(shortfalls), 2) if shortfalls else 0.0
        )

    # Quality ratio vs each baseline. Q = Z_baseline / Z_ours.
    # Only defined when both have a mean objective.
    ours = mean_objective.get("cpsat")
    quality_ratios: dict[str, float] = {}
    if ours is not None and ours > 0:
        for solver, their_mean in mean_objective.items():
            if solver == "cpsat" or their_mean is None or their_mean <= 0:
                continue
            quality_ratios[f"cpsat_vs_{solver}"] = round(their_mean / ours, 3)

    summary.feasibility_rate = feasibility_rate
    summary.mean_objective = mean_objective
    summary.mean_shortfall = mean_shortfall
    summary.quality_ratios = quality_ratios
