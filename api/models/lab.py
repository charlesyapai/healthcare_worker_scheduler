"""Pydantic models for the Lab tab's batch runner.

Shape mirrors `docs/LAB_TAB_SPEC.md §7`. A RunConfig captures all the
knobs that make a solve reproducible (seed, CP-SAT parameters, time
limit). A BatchRunRequest enumerates (instance × solver × seed)
tuples. SingleRun + BatchSummary cover the response shape."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from api.models.events import SolveResultPayload

SolverKey = Literal["cpsat", "greedy", "random_repair"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


SearchBranching = Literal[
    "AUTOMATIC",
    "FIXED_SEARCH",
    "PORTFOLIO_SEARCH",
    "LP_SEARCH",
    "PSEUDO_COST_SEARCH",
    "PORTFOLIO_WITH_QUICK_RESTART_SEARCH",
]


class RunConfig(StrictModel):
    """Full CP-SAT parameter surface — the set of knobs a reviewer needs
    to replay a batch bit-for-bit. Pass-through to `scheduler.solve()`.

    For reproducible runs set `num_workers=1` — the parallel portfolio
    is not deterministic even with a fixed `random_seed`.
    """

    time_limit_s: float = 30.0
    num_workers: int = 1
    random_seed: int = 0
    feasibility_only: bool = False
    search_branching: SearchBranching = "AUTOMATIC"
    linearization_level: int = 1
    cp_model_presolve: bool = True
    optimize_with_core: bool = False
    use_lns_only: bool = False


class BatchRunRequest(StrictModel):
    """One batch = current session state × listed solvers × listed seeds."""

    solvers: list[SolverKey] = Field(default_factory=lambda: ["cpsat"])
    seeds: list[int] = Field(default_factory=lambda: [0])
    run_config: RunConfig = Field(default_factory=RunConfig)


class SingleRun(StrictModel):
    """One cell of (solver, seed) in the batch's cross product."""

    run_id: str
    solver: SolverKey
    seed: int
    status: str                     # OPTIMAL / FEASIBLE / HEURISTIC / INFEASIBLE / UNKNOWN
    wall_time_s: float
    objective: float | None
    best_bound: float | None
    headroom: float | None          # absolute gap objective - best_bound
    first_feasible_s: float | None
    self_check_ok: bool | None
    violation_count: int | None
    coverage_shortfall: int
    coverage_over: int
    n_assignments: int
    notes: str = ""


class BatchSummary(StrictModel):
    """Aggregate of one batch run. Quality ratio vs the first baseline
    in the request is reported as `quality_ratio_vs_*` if both solvers
    ran on at least one shared seed."""

    batch_id: str
    created_at: datetime
    instance_label: str
    n_doctors: int
    n_stations: int
    n_days: int
    run_config: RunConfig
    runs: list[SingleRun]
    # Comparative metrics — only populated when ≥2 solvers in the batch.
    feasibility_rate: dict[str, float] = Field(default_factory=dict)
    mean_objective: dict[str, float | None] = Field(default_factory=dict)
    mean_shortfall: dict[str, float] = Field(default_factory=dict)
    quality_ratios: dict[str, float] = Field(default_factory=dict)


class RunHistoryEntry(StrictModel):
    batch_id: str
    created_at: datetime
    instance_label: str
    n_runs: int
    solvers: list[str]
    n_seeds: int


class SingleRunDetail(StrictModel):
    """Full payload for one run — the assignments + self-check are kept
    here rather than on `SingleRun` so the benchmark-table response
    stays lightweight."""

    run_id: str
    batch_id: str
    solver: SolverKey
    seed: int
    result: SolveResultPayload
    coverage: dict[str, object] = Field(default_factory=dict)
    fairness: dict[str, object] = Field(default_factory=dict)
