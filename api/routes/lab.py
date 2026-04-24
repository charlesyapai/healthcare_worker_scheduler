"""/api/lab — batch runner + history.

Phase 2 endpoints:
  POST /api/lab/run        → run a batch (solvers × seeds on current state)
  GET  /api/lab/runs       → list recent batches
  GET  /api/lab/runs/{id}  → full detail for one batch (+ per-run payloads)

Everything is synchronous and in-memory. Reproducibility bundle export
lands in Phase 3 per `docs/LAB_TAB_SPEC.md §2.3`.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from api.lab.batch import get_batch, list_batches, run_batch
from api.lab.bundle import build_bundle
from api.lab.capacity import run_capacity
from api.lab.scaling import run_scaling
from api.models.lab import (
    BatchRunRequest,
    BatchSummary,
    CapacityRequest,
    CapacityResponse,
    RunHistoryEntry,
    ScalingRequest,
    ScalingResponse,
    SingleRunDetail,
)
from api.sessions import ServerSession, get_session

router = APIRouter(prefix="/api/lab", tags=["lab"])


@router.post("/run", response_model=BatchSummary)
def run(
    req: BatchRunRequest,
    session: ServerSession = Depends(get_session),
) -> BatchSummary:
    """Execute a cross-product of (solver × seed) on the current session
    state. Blocks until every cell finishes. Callers should keep batches
    modest (≤ 3 solvers × ≤ 5 seeds × ≤ 30 s budget) until Phase 3 adds
    a background-job path."""
    if not session.state.doctors or not session.state.stations:
        raise HTTPException(
            status_code=400,
            detail="Seed doctors + stations first (POST /api/state/seed or load a scenario).",
        )
    return run_batch(session.state, req)


@router.get("/runs", response_model=list[RunHistoryEntry])
def list_runs() -> list[RunHistoryEntry]:
    """Most-recent-first list of batches stored in memory (LRU cap 50)."""
    return list_batches()


@router.get("/runs/{batch_id}")
def get_batch_detail(batch_id: str) -> dict[str, Any]:
    b = get_batch(batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail=f"Unknown batch: {batch_id}")
    return {
        "summary": b.summary.model_dump(mode="json"),
        "details": {k: v.model_dump(mode="json") for k, v in b.details.items()},
    }


@router.get("/runs/{batch_id}/details/{run_id}", response_model=SingleRunDetail)
def get_run_detail(batch_id: str, run_id: str) -> SingleRunDetail:
    b = get_batch(batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail=f"Unknown batch: {batch_id}")
    d = b.details.get(run_id)
    if d is None:
        raise HTTPException(
            status_code=404, detail=f"Unknown run in this batch: {run_id}"
        )
    return d


@router.post("/scaling/run", response_model=ScalingResponse)
def scaling_run(req: ScalingRequest) -> ScalingResponse:
    """Run CP-SAT across a grid of synthetic instance sizes and fit a
    power law T = a · N^b where N = n_doctors × n_days. See
    `docs/LAB_TAB_SPEC.md §5`. Synchronous; bound your grid × seeds ×
    time_limit to keep this under ~2 minutes."""
    return run_scaling(req)


@router.post("/capacity/run", response_model=CapacityResponse)
def capacity_run(
    req: CapacityRequest,
    session: ServerSession = Depends(get_session),
) -> CapacityResponse:
    """Analyse manpower / team sizing on the current session state.

    Two modes:

    * **hours_vs_target** — single CP-SAT solve, then compute each
      doctor's worked hours (from the session's `Hours` weights) and
      compare to `target_hours_per_week × fte`. Fast: one solve.
    * **team_reduction** — baseline solve + up to `max_drop` iterative
      re-solves with the lowest-loaded doctor dropped each step. Slow:
      up to `(max_drop + 1) × time_limit_s` wall time.

    The session state is never mutated — analyses run on a snapshot
    copy. Returns a ``CapacityResponse`` shaped by the requested mode.
    """
    if not session.state.doctors or not session.state.stations:
        raise HTTPException(
            status_code=400,
            detail=(
                "Seed doctors + stations first "
                "(POST /api/state/seed or load a scenario)."
            ),
        )
    return run_capacity(session.state, req)


@router.get("/runs/{batch_id}/bundle.zip")
def download_bundle(batch_id: str) -> Response:
    """Reproducibility bundle (ZIP): state.yaml + run_config.json +
    results.json + git_sha.txt + requirements.txt + README.md. See
    `docs/HOW_TO_REPRODUCE.md` for the replay walkthrough."""
    b = get_batch(batch_id)
    if b is None:
        raise HTTPException(status_code=404, detail=f"Unknown batch: {batch_id}")
    # Lazy import to avoid a cycle at module load.
    from api.main import GIT_SHA
    body = build_bundle(b, GIT_SHA)
    return Response(
        content=body,
        media_type="application/zip",
        headers={
            "Content-Disposition":
                f'attachment; filename="lab_bundle_{batch_id}.zip"',
        },
    )
