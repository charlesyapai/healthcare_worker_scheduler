"""Feasibility diagnostics: pre-solve sniff (L1) and soft-relax explainer (L3).

Two public entry points:
  - presolve_feasibility(inst)  -> list[FeasibilityIssue]
        Cheap necessary-condition checks. Runs in milliseconds.
  - explain_infeasibility(inst) -> InfeasibilityReport
        Rebuilds the CP-SAT model with slack variables on every "hard" coverage
        constraint, minimizes sum of slacks, and reports which ones were
        forced nonzero. Use only when the primary solve returns INFEASIBLE
        (or UNKNOWN after the full time budget).
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from scheduler.instance import SESSIONS, Instance


@dataclass
class FeasibilityIssue:
    severity: str          # "error" | "warning" | "info"
    code: str
    message: str
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"severity": self.severity, "code": self.code,
                "message": self.message, "detail": self.detail}


@dataclass
class InfeasibilityViolation:
    code: str
    location: str          # human-readable "day 14, station CT, AM"
    amount: int            # slack magnitude — typically 1 or more
    message: str


@dataclass
class InfeasibilityReport:
    status: str            # "RELAXED_FEASIBLE" | "RELAXED_INFEASIBLE" | "RELAXED_UNKNOWN"
    wall_time_s: float
    total_slack: int
    violations: list[InfeasibilityViolation]
    note: str = ""


# --------------------------------------------------------------- L1: pre-solve

def presolve_feasibility(inst: Instance) -> list[FeasibilityIssue]:
    """Fast necessary-condition checks. Non-exhaustive but catches ~80% of
    real-world infeasibility with specific, actionable error messages."""
    issues: list[FeasibilityIssue] = []
    tier_counts: dict[str, int] = defaultdict(int)
    subspec_counts: dict[str, int] = defaultdict(int)
    for d in inst.doctors:
        tier_counts[d.tier] += 1
        if d.subspec:
            subspec_counts[d.subspec] += 1

    weekend_days = [t for t in range(inst.n_days) if inst.is_weekend(t)]

    # Check 1: minimum tier counts.
    if weekend_days:
        if tier_counts["junior"] < 1:
            issues.append(FeasibilityIssue(
                "error", "no_juniors",
                "Weekend days require junior on-call and junior extended duty, "
                "but there are no junior doctors in the instance.",
                {"weekend_days": weekend_days}))
        if tier_counts["senior"] < 1:
            issues.append(FeasibilityIssue(
                "error", "no_seniors",
                "Weekend days require senior on-call and senior extended duty, "
                "but there are no senior doctors."))
        for ss in inst.subspecs:
            if subspec_counts.get(ss, 0) < 1:
                issues.append(FeasibilityIssue(
                    "error", "no_subspec",
                    f"Weekend coverage needs a consultant of subspec {ss}, "
                    f"but none are present.",
                    {"subspec": ss}))

    # Check 2: per-day per-station eligibility.
    # For each weekday, each station-session, count eligible doctors not on leave.
    for day in range(inst.n_days):
        if inst.is_weekend(day) and not inst.weekend_am_pm_enabled:
            continue
        for st in inst.stations:
            for sess in st.sessions:
                eligible = 0
                for d in inst.doctors:
                    if d.tier not in st.eligible_tiers:
                        continue
                    if st.name not in d.eligible_stations:
                        continue
                    if day in inst.leave.get(d.id, set()):
                        continue
                    eligible += 1
                if eligible < st.required_per_session:
                    issues.append(FeasibilityIssue(
                        "error", "station_coverage",
                        f"Day {day}, {st.name}/{sess}: need "
                        f"{st.required_per_session} eligible doctor(s) but only "
                        f"{eligible} are available (after leave / eligibility).",
                        {"day": day, "station": st.name, "session": sess,
                         "required": st.required_per_session, "available": eligible}))

    # Check 3: subspec coverage on each weekend day.
    for day in weekend_days:
        for ss in inst.subspecs:
            available = sum(1 for d in inst.doctors
                            if d.tier == "consultant" and d.subspec == ss
                            and day not in inst.leave.get(d.id, set()))
            if available < 1:
                issues.append(FeasibilityIssue(
                    "error", "subspec_weekend",
                    f"Day {day} (weekend): no available consultant with "
                    f"subspec {ss} (all on leave).",
                    {"day": day, "subspec": ss}))

    # Check 4: on-call capacity under 1-in-3 cap.
    # Per doctor max oncall-days ~= ceil(avail_days / 3) where avail_days =
    # n_days minus leave days for that doctor.
    for tier in ("junior", "senior"):
        total_cap = 0
        for d in inst.doctors:
            if d.tier != tier:
                continue
            avail = inst.n_days - len(inst.leave.get(d.id, set()))
            total_cap += max(0, (avail + 2) // 3)
        required = inst.n_days  # 1 oncall per night
        if total_cap < required:
            issues.append(FeasibilityIssue(
                "error", "oncall_capacity",
                f"{tier.capitalize()} on-call capacity: {total_cap} doctor-days "
                f"available (under 1-in-3 cap) vs {required} required over "
                f"{inst.n_days}-day horizon.",
                {"tier": tier, "available": total_cap, "required": required}))
        elif total_cap < required * 1.25:
            issues.append(FeasibilityIssue(
                "warning", "oncall_capacity_tight",
                f"{tier.capitalize()} on-call capacity is tight "
                f"({total_cap} available vs {required} required). "
                f"Leave or eligibility changes could push this infeasible.",
                {"tier": tier, "available": total_cap, "required": required}))

    # Check 5: coverage slack per day.
    for day in range(inst.n_days):
        if inst.is_weekend(day) and not inst.weekend_am_pm_enabled:
            continue
        required = sum(st.required_per_session for st in inst.stations for _ in st.sessions)
        available = sum(2 for d in inst.doctors
                        if day not in inst.leave.get(d.id, set()))
        if available < required:
            issues.append(FeasibilityIssue(
                "error", "insufficient_manpower",
                f"Day {day}: total required sessions {required} exceeds "
                f"available doctor-sessions {available}.",
                {"day": day, "required": required, "available": available}))

    return issues


# --------------------------------------------------------------- L3: soft-relax

def explain_infeasibility(inst: Instance, *, time_limit_s: float = 30.0,
                          num_workers: int = 8) -> InfeasibilityReport:
    """Rebuild the model with slacks on coverage constraints and minimize total slack.

    The slacks go on H1 (station coverage) and H8 (weekend coverage) because
    those are where infeasibility tends to originate. Other constraints are
    left as hard — they're either structural (H3, H10 via variable creation)
    or hardly ever the sole cause of infeasibility (H2, H4, H5, H6, H7, H9).

    Returns a report with:
      - total_slack: sum of all constraint violations (0 ⇒ original model
        should have been feasible; caller should investigate).
      - violations: list of specific constraints that had to be broken.
    """
    t0 = time.perf_counter()
    model = cp_model.CpModel()

    # Reuse the same variables as the primary model (same code pattern).
    assign: dict[tuple[int, int, str, str], cp_model.IntVar] = {}
    assign_by_dday: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    station_by_name = {s.name: s for s in inst.stations}
    for d in inst.doctors:
        leave_days = inst.leave.get(d.id, set())
        for day in range(inst.n_days):
            if day in leave_days:
                continue
            if inst.is_weekend(day) and not inst.weekend_am_pm_enabled:
                continue
            for st_name in d.eligible_stations:
                st = station_by_name[st_name]
                if d.tier not in st.eligible_tiers:
                    continue
                for sess in SESSIONS:
                    if sess not in st.sessions:
                        continue
                    v = model.NewBoolVar(f"a_{d.id}_{day}_{st_name}_{sess}")
                    assign[(d.id, day, st_name, sess)] = v
                    assign_by_dday[(d.id, day)].append(v)

    oncall: dict[tuple[int, int], cp_model.IntVar] = {}
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        leave_days = inst.leave.get(d.id, set())
        for day in range(inst.n_days):
            if day in leave_days:
                continue
            oncall[(d.id, day)] = model.NewBoolVar(f"oc_{d.id}_{day}")

    ext: dict[tuple[int, int], cp_model.IntVar] = {}
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        leave_days = inst.leave.get(d.id, set())
        for day in range(inst.n_days):
            if not inst.is_weekend(day) or day in leave_days:
                continue
            ext[(d.id, day)] = model.NewBoolVar(f"ext_{d.id}_{day}")

    wconsult: dict[tuple[int, int], cp_model.IntVar] = {}
    for d in inst.doctors:
        if d.tier != "consultant":
            continue
        leave_days = inst.leave.get(d.id, set())
        for day in range(inst.n_days):
            if not inst.is_weekend(day) or day in leave_days:
                continue
            wconsult[(d.id, day)] = model.NewBoolVar(f"wc_{d.id}_{day}")

    # Slack variables — each constraint we relax gets slack_up + slack_down.
    slacks: list[tuple[str, str, cp_model.IntVar]] = []

    # H1 station coverage, with slack.
    for day in range(inst.n_days):
        if inst.is_weekend(day) and not inst.weekend_am_pm_enabled:
            continue
        for st in inst.stations:
            for sess in st.sessions:
                vars_for = [
                    assign[(d.id, day, st.name, sess)]
                    for d in inst.doctors
                    if (d.id, day, st.name, sess) in assign
                ]
                up = model.NewIntVar(0, st.required_per_session + len(inst.doctors),
                                     f"sl_up_H1_{day}_{st.name}_{sess}")
                dn = model.NewIntVar(0, st.required_per_session + len(inst.doctors),
                                     f"sl_dn_H1_{day}_{st.name}_{sess}")
                lhs = sum(vars_for) if vars_for else 0
                model.Add(lhs + up - dn == st.required_per_session)
                loc = f"day {day} {st.name}/{sess}"
                # lhs + up - dn == req  ⇒  up compensates under-coverage, dn over.
                slacks.append(("H1_coverage_under", loc, up))
                slacks.append(("H1_coverage_over",  loc, dn))

    # H2 one-slot-per-session — keep hard.
    for d in inst.doctors:
        for day in range(inst.n_days):
            for sess in SESSIONS:
                vars_for = [
                    assign[(d.id, day, st.name, sess)]
                    for st in inst.stations
                    if (d.id, day, st.name, sess) in assign
                ]
                if vars_for:
                    model.Add(sum(vars_for) <= 1)

    # H4 oncall 1-in-3 — keep hard (relaxing creates noise).
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        for start in range(inst.n_days - 2):
            window = [oncall[(d.id, day)]
                      for day in range(start, start + 3)
                      if (d.id, day) in oncall]
            if len(window) >= 2:
                model.Add(sum(window) <= 1)

    # H5 post-call off — keep hard.
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        for day in range(inst.n_days - 1):
            if (d.id, day) not in oncall:
                continue
            oc = oncall[(d.id, day)]
            for v in list(assign_by_dday.get((d.id, day + 1), [])):
                model.AddImplication(oc, v.Not())
            if (d.id, day + 1) in oncall:
                model.AddImplication(oc, oncall[(d.id, day + 1)].Not())
            if (d.id, day + 1) in ext:
                model.AddImplication(oc, ext[(d.id, day + 1)].Not())
            if (d.id, day + 1) in wconsult:
                model.AddImplication(oc, wconsult[(d.id, day + 1)].Not())

    # H6 / H7 oncall-day AM/PM pattern — keep hard.
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        for day in range(inst.n_days):
            if (d.id, day) not in oncall:
                continue
            oc = oncall[(d.id, day)]
            am_vars = [assign[(d.id, day, st.name, "AM")] for st in inst.stations
                       if (d.id, day, st.name, "AM") in assign]
            pm_vars = [assign[(d.id, day, st.name, "PM")] for st in inst.stations
                       if (d.id, day, st.name, "PM") in assign]
            if d.tier == "senior":
                if am_vars: model.Add(sum(am_vars) == 0).OnlyEnforceIf(oc)
                if pm_vars: model.Add(sum(pm_vars) == 0).OnlyEnforceIf(oc)
            else:
                if am_vars: model.Add(sum(am_vars) == 0).OnlyEnforceIf(oc)
                if pm_vars and not inst.is_weekend(day):
                    model.Add(sum(pm_vars) == 1).OnlyEnforceIf(oc)

    # H8 weekend coverage — relaxed with slack.
    for day in range(inst.n_days):
        if not inst.is_weekend(day):
            continue
        for label, tier, var_map in (
            ("H8_jr_ext",    "junior",    ext),
            ("H8_sr_ext",    "senior",    ext),
            ("H8_jr_oncall", "junior",    oncall),
            ("H8_sr_oncall", "senior",    oncall),
        ):
            vars_for = [var_map[(d.id, day)] for d in inst.doctors
                        if d.tier == tier and (d.id, day) in var_map]
            up = model.NewIntVar(0, 10, f"sl_up_{label}_{day}")
            dn = model.NewIntVar(0, 10, f"sl_dn_{label}_{day}")
            lhs = sum(vars_for) if vars_for else 0
            model.Add(lhs + up - dn == 1)
            loc = f"day {day} {label}"
            slacks.append((f"{label}_under", loc, up))
            slacks.append((f"{label}_over",  loc, dn))
        for ss in inst.subspecs:
            vars_for = [wconsult[(d.id, day)] for d in inst.doctors
                        if d.tier == "consultant" and d.subspec == ss
                        and (d.id, day) in wconsult]
            up = model.NewIntVar(0, 10, f"sl_up_H8_wc_{day}_{ss}")
            dn = model.NewIntVar(0, 10, f"sl_dn_H8_wc_{day}_{ss}")
            lhs = sum(vars_for) if vars_for else 0
            model.Add(lhs + up - dn == 1)
            loc = f"day {day} subspec {ss} consultant"
            slacks.append((f"H8_wconsult_under", loc, up))
            slacks.append((f"H8_wconsult_over",  loc, dn))

        # one-role-per-doctor cap on weekend days.
        for d in inst.doctors:
            if d.tier == "consultant":
                continue
            roles = []
            if (d.id, day) in ext: roles.append(ext[(d.id, day)])
            if (d.id, day) in oncall: roles.append(oncall[(d.id, day)])
            if len(roles) >= 2:
                model.Add(sum(roles) <= 1)

    # Objective: minimize total slack.
    model.Minimize(sum(v for _, _, v in slacks))

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = num_workers

    status_int = solver.Solve(model)
    wall = time.perf_counter() - t0
    status_name = {
        cp_model.OPTIMAL: "RELAXED_FEASIBLE",
        cp_model.FEASIBLE: "RELAXED_FEASIBLE",
        cp_model.INFEASIBLE: "RELAXED_INFEASIBLE",
        cp_model.UNKNOWN: "RELAXED_UNKNOWN",
        cp_model.MODEL_INVALID: "RELAXED_MODEL_INVALID",
    }.get(status_int, "RELAXED_UNKNOWN")

    violations: list[InfeasibilityViolation] = []
    total_slack = 0
    if status_name == "RELAXED_FEASIBLE":
        for code, loc, var in slacks:
            val = int(solver.Value(var))
            if val > 0:
                total_slack += val
                violations.append(InfeasibilityViolation(
                    code=code, location=loc, amount=val,
                    message=_explain(code, loc, val)))

    note = ""
    if status_name == "RELAXED_FEASIBLE" and total_slack == 0:
        note = ("The relaxed model found a solution with zero slack — the original "
                "model should also be feasible. Consider raising the primary "
                "solve's time limit.")
    elif status_name != "RELAXED_FEASIBLE":
        note = (f"Relaxed model returned {status_name}. Try a longer time limit, "
                f"or check the pre-solve sniff for structural issues.")

    return InfeasibilityReport(
        status=status_name,
        wall_time_s=wall,
        total_slack=total_slack,
        violations=violations,
        note=note,
    )


def _explain(code: str, loc: str, amount: int) -> str:
    if code == "H1_coverage_under":
        return f"{loc}: {amount} short — needed {amount} more eligible doctor(s)."
    if code == "H1_coverage_over":
        return f"{loc}: {amount} over — unable to reduce headcount below requirement."
    if code.startswith("H8_") and code.endswith("_under"):
        return f"{loc}: 1 short — required weekend role could not be filled."
    if code.startswith("H8_") and code.endswith("_over"):
        return f"{loc}: {amount} over — duplicated weekend assignment."
    return f"{loc}: slack amount={amount} on {code}."
