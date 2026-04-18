"""CP-SAT model for the rostering problem.

See `docs/CONSTRAINTS.md` for the authoritative spec. Every constraint block
below is tagged with the H#/S# label from that doc.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

from ortools.sat.python import cp_model

from scheduler.instance import SESSIONS, SUBSPECS, Instance


@dataclass
class SolveResult:
    status: str                  # "OPTIMAL" / "FEASIBLE" / "INFEASIBLE" / "UNKNOWN" / "MODEL_INVALID"
    wall_time_s: float
    objective: float | None
    best_bound: float | None
    n_vars: int
    n_constraints: int
    assignments: dict[str, Any] = field(default_factory=dict)
    # assignments["stations"] = {(d, day, station, sess): 1, ...}
    # assignments["oncall"]   = {(d, day): 1, ...}
    # assignments["ext"]      = {(d, day): 1, ...}
    # assignments["wconsult"] = {(d, day): 1, ...}


@dataclass
class Weights:
    balance_sessions: int = 10
    balance_oncall: int = 20
    balance_weekend: int = 20
    reporting_spread: int = 5


def solve(
    inst: Instance,
    *,
    time_limit_s: float = 300.0,
    weights: Weights | None = None,
    num_workers: int = 8,
    log_search_progress: bool = False,
    feasibility_only: bool = False,
) -> SolveResult:
    """Build and solve the CP-SAT model for `inst`."""
    weights = weights or Weights()
    model = cp_model.CpModel()
    doc_by_id = {d.id: d for d in inst.doctors}

    # ------------------------------------------------------------------ Vars
    # assign[d, day, station, sess] — H1, H2, H3.
    assign: dict[tuple[int, int, str, str], cp_model.IntVar] = {}
    # Index assign by (doctor, day) so post-call / lieu loops stay O(1) per hit.
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

    # oncall[d, day] — juniors + seniors only.
    oncall: dict[tuple[int, int], cp_model.IntVar] = {}
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        leave_days = inst.leave.get(d.id, set())
        for day in range(inst.n_days):
            if day in leave_days:
                continue
            oncall[(d.id, day)] = model.NewBoolVar(f"oc_{d.id}_{day}")

    # ext[d, day] — juniors + seniors, weekend days only.
    ext: dict[tuple[int, int], cp_model.IntVar] = {}
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        leave_days = inst.leave.get(d.id, set())
        for day in range(inst.n_days):
            if not inst.is_weekend(day):
                continue
            if day in leave_days:
                continue
            ext[(d.id, day)] = model.NewBoolVar(f"ext_{d.id}_{day}")

    # wconsult[d, day] — consultants on weekends, one per subspec.
    wconsult: dict[tuple[int, int], cp_model.IntVar] = {}
    for d in inst.doctors:
        if d.tier != "consultant":
            continue
        leave_days = inst.leave.get(d.id, set())
        for day in range(inst.n_days):
            if not inst.is_weekend(day):
                continue
            if day in leave_days:
                continue
            wconsult[(d.id, day)] = model.NewBoolVar(f"wc_{d.id}_{day}")

    # lieu_choice[d, w, side] — per weekend-ext assignment, two bools (fri / mon).
    # Only created where the candidate weekday is inside the horizon and not
    # already a leave day. H9 links these to ext and forces the ext-day lieu off.
    lieu_choice: dict[tuple[int, int, str], cp_model.IntVar] = {}
    # lieu_uses[d, weekday_day] = list of lieu_choice vars that, when true,
    # force that weekday off for that doctor.
    lieu_uses: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        leave_days = inst.leave.get(d.id, set())
        for w in range(inst.n_days):
            if not inst.is_weekend(w):
                continue
            if (d.id, w) not in ext:
                continue
            for side, weekday_target in (("FRI", 4), ("MON", 0)):
                delta = range(1, 8)
                target_day = None
                for dx in delta:
                    t = w - dx if side == "FRI" else w + dx
                    if t < 0 or t >= inst.n_days:
                        break
                    if inst.weekday_of(t) == weekday_target:
                        target_day = t
                        break
                if target_day is None or target_day in leave_days:
                    continue
                lv = model.NewBoolVar(f"lieu_{d.id}_{w}_{side}")
                lieu_choice[(d.id, w, side)] = lv
                lieu_uses[(d.id, target_day)].append(lv)

    # ------------------------------------------------------------ Hard constraints

    # H1 — Station coverage.
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
                if not vars_for:
                    model.Add(1 == 0)
                else:
                    model.Add(sum(vars_for) == st.required_per_session)

    # H2 — One station per session.
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

    # H4 — On-call cap (1-in-3 rolling window).
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        for start in range(inst.n_days - 2):
            window = [
                oncall[(d.id, day)]
                for day in range(start, start + 3)
                if (d.id, day) in oncall
            ]
            if len(window) >= 2:
                model.Add(sum(window) <= 1)

    # prev_oncall seed (H4 continuity): if doctor was on-call on day -1,
    # days 0 and 1 can't have on-call (3-day window includes day -1).
    for did in inst.prev_oncall:
        for day in (0, 1):
            if (did, day) in oncall:
                model.Add(oncall[(did, day)] == 0)

    # H5 — Post-call off: oncall[d, t] == 1 ⇒ no activity on t+1.
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        for day in range(inst.n_days - 1):
            if (d.id, day) not in oncall:
                continue
            oc = oncall[(d.id, day)]
            for v in _activities_on(d.id, day + 1, assign_by_dday, oncall, ext, wconsult):
                model.AddImplication(oc, v.Not())

    # Seed continuity: day 0 is post-call if doctor was on-call on day -1.
    for did in inst.prev_oncall:
        for v in _activities_on(did, 0, assign_by_dday, oncall, ext, wconsult):
            model.Add(v == 0)

    # H6 (senior) / H7 (junior) — on-call day activity pattern.
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        for day in range(inst.n_days):
            if (d.id, day) not in oncall:
                continue
            oc = oncall[(d.id, day)]
            am_vars = [
                assign[(d.id, day, st.name, "AM")]
                for st in inst.stations
                if (d.id, day, st.name, "AM") in assign
            ]
            pm_vars = [
                assign[(d.id, day, st.name, "PM")]
                for st in inst.stations
                if (d.id, day, st.name, "PM") in assign
            ]
            if d.tier == "senior":
                if am_vars:
                    model.Add(sum(am_vars) == 0).OnlyEnforceIf(oc)
                if pm_vars:
                    model.Add(sum(pm_vars) == 0).OnlyEnforceIf(oc)
            else:  # junior
                if am_vars:
                    model.Add(sum(am_vars) == 0).OnlyEnforceIf(oc)
                # PM == 1 on weekdays (on weekends PM vars don't exist by default).
                if pm_vars and not inst.is_weekend(day):
                    model.Add(sum(pm_vars) == 1).OnlyEnforceIf(oc)

    # H8 — Weekend coverage.
    for day in range(inst.n_days):
        if not inst.is_weekend(day):
            continue
        juniors = [d for d in inst.doctors if d.tier == "junior"]
        seniors = [d for d in inst.doctors if d.tier == "senior"]
        ext_j_vars = [ext[(d.id, day)] for d in juniors if (d.id, day) in ext]
        ext_s_vars = [ext[(d.id, day)] for d in seniors if (d.id, day) in ext]
        oc_j_vars = [oncall[(d.id, day)] for d in juniors if (d.id, day) in oncall]
        oc_s_vars = [oncall[(d.id, day)] for d in seniors if (d.id, day) in oncall]
        _exact_one(model, ext_j_vars)
        _exact_one(model, ext_s_vars)
        _exact_one(model, oc_j_vars)
        _exact_one(model, oc_s_vars)
        for ss in SUBSPECS:
            wc_vars = [
                wconsult[(d.id, day)]
                for d in inst.doctors
                if d.tier == "consultant" and d.subspec == ss and (d.id, day) in wconsult
            ]
            _exact_one(model, wc_vars)
        # One weekend role at most per junior/senior doctor on a weekend day.
        for d in juniors + seniors:
            roles = []
            if (d.id, day) in ext:
                roles.append(ext[(d.id, day)])
            if (d.id, day) in oncall:
                roles.append(oncall[(d.id, day)])
            if len(roles) >= 2:
                model.Add(sum(roles) <= 1)

    # H9 — Day in lieu for weekend extended.
    # lieu_choice[d, w, side] ⇒ ext[d, w] == 1 (reverse direction).
    # ext[d, w] == 1 and at least one candidate side exists ⇒ sum of choices == 1.
    # No lieu without a matching ext (i.e. lieu_choice[d, w, side] ≤ ext[d, w]).
    ext_to_choices: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    for (did, w, side), lv in lieu_choice.items():
        ext_to_choices[(did, w)].append(lv)
        model.Add(lv <= ext[(did, w)])
    for (did, w), ev in ext.items():
        choices = ext_to_choices.get((did, w), [])
        if choices:
            model.Add(sum(choices) == 1).OnlyEnforceIf(ev)
            model.Add(sum(choices) == 0).OnlyEnforceIf(ev.Not())
        # If no candidates (both Fri and Mon outside horizon), H9 silently no-ops.

    # lieu-day ⇒ no activity that day.
    for (did, day), choice_vars in lieu_uses.items():
        if not choice_vars:
            continue
        # lieu_taken = OR of choices pointing to (did, day)
        lieu_taken = model.NewBoolVar(f"lieu_taken_{did}_{day}")
        model.AddMaxEquality(lieu_taken, choice_vars)
        for v in _activities_on(did, day, assign_by_dday, oncall, ext, wconsult):
            model.AddImplication(lieu_taken, v.Not())

    # H10 — Leave: enforced by omitting vars on leave days.

    # ----------------------------------------------------------- Soft objective
    penalties: list[cp_model.IntVar | int] = []

    if not feasibility_only:
        session_count: dict[int, cp_model.IntVar] = {}
        oncall_count: dict[int, cp_model.IntVar] = {}
        weekend_count: dict[int, cp_model.IntVar] = {}

        horizon_upper = max(1, inst.n_days * 2)
        by_doc_assign: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for (did, _, _, _), v in assign.items():
            by_doc_assign[did].append(v)
        by_doc_oncall: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for (did, _), v in oncall.items():
            by_doc_oncall[did].append(v)
        by_doc_ext: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for (did, _), v in ext.items():
            by_doc_ext[did].append(v)
        by_doc_wconsult: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for (did, _), v in wconsult.items():
            by_doc_wconsult[did].append(v)
        by_doc_weekend_oncall: dict[int, list[cp_model.IntVar]] = defaultdict(list)
        for (did, day), v in oncall.items():
            if inst.is_weekend(day):
                by_doc_weekend_oncall[did].append(v)

        for d in inst.doctors:
            sc = model.NewIntVar(0, horizon_upper, f"sess_{d.id}")
            terms = by_doc_assign.get(d.id, [])
            if terms:
                model.Add(sc == sum(terms))
            else:
                model.Add(sc == 0)
            session_count[d.id] = sc

            oc = model.NewIntVar(0, inst.n_days, f"occ_{d.id}")
            oc_terms = by_doc_oncall.get(d.id, [])
            if oc_terms:
                model.Add(oc == sum(oc_terms))
            else:
                model.Add(oc == 0)
            oncall_count[d.id] = oc

            wk = model.NewIntVar(0, 3 * inst.n_days, f"wk_{d.id}")
            wk_terms = (
                by_doc_ext.get(d.id, [])
                + by_doc_weekend_oncall.get(d.id, [])
                + by_doc_wconsult.get(d.id, [])
            )
            if wk_terms:
                model.Add(wk == sum(wk_terms))
            else:
                model.Add(wk == 0)
            weekend_count[d.id] = wk

        for tier in ("junior", "senior", "consultant"):
            tier_ids = [d.id for d in inst.doctors if d.tier == tier]
            if not tier_ids:
                continue

            # S1 sessions balance.
            if weights.balance_sessions:
                mx = model.NewIntVar(0, horizon_upper, f"mx_s_{tier}")
                mn = model.NewIntVar(0, horizon_upper, f"mn_s_{tier}")
                model.AddMaxEquality(mx, [session_count[i] for i in tier_ids])
                model.AddMinEquality(mn, [session_count[i] for i in tier_ids])
                gap = model.NewIntVar(0, horizon_upper, f"gap_s_{tier}")
                model.Add(gap == mx - mn)
                penalties.append(gap * weights.balance_sessions)

            # S2 on-call balance (skip consultants — no oncall for them).
            if weights.balance_oncall and tier != "consultant":
                mx = model.NewIntVar(0, inst.n_days, f"mx_o_{tier}")
                mn = model.NewIntVar(0, inst.n_days, f"mn_o_{tier}")
                model.AddMaxEquality(mx, [oncall_count[i] for i in tier_ids])
                model.AddMinEquality(mn, [oncall_count[i] for i in tier_ids])
                gap = model.NewIntVar(0, inst.n_days, f"gap_o_{tier}")
                model.Add(gap == mx - mn)
                penalties.append(gap * weights.balance_oncall)

            # S3 weekend balance.
            if weights.balance_weekend:
                mx = model.NewIntVar(0, 3 * inst.n_days, f"mx_w_{tier}")
                mn = model.NewIntVar(0, 3 * inst.n_days, f"mn_w_{tier}")
                model.AddMaxEquality(mx, [weekend_count[i] for i in tier_ids])
                model.AddMinEquality(mn, [weekend_count[i] for i in tier_ids])
                gap = model.NewIntVar(0, 3 * inst.n_days, f"gap_w_{tier}")
                model.Add(gap == mx - mn)
                penalties.append(gap * weights.balance_weekend)

        # S4 reporting-station consecutive-day spread.
        if weights.reporting_spread:
            for st in inst.stations:
                if not st.is_reporting:
                    continue
                for d in inst.doctors:
                    for day in range(inst.n_days - 1):
                        for sess in st.sessions:
                            a = assign.get((d.id, day, st.name, sess))
                            b = assign.get((d.id, day + 1, st.name, sess))
                            if a is None or b is None:
                                continue
                            pair = model.NewBoolVar(f"rep_{d.id}_{day}_{st.name}_{sess}")
                            model.Add(pair >= a + b - 1)
                            penalties.append(pair * weights.reporting_spread)

        if penalties:
            model.Minimize(sum(penalties))

    # --------------------------------------------------------------- Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = num_workers
    solver.parameters.log_search_progress = log_search_progress

    t0 = time.perf_counter()
    status_int = solver.Solve(model)
    wall = time.perf_counter() - t0

    status_name = {
        cp_model.OPTIMAL: "OPTIMAL",
        cp_model.FEASIBLE: "FEASIBLE",
        cp_model.INFEASIBLE: "INFEASIBLE",
        cp_model.MODEL_INVALID: "MODEL_INVALID",
        cp_model.UNKNOWN: "UNKNOWN",
    }.get(status_int, "UNKNOWN")

    proto = model.Proto()
    n_vars = len(proto.variables)
    n_constraints = len(proto.constraints)

    has_solution = status_name in ("OPTIMAL", "FEASIBLE")
    result = SolveResult(
        status=status_name,
        wall_time_s=wall,
        objective=(solver.ObjectiveValue()
                   if has_solution and not feasibility_only else None),
        best_bound=(solver.BestObjectiveBound()
                    if has_solution and not feasibility_only else None),
        n_vars=n_vars,
        n_constraints=n_constraints,
    )

    if has_solution:
        result.assignments = {
            "stations": {k: solver.Value(v) for k, v in assign.items() if solver.Value(v)},
            "oncall":   {k: solver.Value(v) for k, v in oncall.items() if solver.Value(v)},
            "ext":      {k: solver.Value(v) for k, v in ext.items() if solver.Value(v)},
            "wconsult": {k: solver.Value(v) for k, v in wconsult.items() if solver.Value(v)},
        }
    return result


def _activities_on(
    did: int,
    day: int,
    assign_by_dday: dict[tuple[int, int], list[cp_model.IntVar]],
    oncall: dict[tuple[int, int], cp_model.IntVar],
    ext: dict[tuple[int, int], cp_model.IntVar],
    wconsult: dict[tuple[int, int], cp_model.IntVar],
) -> list[cp_model.IntVar]:
    out: list[cp_model.IntVar] = list(assign_by_dday.get((did, day), []))
    if (did, day) in oncall:
        out.append(oncall[(did, day)])
    if (did, day) in ext:
        out.append(ext[(did, day)])
    if (did, day) in wconsult:
        out.append(wconsult[(did, day)])
    return out


def _exact_one(model: cp_model.CpModel, vars_: list[cp_model.IntVar]) -> None:
    if not vars_:
        model.Add(1 == 0)
    else:
        model.Add(sum(vars_) == 1)
