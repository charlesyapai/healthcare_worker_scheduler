"""/api/roster — validation for manually-edited rosters."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from api.models.events import AssignmentRow
from api.sessions import ServerSession, get_session
from api.validator import validate as run_validate

router = APIRouter(prefix="/api/roster", tags=["roster"])


class ValidateRequest(BaseModel):
    assignments: list[AssignmentRow]


class Violation(BaseModel):
    rule: str
    severity: str
    location: str
    message: str


class ValidateResponse(BaseModel):
    ok: bool
    violation_count: int
    violations: list[Violation]
    rules_passed: list[str]
    rules_failed: list[str]


_ALL_RULES = ["H1", "H2", "H3", "H4", "H5", "H8", "H10", "H12", "H13", "weekday_oc"]


@router.post("/validate", response_model=ValidateResponse)
def validate_roster(
    req: ValidateRequest,
    session: ServerSession = Depends(get_session),
) -> ValidateResponse:
    """Run hard-constraint checks on a caller-provided assignment list.
    Does not run the solver — pure validation."""
    raw = run_validate(session.state, req.assignments)
    violations = [Violation(**v) for v in raw]
    failed = sorted({v.rule for v in violations})
    passed = sorted([r for r in _ALL_RULES if r not in failed])
    return ValidateResponse(
        ok=len(violations) == 0,
        violation_count=len(violations),
        violations=violations,
        rules_passed=passed,
        rules_failed=failed,
    )
