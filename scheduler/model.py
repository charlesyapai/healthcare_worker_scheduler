"""CP-SAT model for the rostering problem.

See `docs/CONSTRAINTS.md` for the authoritative spec. Every constraint block
below is tagged with the H#/S# label from that doc.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Callable

from ortools.sat.python import cp_model

from scheduler.instance import SESSIONS, Instance


@dataclass
class SolveResult:
    status: str                  # "OPTIMAL" / "FEASIBLE" / "INFEASIBLE" / "UNKNOWN" / "MODEL_INVALID"
    wall_time_s: float
    objective: float | None
    best_bound: float | None
    n_vars: int
    n_constraints: int
    # Time to first feasible solution (captured via callback). None if never.
    first_feasible_s: float | None = None
    # Final per-component penalty values. Keyed by component name (e.g.
    # "S1_balance_sessions_junior"). Value is the weighted contribution.
    penalty_components: dict[str, int] = field(default_factory=dict)
    assignments: dict[str, Any] = field(default_factory=dict)
    # assignments["stations"] = {(d, day, station, sess): 1, ...}
    # assignments["oncall"]   = {(d, day): 1, ...}
    # assignments["ext"]      = {(d, day): 1, ...}
    # assignments["wconsult"] = {(d, day): 1, ...}


@dataclass
class WorkloadWeights:
    """Weights that turn raw assignments into a single per-doctor workload score.

    Used both for display (the 'workload score' column in the UI) and for the
    solver's S0 weighted-balance term (balances `weighted_score + prev_workload`
    across doctors within a tier).

    Integer-valued so the CP-SAT objective stays integer. Defaults reflect
    "weekend work costs more than weekday work" with sensible ratios.
    """
    weekday_session: int = 10      # AM or PM station on a weekday
    weekend_session: int = 15      # AM or PM station on a weekend (if enabled)
    weekday_oncall: int = 20       # Junior/senior on-call on a weekday night
    weekend_oncall: int = 35       # Junior/senior on-call on a weekend night
    weekend_ext: int = 20          # Weekend extended-duty role
    weekend_consult: int = 25      # Consultant weekend role


@dataclass
class ConstraintConfig:
    """Toggles + parameters for the hard constraints. All default on."""
    h4_oncall_cap_enabled: bool = True
    h4_oncall_gap_days: int = 3      # "1-in-N" — 1 on-call per N consecutive days
    h5_post_call_off_enabled: bool = True
    h6_senior_oncall_full_off_enabled: bool = True
    h7_junior_oncall_pm_enabled: bool = True
    h8_weekend_coverage_enabled: bool = True
    h9_lieu_day_enabled: bool = True
    h11_mandatory_weekday_enabled: bool = True   # Soft: penalty per idle doc-day
    # Gap #4 from CONSTRAINTS.md §5: "1 junior + 1 senior every night
    # (weekday and weekend)". Weekends are handled by H8; weekdays need
    # their own constraint. Default OFF here so legacy callers (direct
    # scheduler.solve invocations, existing tests) are unaffected. The
    # v2 API layer defaults this to True in `ConstraintsConfig` so SPA
    # users get weekday coverage unless they explicitly opt out.
    weekday_oncall_coverage_enabled: bool = False


@dataclass
class HoursConfig:
    """Hours worked per role — used for the 'hours per week' display metric.

    Adjustable so each hospital can set its own shift lengths. The numbers
    do NOT affect solver decisions (only the workload weights do); they are
    a reporting convenience so the UI can show 'Dr X works ~42h/week'.
    """
    weekday_am: float = 4.0
    weekday_pm: float = 4.0
    weekend_am: float = 4.0
    weekend_pm: float = 4.0
    weekday_oncall: float = 12.0     # night shift + on-call coverage
    weekend_oncall: float = 16.0     # longer on weekend nights
    weekend_ext: float = 12.0        # extended-duty day shift
    weekend_consult: float = 8.0     # consultant weekend cover


@dataclass
class Weights:
    balance_sessions: int = 5
    balance_oncall: int = 10
    balance_weekend: int = 10
    reporting_spread: int = 5
    balance_workload: int = 40       # S0 — weighted total workload balance
    idle_weekday: int = 100          # S5 — per-idle-doctor-weekday penalty
    preference: int = 5              # S6 — penalty per unmet positive preference


IntermediateCallback = Callable[[dict[str, Any]], None]


class _IntermediateLogger(cp_model.CpSolverSolutionCallback):
    """Invokes `callback` with {wall_s, objective, bound, components, assignments?} on each new solution."""

    def __init__(
        self,
        start: float,
        callback: IntermediateCallback,
        components: dict[str, tuple[cp_model.IntVar, int]] | None = None,
        snapshot_vars: dict[str, dict[tuple, cp_model.IntVar]] | None = None,
        stop_event: threading.Event | None = None,
    ) -> None:
        super().__init__()
        self._start = start
        self._cb = callback
        self._components = components or {}
        self._snapshot_vars = snapshot_vars or {}
        self._stop_event = stop_event

    def on_solution_callback(self) -> None:  # noqa: D401 — CP-SAT API
        try:
            obj = self.ObjectiveValue()
            bound = self.BestObjectiveBound()
        except Exception:
            obj = None
            bound = None
        comp_vals: dict[str, int] = {}
        for name, (var, weight) in self._components.items():
            try:
                comp_vals[name] = int(self.Value(var)) * int(weight)
            except Exception:
                comp_vals[name] = 0
        event: dict[str, Any] = {
            "wall_s": time.perf_counter() - self._start,
            "objective": obj,
            "best_bound": bound,
            "components": comp_vals,
        }
        if self._snapshot_vars:
            snap: dict[str, dict] = {}
            for key, vmap in self._snapshot_vars.items():
                taken = {}
                for k, v in vmap.items():
                    try:
                        if self.Value(v):
                            taken[k] = 1
                    except Exception:
                        continue
                snap[key] = taken
            event["assignments"] = snap
        self._cb(event)
        # Caller-requested early stop (e.g. UI "Stop" button): exit the search
        # with whatever the current best solution is. CP-SAT returns FEASIBLE.
        if self._stop_event is not None and self._stop_event.is_set():
            self.StopSearch()


def solve(
    inst: Instance,
    *,
    time_limit_s: float = 300.0,
    weights: Weights | None = None,
    workload_weights: WorkloadWeights | None = None,
    constraints: ConstraintConfig | None = None,
    num_workers: int = 8,
    log_search_progress: bool = False,
    feasibility_only: bool = False,
    on_intermediate: IntermediateCallback | None = None,
    snapshot_assignments: bool = False,
    stop_event: threading.Event | None = None,
) -> SolveResult:
    """Build and solve the CP-SAT model for `inst`.

    Parameters
    ----------
    on_intermediate : optional callable invoked with a dict
        `{wall_s, objective, best_bound}` each time CP-SAT finds a new
        improving solution. Lets the caller stream progress.
    """
    weights = weights or Weights()
    workload_weights = workload_weights or WorkloadWeights()
    cfg = constraints or ConstraintConfig()
    model = cp_model.CpModel()

    # ------------------------------------------------------------------ Vars
    # assign[d, day, station, sess] — H1, H2, H3.
    assign: dict[tuple[int, int, str, str], cp_model.IntVar] = {}
    # Index assign by (doctor, day) so post-call / lieu loops stay O(1) per hit.
    assign_by_dday: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    # Split by session so H11 can reason about AM/PM separately.
    assign_by_dday_am: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    assign_by_dday_pm: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
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
                    (assign_by_dday_am if sess == "AM" else assign_by_dday_pm)[
                        (d.id, day)].append(v)

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
    lieu_choice: dict[tuple[int, int, str], cp_model.IntVar] = {}
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

    # lieu_taken[d, day] — OR of lieu choices pointing at (d, day). Used by
    # H5/H9 (force no activity) AND H11 (counts as an "excused" weekday).
    lieu_taken: dict[tuple[int, int], cp_model.IntVar] = {}
    for (did, day), choice_vars in lieu_uses.items():
        if not choice_vars:
            continue
        lt = model.NewBoolVar(f"lieu_taken_{did}_{day}")
        model.AddMaxEquality(lt, choice_vars)
        lieu_taken[(did, day)] = lt

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

    # H4 — On-call cap (1-in-N rolling window).
    if cfg.h4_oncall_cap_enabled and cfg.h4_oncall_gap_days >= 2:
        N = cfg.h4_oncall_gap_days
        for d in inst.doctors:
            if d.tier == "consultant":
                continue
            for start in range(inst.n_days - (N - 1)):
                window = [
                    oncall[(d.id, day)]
                    for day in range(start, start + N)
                    if (d.id, day) in oncall
                ]
                if len(window) >= 2:
                    model.Add(sum(window) <= 1)

        # prev_oncall seed: days 0..N-2 can't have on-call if prior-period ended on-call.
        for did in inst.prev_oncall:
            for day in range(min(N - 1, inst.n_days)):
                if (did, day) in oncall:
                    model.Add(oncall[(did, day)] == 0)

    # H5 — Post-call off: oncall[d, t] == 1 ⇒ no activity on t+1.
    post_call: dict[tuple[int, int], cp_model.IntVar] = {}
    if cfg.h5_post_call_off_enabled:
        for d in inst.doctors:
            if d.tier == "consultant":
                continue
            for day in range(inst.n_days - 1):
                if (d.id, day) not in oncall:
                    continue
                oc = oncall[(d.id, day)]
                for v in _activities_on(d.id, day + 1, assign_by_dday, oncall, ext, wconsult):
                    model.AddImplication(oc, v.Not())
                # post_call[d, day+1] mirrors oncall[d, day] for H11's "excused" check.
                pc = model.NewBoolVar(f"pc_{d.id}_{day+1}")
                model.Add(pc == oc)
                post_call[(d.id, day + 1)] = pc

        # Seed continuity: day 0 is post-call if doctor was on-call on day -1.
        for did in inst.prev_oncall:
            for v in _activities_on(did, 0, assign_by_dday, oncall, ext, wconsult):
                model.Add(v == 0)
            # Record as post-call day 0 for H11.
            pc = model.NewBoolVar(f"pc_{did}_0_seed")
            model.Add(pc == 1)
            post_call[(did, 0)] = pc

    # H6 (senior) / H7 (junior) — on-call day activity pattern.
    for d in inst.doctors:
        if d.tier == "consultant":
            continue
        for day in range(inst.n_days):
            if (d.id, day) not in oncall:
                continue
            oc = oncall[(d.id, day)]
            am_vars = assign_by_dday_am.get((d.id, day), [])
            pm_vars = assign_by_dday_pm.get((d.id, day), [])
            if d.tier == "senior" and cfg.h6_senior_oncall_full_off_enabled:
                if am_vars:
                    model.Add(sum(am_vars) == 0).OnlyEnforceIf(oc)
                if pm_vars:
                    model.Add(sum(pm_vars) == 0).OnlyEnforceIf(oc)
            elif d.tier == "junior" and cfg.h7_junior_oncall_pm_enabled:
                if am_vars:
                    model.Add(sum(am_vars) == 0).OnlyEnforceIf(oc)
                # PM == 1 on weekdays (on weekends PM vars don't exist by default).
                if pm_vars and not inst.is_weekend(day):
                    model.Add(sum(pm_vars) == 1).OnlyEnforceIf(oc)

    # Weekday on-call coverage: 1 junior + 1 senior on-call every weekday
    # night (spec §5 gap #4). H8 covers weekends; this closes the weekday
    # gap so Minimal-staffing mode (H11 off) still produces an on-call-
    # covered roster.
    if cfg.weekday_oncall_coverage_enabled:
        juniors_all = [d for d in inst.doctors if d.tier == "junior"]
        seniors_all = [d for d in inst.doctors if d.tier == "senior"]
        for day in range(inst.n_days):
            if inst.is_weekend(day):
                continue
            oc_j = [oncall[(d.id, day)] for d in juniors_all if (d.id, day) in oncall]
            oc_s = [oncall[(d.id, day)] for d in seniors_all if (d.id, day) in oncall]
            _exact_one(model, oc_j)
            _exact_one(model, oc_s)

    # H8 — Weekend coverage.
    if cfg.h8_weekend_coverage_enabled:
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
            for ss in inst.subspecs:
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
    if cfg.h9_lieu_day_enabled:
        ext_to_choices: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
        for (did, w, side), lv in lieu_choice.items():
            ext_to_choices[(did, w)].append(lv)
            model.Add(lv <= ext[(did, w)])
        for (did, w), ev in ext.items():
            choices = ext_to_choices.get((did, w), [])
            if choices:
                model.Add(sum(choices) == 1).OnlyEnforceIf(ev)
                model.Add(sum(choices) == 0).OnlyEnforceIf(ev.Not())

        # lieu-day ⇒ no activity that day.
        for (did, day), lt in lieu_taken.items():
            for v in _activities_on(did, day, assign_by_dday, oncall, ext, wconsult):
                model.AddImplication(lt, v.Not())

    # H10 — Leave: enforced by omitting vars on leave days.

    # H12 — Call blocks (soft-block: doctor can't take on-call that day).
    # Unlike leave, doesn't prevent station/AM/PM work.
    for did, days in inst.no_oncall.items():
        for day in days:
            if (did, day) in oncall:
                model.Add(oncall[(did, day)] == 0)

    # H13 — Session blocks (doctor opts out of a specific AM or PM on a day).
    for did, per_day in inst.no_session.items():
        for day, sessions in per_day.items():
            for sess in sessions:
                blocked_vars = [
                    v for (d, d_day, _, s), v in assign.items()
                    if d == did and d_day == day and s == sess
                ]
                if blocked_vars:
                    model.Add(sum(blocked_vars) == 0)

    # H14 — Per-doctor on-call cap (max_oncalls).
    for d in inst.doctors:
        if d.max_oncalls is None or d.tier == "consultant":
            continue
        doc_oncalls = [oncall[(d.id, day)] for day in range(inst.n_days)
                       if (d.id, day) in oncall]
        if doc_oncalls:
            model.Add(sum(doc_oncalls) <= int(d.max_oncalls))

    # H15 — Manual overrides (force specific assignments).
    for override in inst.overrides:
        did, day, station, sess, role = override
        if role == "STATION" and station and sess:
            v = assign.get((did, day, station, sess))
            if v is not None:
                model.Add(v == 1)
        elif role == "ONCALL":
            v = oncall.get((did, day))
            if v is not None:
                model.Add(v == 1)
        elif role == "EXT":
            v = ext.get((did, day))
            if v is not None:
                model.Add(v == 1)
        elif role == "WCONSULT":
            v = wconsult.get((did, day))
            if v is not None:
                model.Add(v == 1)

    # ----------------------------------------------------------- Soft objective
    penalties: list[cp_model.IntVar | int] = []
    # name -> (var, weight) for the real-time callback and SolveResult.
    penalty_components: dict[str, tuple[cp_model.IntVar, int]] = {}

    # Per-doctor auxiliary counters are computed regardless of objective so
    # they're available for reporting. Only used in penalties when weights > 0.
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

    # ---- H11 / S5 — mandatory weekday assignment (soft, heavy weight).
    # Per-weekday-per-doctor "idle" indicator: 1 if the doctor is neither
    # assigned a station, nor on junior-oncall, nor excused (leave / post-call
    # / senior-oncall-day / lieu-day). FTE-scaled: a 0.5-FTE doctor's idle
    # day costs half as much, so the solver tolerates more idle for part-timers.
    idle_vars: list[cp_model.IntVar] = []
    if cfg.h11_mandatory_weekday_enabled and weights.idle_weekday:
        for d in inst.doctors:
            leave_days = inst.leave.get(d.id, set())
            fte_pct = max(1, int(round(d.fte * 100)))
            per_day_weight = max(1, weights.idle_weekday * fte_pct // 100)
            for day in range(inst.n_days):
                if inst.is_weekend(day):
                    continue
                if day in leave_days:
                    continue  # excused by H10
                working = list(assign_by_dday.get((d.id, day), []))
                if (d.id, day) in oncall:
                    working.append(oncall[(d.id, day)])
                excused: list[cp_model.IntVar] = []
                if (d.id, day) in post_call:
                    excused.append(post_call[(d.id, day)])
                if (d.id, day) in lieu_taken:
                    excused.append(lieu_taken[(d.id, day)])
                idle = model.NewBoolVar(f"idle_{d.id}_{day}")
                model.Add(idle + sum(working) + sum(excused) >= 1)
                idle_vars.append(idle)
                if not feasibility_only:
                    penalties.append(idle * per_day_weight)
        if idle_vars and not feasibility_only:
            idle_total = model.NewIntVar(0, len(idle_vars), "idle_total")
            model.Add(idle_total == sum(idle_vars))
            penalty_components["S5_idle_weekday_count"] = (
                idle_total, weights.idle_weekday)

    if not feasibility_only:
        session_count: dict[int, cp_model.IntVar] = {}
        oncall_count: dict[int, cp_model.IntVar] = {}
        weekend_count: dict[int, cp_model.IntVar] = {}
        # Weighted workload per doctor (includes prev_workload carry-in as an
        # additive offset: balance is max(wl[d]+prev) − min(wl[d]+prev) so
        # doctors who did more last period naturally get less this period).
        weighted_workload: dict[int, cp_model.IntVar] = {}

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

            # Weighted workload: sum of weighted terms per assignment type.
            wl_terms: list[cp_model.IntVar | int] = []
            for (did, day, _st, sess), v in assign.items():
                if did != d.id:
                    continue
                w = (workload_weights.weekend_session
                     if inst.is_weekend(day)
                     else workload_weights.weekday_session)
                wl_terms.append(v * w)
            for (did, day), v in oncall.items():
                if did != d.id:
                    continue
                w = (workload_weights.weekend_oncall
                     if inst.is_weekend(day)
                     else workload_weights.weekday_oncall)
                wl_terms.append(v * w)
            for (did, _), v in ext.items():
                if did == d.id:
                    wl_terms.append(v * workload_weights.weekend_ext)
            for (did, _), v in wconsult.items():
                if did == d.id:
                    wl_terms.append(v * workload_weights.weekend_consult)

            # Upper bound: worst case every day × highest single-day weight × 2 sessions.
            wl_upper = max(
                1,
                inst.n_days * max(
                    workload_weights.weekday_session,
                    workload_weights.weekend_session,
                    workload_weights.weekday_oncall,
                    workload_weights.weekend_oncall,
                    workload_weights.weekend_ext,
                    workload_weights.weekend_consult,
                ) * 2,
            )
            wl = model.NewIntVar(0, wl_upper, f"wlw_{d.id}")
            if wl_terms:
                model.Add(wl == sum(wl_terms))
            else:
                model.Add(wl == 0)
            weighted_workload[d.id] = wl

        for tier in ("junior", "senior", "consultant"):
            tier_ids = [d.id for d in inst.doctors if d.tier == tier]
            if not tier_ids:
                continue

            # S0 — weighted-workload balance including prev_workload carry-in
            # AND per-doctor FTE scaling. FTE-adjusted score is
            # weighted_workload[d] × (100 / fte_pct[d]) so a 0.5-FTE doctor's
            # score is doubled for balance purposes (solver gives them less).
            if weights.balance_workload:
                doc_by_id = {d.id: d for d in inst.doctors}
                adj_upper = max(1, horizon_upper * 40 * 10)  # 10x slack for FTE
                adj_lower = 0
                adj_vars: list[cp_model.IntVar] = []
                for i in tier_ids:
                    fte_pct = max(1, int(round(doc_by_id[i].fte * 100)))
                    # multiplier K = round(100 / fte_pct). K=1 for fte=1.0;
                    # K=2 for fte=0.5; K=1 for fte=0.8 (12% rounding error).
                    K = max(1, round(100 / fte_pct))
                    prev = int(inst.prev_workload.get(i, 0))
                    adj = model.NewIntVar(adj_lower, adj_upper, f"adj_{tier}_{i}")
                    model.Add(adj == weighted_workload[i] * K + prev)
                    adj_vars.append(adj)
                mx = model.NewIntVar(adj_lower, adj_upper, f"mx_wl_{tier}")
                mn = model.NewIntVar(adj_lower, adj_upper, f"mn_wl_{tier}")
                model.AddMaxEquality(mx, adj_vars)
                model.AddMinEquality(mn, adj_vars)
                gap = model.NewIntVar(0, adj_upper - adj_lower, f"gap_wl_{tier}")
                model.Add(gap == mx - mn)
                penalties.append(gap * weights.balance_workload)
                penalty_components[f"S0_workload_gap_{tier}"] = (
                    gap, weights.balance_workload)

            # S1 sessions balance.
            if weights.balance_sessions:
                mx = model.NewIntVar(0, horizon_upper, f"mx_s_{tier}")
                mn = model.NewIntVar(0, horizon_upper, f"mn_s_{tier}")
                model.AddMaxEquality(mx, [session_count[i] for i in tier_ids])
                model.AddMinEquality(mn, [session_count[i] for i in tier_ids])
                gap = model.NewIntVar(0, horizon_upper, f"gap_s_{tier}")
                model.Add(gap == mx - mn)
                penalties.append(gap * weights.balance_sessions)
                penalty_components[f"S1_sessions_gap_{tier}"] = (gap, weights.balance_sessions)

            # S2 on-call balance (skip consultants — no oncall for them).
            if weights.balance_oncall and tier != "consultant":
                mx = model.NewIntVar(0, inst.n_days, f"mx_o_{tier}")
                mn = model.NewIntVar(0, inst.n_days, f"mn_o_{tier}")
                model.AddMaxEquality(mx, [oncall_count[i] for i in tier_ids])
                model.AddMinEquality(mn, [oncall_count[i] for i in tier_ids])
                gap = model.NewIntVar(0, inst.n_days, f"gap_o_{tier}")
                model.Add(gap == mx - mn)
                penalties.append(gap * weights.balance_oncall)
                penalty_components[f"S2_oncall_gap_{tier}"] = (gap, weights.balance_oncall)

            # S3 weekend balance.
            if weights.balance_weekend:
                mx = model.NewIntVar(0, 3 * inst.n_days, f"mx_w_{tier}")
                mn = model.NewIntVar(0, 3 * inst.n_days, f"mn_w_{tier}")
                model.AddMaxEquality(mx, [weekend_count[i] for i in tier_ids])
                model.AddMinEquality(mn, [weekend_count[i] for i in tier_ids])
                gap = model.NewIntVar(0, 3 * inst.n_days, f"gap_w_{tier}")
                model.Add(gap == mx - mn)
                penalties.append(gap * weights.balance_weekend)
                penalty_components[f"S3_weekend_gap_{tier}"] = (gap, weights.balance_weekend)

        # S6 — Positive preferences (soft bonus for assigning preferred session).
        # Each (doctor, day, session) the doctor asked for costs `preference`
        # when the solver doesn't honour it.
        if weights.preference and inst.prefer_session:
            unmet_prefs: list[cp_model.IntVar] = []
            for did, per_day in inst.prefer_session.items():
                for day, sessions in per_day.items():
                    for sess in sessions:
                        sess_vars = [
                            v for (d, d_day, _, s), v in assign.items()
                            if d == did and d_day == day and s == sess
                        ]
                        if not sess_vars:
                            continue
                        unmet = model.NewBoolVar(f"pref_miss_{did}_{day}_{sess}")
                        # unmet = 1 - sum(sess_vars), bounded to [0,1]. Since
                        # sess_vars is bool-set summing to 0 or 1 under H2.
                        model.Add(sum(sess_vars) + unmet == 1)
                        unmet_prefs.append(unmet)
            if unmet_prefs:
                pref_total = model.NewIntVar(0, len(unmet_prefs), "pref_total")
                model.Add(pref_total == sum(unmet_prefs))
                penalties.append(pref_total * weights.preference)
                penalty_components["S6_unmet_preferences"] = (
                    pref_total, weights.preference)

        # S4 reporting-station consecutive-day spread.
        if weights.reporting_spread:
            rep_pair_vars: list[cp_model.IntVar] = []
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
                            rep_pair_vars.append(pair)
            if rep_pair_vars:
                rep_total = model.NewIntVar(0, len(rep_pair_vars), "rep_total")
                model.Add(rep_total == sum(rep_pair_vars))
                penalty_components["S4_reporting_count"] = (rep_total, weights.reporting_spread)

        if penalties:
            model.Minimize(sum(penalties))

    # --------------------------------------------------------------- Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = num_workers
    solver.parameters.log_search_progress = log_search_progress

    # Always capture first-feasible time, even if the caller didn't pass a
    # streaming callback. Chain caller's callback if present.
    first_feasible: dict[str, float] = {}

    def _dispatch(event: dict[str, Any]) -> None:
        if "first" not in first_feasible:
            first_feasible["first"] = event["wall_s"]
        if on_intermediate is not None:
            on_intermediate(event)

    t0 = time.perf_counter()
    snapshot_maps = None
    if snapshot_assignments:
        snapshot_maps = {
            "stations": assign,
            "oncall": oncall,
            "ext": ext,
            "wconsult": wconsult,
        }
    if not feasibility_only:
        logger = _IntermediateLogger(
            t0, _dispatch, penalty_components, snapshot_maps,
            stop_event=stop_event,
        )
        status_int = solver.Solve(model, logger)
    elif stop_event is not None:
        # Even in feasibility-only mode, honour the stop signal by attaching
        # a minimal callback whose only job is to call StopSearch().
        logger = _IntermediateLogger(
            t0, lambda _e: None, None, None, stop_event=stop_event)
        status_int = solver.Solve(model, logger)
    else:
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
    final_components: dict[str, int] = {}
    if has_solution and not feasibility_only:
        for name, (var, weight) in penalty_components.items():
            try:
                final_components[name] = int(solver.Value(var)) * int(weight)
            except Exception:
                pass

    result = SolveResult(
        status=status_name,
        wall_time_s=wall,
        objective=(solver.ObjectiveValue()
                   if has_solution and not feasibility_only else None),
        best_bound=(solver.BestObjectiveBound()
                    if has_solution and not feasibility_only else None),
        n_vars=n_vars,
        n_constraints=n_constraints,
        first_feasible_s=first_feasible.get("first"),
        penalty_components=final_components,
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
