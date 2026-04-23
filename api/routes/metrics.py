"""/api/metrics/* — per-solve analysis metrics.

Pure computations over a caller-provided assignment list, using the
current session's doctors / stations / weights / horizon / public
holidays as the reference configuration. No solver invocation.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.metrics.coverage import compute_coverage
from api.metrics.fairness import compute_fairness
from api.models.events import AssignmentRow
from api.sessions import ServerSession, get_session

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


class AssignmentsBody(BaseModel):
    assignments: list[AssignmentRow]


@router.post("/fairness")
def fairness(
    req: AssignmentsBody,
    session: ServerSession = Depends(get_session),
) -> dict[str, Any]:
    """FTE-aware per-tier fairness metrics for a caller-provided roster.

    Formulae documented in `docs/RESEARCH_METRICS.md §4`. Reports Gini
    (our convention) + CV (NRP-literature standard) alongside range,
    std, mean, and per-individual delta-from-median."""
    return compute_fairness(session.state, req.assignments)


@router.post("/coverage")
def coverage(
    req: AssignmentsBody,
    session: ServerSession = Depends(get_session),
) -> dict[str, Any]:
    """Coverage shortfall + over-coverage per the NRP literature.

    Formulae in `docs/RESEARCH_METRICS.md §5.1b`. For a feasible solve
    under H1 both totals are zero — useful signal comes from running
    the greedy / random-repair baselines, which frequently leave gaps."""
    return compute_coverage(session.state, req.assignments)
