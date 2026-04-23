"""Pydantic models for solve-stream events and results."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="ignore")


class AssignmentRow(StrictModel):
    """One role a doctor was assigned on a specific date.

    `role` follows the v1 export convention:
      - STATION_<station>_<AM|PM>
      - ONCALL
      - WEEKEND_EXT
      - WEEKEND_CONSULT
    """
    doctor: str
    date: date
    role: str


# --------------------------------------------------------------- WS inbound

class SolveStart(StrictModel):
    action: Literal["start"]
    snapshot_assignments: bool = True


class SolveStop(StrictModel):
    action: Literal["stop"]


# --------------------------------------------------------------- WS outbound

class SolveEvent(StrictModel):
    """One improving solution found by CP-SAT."""
    type: Literal["event"] = "event"
    wall_s: float
    objective: float | None = None
    best_bound: float | None = None
    components: dict[str, int] = Field(default_factory=dict)
    assignments: list[AssignmentRow] | None = None


class SelfCheckViolation(StrictModel):
    rule: str
    severity: str
    location: str
    message: str


class SolverSelfCheck(StrictModel):
    """Automated post-solve hard-constraint audit. Every solve emits one;
    a green result is the feasibility receipt researchers and coordinators
    can trust. A non-green result means the model and the validator
    disagree — always a bug worth investigating."""
    ok: bool
    violation_count: int
    rules_passed: list[str] = Field(default_factory=list)
    rules_failed: list[str] = Field(default_factory=list)
    violations: list[SelfCheckViolation] = Field(default_factory=list)


class SolveResultPayload(StrictModel):
    status: str
    wall_time_s: float
    objective: float | None = None
    best_bound: float | None = None
    n_vars: int
    n_constraints: int
    first_feasible_s: float | None = None
    penalty_components: dict[str, int] = Field(default_factory=dict)
    assignments: list[AssignmentRow] = Field(default_factory=list)
    intermediate: list[SolveEvent] = Field(default_factory=list)
    self_check: SolverSelfCheck | None = None


class SolveDone(StrictModel):
    type: Literal["done"] = "done"
    result: SolveResultPayload


class SolveErrorMessage(StrictModel):
    type: Literal["error"] = "error"
    message: str


# --------------------------------------------------------------- Diagnostics

class FeasibilityIssueOut(StrictModel):
    severity: Literal["error", "warning", "info"]
    code: str
    message: str
    detail: dict = Field(default_factory=dict)


class ExplainViolation(StrictModel):
    code: str
    location: str
    amount: int
    message: str


class ExplainReport(StrictModel):
    status: str
    wall_time_s: float
    total_slack: int
    violations: list[ExplainViolation]
    note: str = ""


# --------------------------------------------------------------- Requests

class PrevWorkloadRequest(StrictModel):
    prev_roster_json: dict


class FillFromSnapshotRequest(StrictModel):
    """Copy assignments from a completed solve into the overrides list.

    `snapshot_id` is either "final" or the 0-based index of an intermediate
    solve event from the last solve.
    """
    snapshot_id: str = "final"


class YamlImportRequest(StrictModel):
    yaml: str


class YamlExportResponse(StrictModel):
    yaml: str
