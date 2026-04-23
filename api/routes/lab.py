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

from api.lab.batch import get_batch, list_batches, run_batch
from api.models.lab import (
    BatchRunRequest,
    BatchSummary,
    RunHistoryEntry,
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
