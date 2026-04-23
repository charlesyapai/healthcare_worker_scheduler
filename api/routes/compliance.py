"""/api/compliance/* — post-solve statutory audits.

Layered on top of `/api/metrics/*` for reviewers / procurement who need
a "passes UK WTD" (or analogous) claim on top of H1–H15 feasibility.

See `docs/INDUSTRY_CONTEXT.md §5` and
`api/compliance/uk_wtd.py` for the rule-set.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field

from api.compliance import WtdConfig, check_uk_wtd
from api.models.events import AssignmentRow
from api.sessions import ServerSession, get_session

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


class WtdConfigPatch(BaseModel):
    """Overrides for the default UK WTD thresholds. All fields optional —
    omit to keep the statutory default. Lets a researcher ablate one
    rule at a time (e.g. "what if we lift the 72-hr rolling cap?")."""

    model_config = ConfigDict(extra="ignore")

    max_avg_weekly_hours: float | None = None
    max_hours_per_7_days: float | None = None
    max_shift_hours: float | None = None
    min_rest_between_hours: float | None = None
    max_consecutive_long_days: int | None = None
    max_consecutive_nights: int | None = None
    long_day_threshold_hours: float | None = None
    reference_period_weeks: int | None = None


class WtdRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    assignments: list[AssignmentRow]
    config: WtdConfigPatch = Field(default_factory=WtdConfigPatch)


def _apply_patch(patch: WtdConfigPatch) -> WtdConfig:
    defaults = WtdConfig()
    fields = patch.model_dump(exclude_none=True)
    if not fields:
        return defaults
    return WtdConfig(**{**asdict(defaults), **fields})


@router.post("/uk_wtd")
def uk_wtd(
    req: WtdRequest,
    session: ServerSession = Depends(get_session),
) -> dict[str, Any]:
    """Run the UK junior-doctor 2016 + EU WTD audit against a caller-
    provided roster. Returns structured violations grouped by rule,
    with counts per severity. The roster is not solved here — the
    caller already has one (either from `/api/solve` or manual edit).
    """
    cfg = _apply_patch(req.config)
    violations = check_uk_wtd(session.state, req.assignments, config=cfg)

    by_rule: dict[str, int] = {}
    by_severity: dict[str, int] = {}
    for v in violations:
        by_rule[v.rule] = by_rule.get(v.rule, 0) + 1
        by_severity[v.severity] = by_severity.get(v.severity, 0) + 1

    errors = by_severity.get("error", 0)
    return {
        "ok": errors == 0,
        "violation_count": len(violations),
        "error_count": errors,
        "warning_count": by_severity.get("warning", 0),
        "by_rule": by_rule,
        "config": asdict(cfg),
        "violations": [
            {
                "rule": v.rule,
                "severity": v.severity,
                "doctor": v.doctor,
                "message": v.message,
                "detail": v.detail,
            }
            for v in violations
        ],
    }
