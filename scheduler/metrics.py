"""Metrics for characterizing problems, solves, and solutions.

Three buckets:
  - problem_metrics(inst): shape of the input problem — what the solver sees.
  - solve_metrics(result, events): how hard it was to solve and how fast.
  - solution_metrics(inst, result): quality of the returned roster.

All functions return plain dicts so they compose into DataFrames and JSON.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from statistics import mean, median, pstdev
from typing import Any

from scheduler.instance import SESSIONS, Instance
from scheduler.model import HoursConfig, SolveResult, WorkloadWeights


# ----------------------------------------------------------------- Problem

def problem_metrics(inst: Instance) -> dict[str, Any]:
    """Shape-of-problem metrics, cheap to compute, no solve needed."""
    n = len(inst.doctors)
    tier_counts = defaultdict(int)
    subspec_counts = defaultdict(int)
    for d in inst.doctors:
        tier_counts[d.tier] += 1
        if d.subspec:
            subspec_counts[d.subspec] += 1

    weekend_days = sum(1 for t in range(inst.n_days) if inst.is_weekend(t))
    weekday_days = inst.n_days - weekend_days
    leave_doctor_days = sum(len(v) for v in inst.leave.values())
    leave_density = (leave_doctor_days / max(1, n * inst.n_days))

    # Eligibility density per tier: avg |eligible_stations| / |allowed_stations|.
    eligibility: dict[str, float] = {}
    for tier in ("junior", "senior", "consultant"):
        tier_docs = [d for d in inst.doctors if d.tier == tier]
        if not tier_docs:
            continue
        allowed = [s for s in inst.stations if tier in s.eligible_tiers]
        if not allowed:
            continue
        denom = len(allowed)
        vals = [len([s for s in d.eligible_stations
                     if s in {st.name for st in allowed}]) / denom
                for d in tier_docs]
        eligibility[tier] = round(mean(vals), 3)

    # Coverage-slack ratio per weekday: available / required.
    # Available = doctor-sessions on a given day (AM + PM = 2 per available doctor).
    # Required = sum over stations active in that session × required_per_session.
    slack_by_day: dict[int, float] = {}
    for day in range(inst.n_days):
        if inst.is_weekend(day) and not inst.weekend_am_pm_enabled:
            continue
        req = 0
        for st in inst.stations:
            for sess in st.sessions:
                req += st.required_per_session
        available = 0
        for d in inst.doctors:
            if day in inst.leave.get(d.id, set()):
                continue
            # Up to 2 sessions per doctor (AM + PM), minus roles that claim
            # the day — but at the problem-metrics stage we don't know those.
            available += 2
        slack_by_day[day] = round(available / max(1, req), 3)

    slack_min = round(min(slack_by_day.values()), 3) if slack_by_day else None

    # Required weekend roles:
    # per weekend day: 1 junior_ext + 1 senior_ext + 1 junior_oc + 1 senior_oc
    # + 1 consultant per subspec.
    wknd_oncall_required_per_tier = weekend_days  # 1/day for junior and senior each
    wknd_ext_required_per_tier = weekend_days
    wknd_consult_required_per_subspec = weekend_days

    # Oncall capacity under 1-in-3 cap, ignoring leave:
    oncall_cap_per_doc_max = (inst.n_days + 2) // 3   # ceil(n_days/3)
    oncall_required_junior = inst.n_days              # 1/night over horizon
    oncall_required_senior = inst.n_days
    # Available capacity summed across juniors / seniors.
    avail_oncall_junior = tier_counts["junior"] * oncall_cap_per_doc_max
    avail_oncall_senior = tier_counts["senior"] * oncall_cap_per_doc_max

    return {
        "n_doctors": n,
        "n_days": inst.n_days,
        "tier_counts": dict(tier_counts),
        "subspec_counts": dict(subspec_counts),
        "n_stations": len(inst.stations),
        "weekend_days": weekend_days,
        "weekday_days": weekday_days,
        "public_holidays": sorted(inst.public_holidays),
        "leave_doctor_days": leave_doctor_days,
        "leave_density": round(leave_density, 4),
        "eligibility_density": eligibility,
        "coverage_slack_min": slack_min,
        "coverage_slack_by_day": slack_by_day,
        "oncall_capacity": {
            "junior_available": avail_oncall_junior,
            "junior_required":  oncall_required_junior,
            "senior_available": avail_oncall_senior,
            "senior_required":  oncall_required_senior,
        },
        "weekend_roles_per_subspec_required": wknd_consult_required_per_subspec,
    }


# ------------------------------------------------------------------- Solve

def solve_metrics(result: SolveResult, events: list[dict]) -> dict[str, Any]:
    """Metrics about how the solver behaved."""
    n_events = len(events)
    gap = None
    if (result.objective is not None and result.best_bound is not None
            and result.objective > 0):
        gap = round((result.objective - result.best_bound) / max(1.0, result.objective), 4)

    # Convergence timeline (obj, bound, wall_s) — straight from events.
    timeline = [
        {
            "wall_s": round(e["wall_s"], 3),
            "objective": e["objective"],
            "best_bound": e["best_bound"],
        }
        for e in events
    ]

    return {
        "status": result.status,
        "wall_time_s": round(result.wall_time_s, 3),
        "first_feasible_s": (round(result.first_feasible_s, 3)
                             if result.first_feasible_s is not None else None),
        "objective": result.objective,
        "best_bound": result.best_bound,
        "optimality_gap": gap,
        "n_vars": result.n_vars,
        "n_constraints": result.n_constraints,
        "n_intermediate_solutions": n_events,
        "convergence_timeline": timeline,
        "penalty_components": dict(result.penalty_components),
    }


# ----------------------------------------------------------------- Solution

def solution_metrics(inst: Instance, result: SolveResult) -> dict[str, Any]:
    """Quality metrics on the returned roster. Empty dict if no solution."""
    if result.status not in ("OPTIMAL", "FEASIBLE"):
        return {}

    st_assigns = result.assignments["stations"]
    oncall = result.assignments["oncall"]
    ext = result.assignments["ext"]
    wconsult = result.assignments["wconsult"]
    doc_by_id = {d.id: d for d in inst.doctors}

    per_doc = {
        d.id: {"tier": d.tier, "subspec": d.subspec,
               "am_pm": 0, "oncall": 0, "weekend_ext": 0, "weekend_consult": 0,
               "oncall_days": []}
        for d in inst.doctors
    }
    for (did, day, _, _) in st_assigns:
        per_doc[did]["am_pm"] += 1
    for (did, day) in oncall:
        per_doc[did]["oncall"] += 1
        per_doc[did]["oncall_days"].append(day)
    for (did, day) in ext:
        per_doc[did]["weekend_ext"] += 1
    for (did, day) in wconsult:
        per_doc[did]["weekend_consult"] += 1

    # Balance gaps per tier.
    tier_balance: dict[str, dict[str, int]] = {}
    for tier in ("junior", "senior", "consultant"):
        tier_docs = [v for v in per_doc.values() if v["tier"] == tier]
        if not tier_docs:
            continue
        am_pms = [d["am_pm"] for d in tier_docs]
        oncalls = [d["oncall"] for d in tier_docs]
        wknds = [d["weekend_ext"] + d["weekend_consult"] for d in tier_docs]
        tier_balance[tier] = {
            "sessions_gap": max(am_pms) - min(am_pms) if am_pms else 0,
            "oncall_gap": max(oncalls) - min(oncalls) if oncalls else 0,
            "weekend_gap": max(wknds) - min(wknds) if wknds else 0,
            "sessions_mean": round(mean(am_pms), 2) if am_pms else 0,
        }

    # Oncall spacing stats (min / mean gap between consecutive on-calls per doctor).
    spacings: list[int] = []
    tight_spacings = 0
    for v in per_doc.values():
        days = sorted(v["oncall_days"])
        for i in range(1, len(days)):
            d = days[i] - days[i - 1]
            spacings.append(d)
            if d < 3:
                tight_spacings += 1  # shouldn't happen if H4 held

    # Reporting-station consecutive violations (S4 counter).
    rep_pairs = 0
    rep_assigns: set[tuple[int, int, str, str]] = set(st_assigns.keys())
    reporting_stations = {s.name for s in inst.stations if s.is_reporting}
    for (did, day, sname, sess) in rep_assigns:
        if sname not in reporting_stations:
            continue
        if (did, day + 1, sname, sess) in rep_assigns:
            rep_pairs += 1

    # Coverage verification (H1). Should be all-green.
    coverage_violations: list[str] = []
    from collections import Counter
    cov: Counter = Counter()
    for (did, day, sname, sess) in st_assigns:
        cov[(day, sname, sess)] += 1
    for day in range(inst.n_days):
        if inst.is_weekend(day) and not inst.weekend_am_pm_enabled:
            continue
        for st in inst.stations:
            for sess in st.sessions:
                got = cov.get((day, st.name, sess), 0)
                if got != st.required_per_session:
                    coverage_violations.append(f"day {day} {st.name}/{sess}: {got}/{st.required_per_session}")

    return {
        "tier_balance": tier_balance,
        "oncall_spacing": {
            "count": len(spacings),
            "min": min(spacings) if spacings else None,
            "mean": round(mean(spacings), 2) if spacings else None,
            "median": median(spacings) if spacings else None,
            "stdev": round(pstdev(spacings), 2) if len(spacings) > 1 else 0,
            "tight_below_3": tight_spacings,
        },
        "reporting_spread_pairs": rep_pairs,
        "coverage_violations": coverage_violations,
        "per_doctor": {did: {k: v for k, v in info.items() if k != "oncall_days"}
                       for did, info in per_doc.items()},
    }


# --------------------------------------------------- Weighted workload scoring

def workload_breakdown(
    inst: Instance,
    assignments: dict,
    workload_weights: WorkloadWeights | None = None,
) -> dict[int, dict[str, int]]:
    """Per-doctor weighted workload breakdown from an assignment snapshot.

    Returns `{doctor_id: {weekday_sessions, weekend_sessions, weekday_oncall,
    weekend_oncall, ext, wconsult, leave_days, prev_workload, score}}` where
    `score = weekday_sessions*w_wd + weekend_sessions*w_we + ... + prev_workload`.
    Mirrors the solver's S0 term so the UI table reflects what the solver
    balanced on.
    """
    w = workload_weights or WorkloadWeights()
    out: dict[int, dict[str, int]] = {}
    for d in inst.doctors:
        out[d.id] = {
            "weekday_sessions": 0,
            "weekend_sessions": 0,
            "weekday_oncall": 0,
            "weekend_oncall": 0,
            "ext": 0,
            "wconsult": 0,
            "leave_days": len(inst.leave.get(d.id, set())),
            "prev_workload": int(inst.prev_workload.get(d.id, 0)),
        }

    for (did, day, _st, _sess), v in assignments.get("stations", {}).items():
        if not v:
            continue
        key = "weekend_sessions" if inst.is_weekend(day) else "weekday_sessions"
        out[did][key] += 1
    for (did, day), v in assignments.get("oncall", {}).items():
        if not v:
            continue
        key = "weekend_oncall" if inst.is_weekend(day) else "weekday_oncall"
        out[did][key] += 1
    for (did, _), v in assignments.get("ext", {}).items():
        if v:
            out[did]["ext"] += 1
    for (did, _), v in assignments.get("wconsult", {}).items():
        if v:
            out[did]["wconsult"] += 1

    for did, row in out.items():
        score = (
            row["weekday_sessions"] * w.weekday_session
            + row["weekend_sessions"] * w.weekend_session
            + row["weekday_oncall"] * w.weekday_oncall
            + row["weekend_oncall"] * w.weekend_oncall
            + row["ext"] * w.weekend_ext
            + row["wconsult"] * w.weekend_consult
            + row["prev_workload"]
        )
        row["score"] = int(score)
    return out


def count_idle_weekdays(inst: Instance, assignments: dict) -> dict[int, int]:
    """Per-doctor count of weekdays where the doctor had no station/oncall/ext/wc
    role and was not on leave. Mirrors H11's idle definition (leave-excused only;
    post-call / senior-oncall / lieu days still show up as idle here so the UI
    flags them — the caller can net them out if desired)."""
    out: dict[int, int] = {d.id: 0 for d in inst.doctors}
    # Build per-(doc, day) "busy" flag.
    busy: dict[tuple[int, int], bool] = {}
    for (did, day, _st, _sess), v in assignments.get("stations", {}).items():
        if v:
            busy[(did, day)] = True
    for key, v in assignments.get("oncall", {}).items():
        if v:
            busy[key] = True
    for key, v in assignments.get("ext", {}).items():
        if v:
            busy[key] = True
    for key, v in assignments.get("wconsult", {}).items():
        if v:
            busy[key] = True

    for d in inst.doctors:
        leave_days = inst.leave.get(d.id, set())
        for day in range(inst.n_days):
            if inst.is_weekend(day):
                continue
            if day in leave_days:
                continue
            if not busy.get((d.id, day), False):
                out[d.id] += 1
    return out


def hours_per_doctor(
    inst: Instance,
    assignments: dict,
    hours: HoursConfig | None = None,
) -> dict[int, dict[str, float]]:
    """Per-doctor hours total + average per week across the horizon.

    Returns `{doctor_id: {total_hours, hours_per_week}}`. `hours_per_week` is
    total / (n_days / 7) so a 21-day horizon averages across 3 weeks. Default
    shift lengths come from `HoursConfig` (AM=4h, PM=4h, weekday on-call=12h,
    weekend on-call=16h, EXT=12h, weekend-consult=8h).
    """
    h = hours or HoursConfig()
    out: dict[int, dict[str, float]] = {d.id: {"total_hours": 0.0} for d in inst.doctors}

    for (did, day, _st, sess), v in assignments.get("stations", {}).items():
        if not v:
            continue
        if inst.is_weekend(day):
            hrs = h.weekend_am if sess == "AM" else h.weekend_pm
        else:
            hrs = h.weekday_am if sess == "AM" else h.weekday_pm
        out[did]["total_hours"] += hrs

    for (did, day), v in assignments.get("oncall", {}).items():
        if not v:
            continue
        out[did]["total_hours"] += h.weekend_oncall if inst.is_weekend(day) else h.weekday_oncall

    for (did, _), v in assignments.get("ext", {}).items():
        if v:
            out[did]["total_hours"] += h.weekend_ext
    for (did, _), v in assignments.get("wconsult", {}).items():
        if v:
            out[did]["total_hours"] += h.weekend_consult

    n_weeks = max(1.0, inst.n_days / 7.0)
    for did, row in out.items():
        row["hours_per_week"] = round(row["total_hours"] / n_weeks, 1)
        row["total_hours"] = round(row["total_hours"], 1)
    return out
