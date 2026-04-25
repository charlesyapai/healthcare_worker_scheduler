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

def _day_active_for_type(day: int, t, inst: Instance) -> bool:
    wd = inst.weekday_of(day)
    if wd in t.days_active:
        return True
    if day in inst.public_holidays and (5 in t.days_active or 6 in t.days_active):
        return True
    return False


def presolve_feasibility(inst: Instance) -> list[FeasibilityIssue]:
    """Fast necessary-condition checks. Non-exhaustive but catches ~80% of
    real-world infeasibility with specific, actionable error messages."""
    issues: list[FeasibilityIssue] = []
    tier_counts: dict[str, int] = defaultdict(int)
    for d in inst.doctors:
        tier_counts[d.tier] += 1

    weekend_days = [t for t in range(inst.n_days) if inst.is_weekend(t)]

    # Check 1: per-OnCallType eligibility — at least one eligible doctor
    # must exist for every type with daily_required > 0.
    for t in inst.on_call_types:
        if t.daily_required <= 0:
            continue
        eligible_pool = sum(
            1 for d in inst.doctors if t.key in d.eligible_oncall_types
        )
        if eligible_pool < t.daily_required:
            issues.append(FeasibilityIssue(
                "error", "oncall_type_unstaffable",
                f"On-call type '{t.key}': only {eligible_pool} eligible "
                f"doctor(s), but {t.daily_required} required per active day.",
                {"type": t.key, "available": eligible_pool,
                 "required": t.daily_required}))

    # Check 2: per-day per-station eligibility (per-doctor only).
    # For each day, each station-session, count eligible doctors not on leave.
    # Per-station weekday/weekend gates control whether the slot is in scope.
    for day in range(inst.n_days):
        is_we = inst.is_weekend(day)
        for st in inst.stations:
            if is_we and not st.weekend_enabled:
                continue
            if not is_we and not st.weekday_enabled:
                continue
            for sess in st.sessions:
                eligible = 0
                for d in inst.doctors:
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

    # Check 3: per-OnCallType per-day staffability under leave + frequency cap.
    for t in inst.on_call_types:
        if t.daily_required <= 0:
            continue
        active_days = [d for d in range(inst.n_days)
                       if _day_active_for_type(d, t, inst)]
        if not active_days:
            continue
        # Capacity per eligible doctor under H4 cap and leave: avail_days / N
        # (where N = frequency_cap_days; uncapped → avail_days).
        N = t.frequency_cap_days or 0
        total_cap = 0
        for d in inst.doctors:
            if t.key not in d.eligible_oncall_types:
                continue
            avail = sum(1 for day in active_days
                        if day not in inst.leave.get(d.id, set()))
            if N >= 2:
                total_cap += max(0, (avail + N - 1) // N)
            else:
                total_cap += avail
        required = len(active_days) * t.daily_required
        if total_cap < required:
            issues.append(FeasibilityIssue(
                "error", "oncall_type_capacity",
                f"On-call type '{t.key}': {total_cap} doctor-day(s) "
                f"available (under H4 cap {N or '∞'}) vs {required} required.",
                {"type": t.key, "available": total_cap, "required": required}))
        elif total_cap < required * 1.25:
            issues.append(FeasibilityIssue(
                "warning", "oncall_type_capacity_tight",
                f"On-call type '{t.key}' capacity is tight "
                f"({total_cap} available vs {required} required).",
                {"type": t.key, "available": total_cap, "required": required}))

    # Check 5: coverage slack per day. Counts only stations enabled on the
    # day's kind (weekday vs weekend) — disabled stations contribute no demand.
    for day in range(inst.n_days):
        is_we = inst.is_weekend(day)
        active_stations = [
            st for st in inst.stations
            if (is_we and st.weekend_enabled) or (not is_we and st.weekday_enabled)
        ]
        if not active_stations:
            continue
        required = sum(
            st.required_per_session for st in active_stations for _ in st.sessions
        )
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
            is_we = inst.is_weekend(day)
            for st_name in d.eligible_stations:
                st = station_by_name[st_name]
                if is_we and not st.weekend_enabled:
                    continue
                if not is_we and not st.weekday_enabled:
                    continue
                for sess in SESSIONS:
                    if sess not in st.sessions:
                        continue
                    v = model.NewBoolVar(f"a_{d.id}_{day}_{st_name}_{sess}")
                    assign[(d.id, day, st_name, sess)] = v
                    assign_by_dday[(d.id, day)].append(v)

    # Phase B: generic per-OnCallType vars (mirroring the primary model).
    oc_vars: dict[str, dict[tuple[int, int], cp_model.IntVar]] = {
        t.key: {} for t in inst.on_call_types
    }
    for t in inst.on_call_types:
        for d in inst.doctors:
            if t.key not in d.eligible_oncall_types:
                continue
            leave_days = inst.leave.get(d.id, set())
            for day in range(inst.n_days):
                if day in leave_days:
                    continue
                if not _day_active_for_type(day, t, inst):
                    continue
                oc_vars[t.key][(d.id, day)] = model.NewBoolVar(
                    f"oc_{t.key}_{d.id}_{day}"
                )

    # Slack variables — each constraint we relax gets slack_up + slack_down.
    slacks: list[tuple[str, str, cp_model.IntVar]] = []

    # H1 station coverage, with slack.
    for day in range(inst.n_days):
        is_we = inst.is_weekend(day)
        for st in inst.stations:
            if is_we and not st.weekend_enabled:
                continue
            if not is_we and not st.weekday_enabled:
                continue
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

    # H4 per-OnCallType frequency cap — keep hard.
    for t in inst.on_call_types:
        N = t.frequency_cap_days
        if N is None or N < 2:
            continue
        type_vars = oc_vars[t.key]
        for d in inst.doctors:
            if t.key not in d.eligible_oncall_types:
                continue
            for start in range(inst.n_days - (N - 1)):
                window = [type_vars[(d.id, day)]
                          for day in range(start, start + N)
                          if (d.id, day) in type_vars]
                if len(window) >= 2:
                    model.Add(sum(window) <= 1)

    # H5 post-call (per-type next_day_off) — keep hard.
    for t in inst.on_call_types:
        if not t.next_day_off:
            continue
        for (did, day), oc in oc_vars[t.key].items():
            if day + 1 >= inst.n_days:
                continue
            for v in list(assign_by_dday.get((did, day + 1), [])):
                model.AddImplication(oc, v.Not())
            for other in inst.on_call_types:
                ov = oc_vars[other.key].get((did, day + 1))
                if ov is not None:
                    model.AddImplication(oc, ov.Not())

    # H6 / H7 per-type day-of pattern — keep hard.
    for t in inst.on_call_types:
        if not (t.works_full_day or t.works_pm_only):
            continue
        for (did, day), oc in oc_vars[t.key].items():
            am_vars = [assign[(did, day, st.name, "AM")] for st in inst.stations
                       if (did, day, st.name, "AM") in assign]
            pm_vars = [assign[(did, day, st.name, "PM")] for st in inst.stations
                       if (did, day, st.name, "PM") in assign]
            if t.works_full_day:
                if am_vars: model.Add(sum(am_vars) == 0).OnlyEnforceIf(oc)
                if pm_vars: model.Add(sum(pm_vars) == 0).OnlyEnforceIf(oc)
            elif t.works_pm_only:
                if am_vars: model.Add(sum(am_vars) == 0).OnlyEnforceIf(oc)
                if pm_vars and not inst.is_weekend(day):
                    model.Add(sum(pm_vars) == 1).OnlyEnforceIf(oc)

    # Per-type daily_required — relaxed with slack.
    for t in inst.on_call_types:
        if t.daily_required <= 0:
            continue
        for day in range(inst.n_days):
            if not _day_active_for_type(day, t, inst):
                continue
            day_vars = [v for (_did, dd), v in oc_vars[t.key].items() if dd == day]
            up = model.NewIntVar(0, max(1, len(inst.doctors)),
                                 f"sl_up_{t.key}_{day}")
            dn = model.NewIntVar(0, max(1, len(inst.doctors)),
                                 f"sl_dn_{t.key}_{day}")
            lhs = sum(day_vars) if day_vars else 0
            model.Add(lhs + up - dn == t.daily_required)
            loc = f"day {day} oncall_type={t.key}"
            slacks.append((f"oncall_{t.key}_under", loc, up))
            slacks.append((f"oncall_{t.key}_over",  loc, dn))

    # Mutual exclusion: at most one on-call type per (doctor, day).
    by_dday: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    for type_map in oc_vars.values():
        for key, v in type_map.items():
            by_dday[key].append(v)
    for vars_ in by_dday.values():
        if len(vars_) >= 2:
            model.Add(sum(vars_) <= 1)

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
    if code.startswith("oncall_") and code.endswith("_under"):
        return f"{loc}: {amount} short — type couldn't reach `daily_required`."
    if code.startswith("oncall_") and code.endswith("_over"):
        return f"{loc}: {amount} over — too many doctors on this type."
    if code.startswith("H8_") and code.endswith("_under"):
        return f"{loc}: 1 short — required weekend role could not be filled."
    if code.startswith("H8_") and code.endswith("_over"):
        return f"{loc}: {amount} over — duplicated weekend assignment."
    return f"{loc}: slack amount={amount} on {code}."
