"""/api/diagnose (L1) + /api/explain (L3) endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.models.events import ExplainReport, ExplainViolation, FeasibilityIssueOut
from api.sessions import ServerSession, get_session, session_to_instance
from scheduler.diagnostics import explain_infeasibility, presolve_feasibility
from scheduler.ui_state import BuildError

router = APIRouter(prefix="/api", tags=["diagnostics"])


@router.post("/diagnose", response_model=list[FeasibilityIssueOut])
def diagnose(session: ServerSession = Depends(get_session)) -> list[FeasibilityIssueOut]:
    """Millisecond necessary-condition checks (L1)."""
    try:
        inst = session_to_instance(session.state)
    except BuildError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    issues = presolve_feasibility(inst)
    return [
        FeasibilityIssueOut(
            severity=i.severity,
            code=i.code,
            message=i.message,
            detail=i.detail,
        )
        for i in issues
    ]


@router.post("/explain", response_model=ExplainReport)
def explain(session: ServerSession = Depends(get_session)) -> ExplainReport:
    """Soft-relax diagnostic (L3). ~30 s — use only after an INFEASIBLE solve."""
    try:
        inst = session_to_instance(session.state)
    except BuildError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    report = explain_infeasibility(
        inst,
        time_limit_s=min(30.0, float(session.state.solver.time_limit)),
        num_workers=session.state.solver.num_workers,
    )
    return ExplainReport(
        status=report.status,
        wall_time_s=report.wall_time_s,
        total_slack=report.total_slack,
        violations=[
            ExplainViolation(code=v.code, location=v.location,
                             amount=v.amount, message=v.message)
            for v in report.violations
        ],
        note=report.note,
    )
