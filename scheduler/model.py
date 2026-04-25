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

from scheduler.instance import SESSIONS, Instance, OnCallType


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
    # assignments["stations"]       = {(d, day, station, sess): 1, ...}
    # assignments["oncall_by_type"] = {type_key: {(d, day): 1, ...}, ...}
    # Back-compat aggregate views (populated from types whose
    # legacy_role_alias matches):
    #   assignments["oncall"]   = {(d, day): 1, ...}  (ONCALL alias)
    #   assignments["ext"]      = {(d, day): 1, ...}  (WEEKEND_EXT alias)
    #   assignments["wconsult"] = {(d, day): 1, ...}  (WEEKEND_CONSULT alias)


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
    """Toggles + parameters for the hard constraints. Phase B: most legacy
    on-call toggles are now per-OnCallType (frequency cap, post-shift rest,
    works-full-day / works-pm-only, daily required headcount). Only the
    statutory rest master override (`h5_post_call_off_enabled`), the lieu
    day rule (`h9_lieu_day_enabled`), and the idle-weekday penalty
    (`h11_mandatory_weekday_enabled`) remain global."""
    # Master override — when False, every type's `next_day_off=True`
    # is silently ignored. Useful for stress fixtures that need to
    # bypass post-shift rest entirely.
    h5_post_call_off_enabled: bool = True
    h9_lieu_day_enabled: bool = True
    h11_mandatory_weekday_enabled: bool = True   # Soft: penalty per idle doc-day


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
    warm_start: dict[str, Any] | None = None,
    # CP-SAT parameter passthrough — additive kwargs that map straight
    # onto `solver.parameters.*`. Used by the Lab tab's batch runner
    # to make runs reproducible and to sweep parameters. Defaults match
    # OR-Tools defaults so existing call sites are unaffected.
    random_seed: int = 0,
    search_branching: str = "AUTOMATIC",
    linearization_level: int = 1,
    cp_model_presolve: bool = True,
    optimize_with_core: bool = False,
    use_lns_only: bool = False,
    # --- Model-level tuning toggles (A/B-able via /lab/benchmark) ---
    symmetry_break: bool = False,
    decision_strategy: str = "default",
    redundant_aggregates: bool = False,
) -> SolveResult:
    """Build and solve the CP-SAT model for `inst`.

    Parameters
    ----------
    on_intermediate : optional callable invoked with a dict
        `{wall_s, objective, best_bound}` each time CP-SAT finds a new
        improving solution. Lets the caller stream progress.
    warm_start : optional assignments dict in the same shape as
        `SolveResult.assignments` (keys: "stations", "oncall", "ext",
        "wconsult"; each a tuple-keyed dict of 1-values). Registered as
        CP-SAT hints so the solver finds the previous solution first
        and then spends the rest of its budget trying to improve on it.
        Mismatched keys (e.g. the instance changed since) are silently
        ignored — the solver falls back to a fresh search.
    random_seed, search_branching, linearization_level, cp_model_presolve,
    optimize_with_core, use_lns_only : CP-SAT parameter levers exposed
        for reproducibility + parameter-sweep experiments. For
        bit-deterministic runs, set `num_workers=1` AND a fixed
        `random_seed` — the parallel portfolio is not deterministic.
        `search_branching` values follow CP-SAT's enum
        (AUTOMATIC, FIXED_SEARCH, PORTFOLIO_SEARCH,
        LP_SEARCH, PSEUDO_COST_SEARCH, PORTFOLIO_WITH_QUICK_RESTART_SEARCH).
    symmetry_break : when True, add lex-order constraints on groups of
        interchangeable doctors (same tier/eligibility/FTE/leave
        pattern). Interchangeable doctors would otherwise let CP-SAT
        explore swapped-but-identical solutions; forcing an ordering by
        on-call count collapses those to one representative.
    decision_strategy : "default" keeps CP-SAT's automatic var
        selection. "oncall_first" adds a high-priority decision strategy
        that branches on on-call variables before station assignments.
        On-call choices cascade via H5 (post-call off) and H4 (1-in-N
        gap), so committing to them first usually prunes faster.
    redundant_aggregates : when True, add per-tier total-oncall equality
        constraints. They're logically implied by H8 + weekday on-call
        coverage, but materialising them as explicit sums can help
        CP-SAT's LP relaxation find a tighter dual bound.
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
    # Stations whose `sessions` is ("FULL_DAY",). Booking one of these
    # means the doctor holds both AM and PM on that station for the
    # whole day. We realise this via a paired-variable trick: create
    # both an AM and PM assign var and lock them equal. Every downstream
    # constraint that counts AM-only or PM-only vars keeps working
    # without needing to know about FULL_DAY at all — the only place
    # we special-case is H1 (station coverage), which must count pairs
    # once, not twice.
    full_day_station_names = {
        s.name for s in inst.stations if "FULL_DAY" in s.sessions
    }
    for d in inst.doctors:
        leave_days = inst.leave.get(d.id, set())
        for day in range(inst.n_days):
            if day in leave_days:
                continue
            is_we = inst.is_weekend(day)
            for st_name in d.eligible_stations:
                st = station_by_name[st_name]
                # Per-station weekday/weekend gate. station.eligible_tiers is
                # advisory metadata only — not enforced here. Per-doctor
                # `eligible_stations` is the only enforced eligibility check.
                if is_we and not st.weekend_enabled:
                    continue
                if not is_we and not st.weekday_enabled:
                    continue
                is_full_day = st_name in full_day_station_names
                session_iter = ("AM", "PM") if is_full_day else SESSIONS
                created_vars: list[cp_model.IntVar] = []
                for sess in session_iter:
                    if not is_full_day and sess not in st.sessions:
                        continue
                    v = model.NewBoolVar(f"a_{d.id}_{day}_{st_name}_{sess}")
                    assign[(d.id, day, st_name, sess)] = v
                    assign_by_dday[(d.id, day)].append(v)
                    (assign_by_dday_am if sess == "AM" else assign_by_dday_pm)[
                        (d.id, day)].append(v)
                    created_vars.append(v)
                if is_full_day and len(created_vars) == 2:
                    # Pair: AM == PM for this (doctor, day, station). If a
                    # surgeon takes the OR list, they're on it both halves.
                    model.Add(created_vars[0] == created_vars[1])

    # ---------------- Generic on-call type variables (Phase B) -----------
    # `oc_vars[type_key][(doctor_id, day)]` is the indicator that a doctor
    # holds that on-call type on that calendar day. Vars exist only on
    # (doctor, day, type) triples where:
    #   * doctor's `eligible_oncall_types` includes the type's key,
    #   * the day matches the type's `days_active` (with PH treated as
    #     weekend-day-equivalent for activation purposes), and
    #   * the doctor is not on leave that day.
    types_by_key = {t.key: t for t in inst.on_call_types}

    def _day_active_for_type(day: int, t: OnCallType) -> bool:
        wd = inst.weekday_of(day)
        if wd in t.days_active:
            return True
        if day in inst.public_holidays and (5 in t.days_active or 6 in t.days_active):
            return True
        return False

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
                if not _day_active_for_type(day, t):
                    continue
                v = model.NewBoolVar(f"oc_{t.key}_{d.id}_{day}")
                oc_vars[t.key][(d.id, day)] = v

    # Mutual exclusion: each (doctor, day) holds at most one on-call type.
    by_dday_oncall: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    for type_map in oc_vars.values():
        for key, v in type_map.items():
            by_dday_oncall[key].append(v)
    for vars_ in by_dday_oncall.values():
        if len(vars_) >= 2:
            model.Add(sum(vars_) <= 1)

    # ---------------- Lieu-day machinery (H9) -----------------------------
    # Applies to any on-call type with `counts_as_weekend_role=True` and
    # neither `works_full_day` nor `works_pm_only` (those types already
    # carry their own day-of pattern, like the legacy senior on-call).
    lieu_choice: dict[tuple[int, int, str, str], cp_model.IntVar] = {}
    lieu_uses: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
    for t in inst.on_call_types:
        if not t.counts_as_weekend_role:
            continue
        if t.works_full_day or t.works_pm_only:
            continue
        for d in inst.doctors:
            if t.key not in d.eligible_oncall_types:
                continue
            leave_days = inst.leave.get(d.id, set())
            for w in range(inst.n_days):
                if (d.id, w) not in oc_vars[t.key]:
                    continue
                if not inst.is_weekend(w):
                    # Lieu mechanic only meaningful when the assignment
                    # falls on a calendar weekend day.
                    continue
                for side, weekday_target in (("FRI", 4), ("MON", 0)):
                    target_day = None
                    for dx in range(1, 8):
                        cand = w - dx if side == "FRI" else w + dx
                        if cand < 0 or cand >= inst.n_days:
                            break
                        if inst.weekday_of(cand) == weekday_target:
                            target_day = cand
                            break
                    if target_day is None or target_day in leave_days:
                        continue
                    lv = model.NewBoolVar(f"lieu_{t.key}_{d.id}_{w}_{side}")
                    lieu_choice[(d.id, w, t.key, side)] = lv
                    lieu_uses[(d.id, target_day)].append(lv)

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
        is_we = inst.is_weekend(day)
        for st in inst.stations:
            # Per-station weekday/weekend gate — a station that's not enabled
            # on this kind of day contributes no demand.
            if is_we and not st.weekend_enabled:
                continue
            if not is_we and not st.weekday_enabled:
                continue
            # A FULL_DAY station's AM and PM vars are paired (AM == PM),
            # so counting either set gives the number of full-day holders.
            # Use AM side to avoid double-counting.
            if st.name in full_day_station_names:
                effective_sessions: tuple[str, ...] = ("AM",)
            else:
                effective_sessions = tuple(st.sessions)
            for sess in effective_sessions:
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

    # H4 — Per-OnCallType frequency cap (1-in-N rolling window).
    # Each type's `frequency_cap_days` controls the cap for that type
    # only; None means uncapped (e.g. weekend EXT in legacy semantics).
    for t in inst.on_call_types:
        N = t.frequency_cap_days
        if N is None or N < 2:
            continue
        type_vars = oc_vars[t.key]
        for d in inst.doctors:
            if t.key not in d.eligible_oncall_types:
                continue
            for start in range(inst.n_days - (N - 1)):
                window = [
                    type_vars[(d.id, day)]
                    for day in range(start, start + N)
                    if (d.id, day) in type_vars
                ]
                if len(window) >= 2:
                    model.Add(sum(window) <= 1)
        # prev_oncall seed: days 0..N-2 can't have on-call of any type
        # with frequency_cap_days >= 2 if doctor ended prior period on-call.
        for did in inst.prev_oncall:
            for day in range(min(N - 1, inst.n_days)):
                if (did, day) in type_vars:
                    model.Add(type_vars[(did, day)] == 0)

    # H5 — Post-shift rest. Per-OnCallType: types with `next_day_off=True`
    # force no activity on day+1. The global cfg.h5_post_call_off_enabled
    # is a master override (matches legacy shape).
    post_call: dict[tuple[int, int], cp_model.IntVar] = {}
    if cfg.h5_post_call_off_enabled:
        oc_yesterday: dict[tuple[int, int], list[cp_model.IntVar]] = defaultdict(list)
        for t in inst.on_call_types:
            if not t.next_day_off:
                continue
            for (did, day), oc in oc_vars[t.key].items():
                if day + 1 < inst.n_days:
                    oc_yesterday[(did, day + 1)].append(oc)
                    for v in _activities_on(did, day + 1, assign_by_dday, oc_vars):
                        model.AddImplication(oc, v.Not())
        # post_call indicator for H11: OR across types that opted in.
        for key, vars_ in oc_yesterday.items():
            if not vars_:
                continue
            pc = model.NewBoolVar(f"pc_{key[0]}_{key[1]}")
            model.AddMaxEquality(pc, vars_)
            post_call[key] = pc
        # Seed continuity: day 0 is post-call if doctor was on-call on day -1.
        for did in inst.prev_oncall:
            for v in _activities_on(did, 0, assign_by_dday, oc_vars):
                model.Add(v == 0)
            pc = model.NewBoolVar(f"pc_{did}_0_seed")
            model.Add(pc == 1)
            post_call[(did, 0)] = pc

    # H6 / H7 — Per-OnCallType day-of activity pattern.
    # `works_full_day=True` (legacy H6 senior) ⇒ no AM/PM that day.
    # `works_pm_only=True`  (legacy H7 junior) ⇒ AM=0, PM=1 (weekdays).
    for t in inst.on_call_types:
        if not (t.works_full_day or t.works_pm_only):
            continue
        for (did, day), oc in oc_vars[t.key].items():
            am_vars = assign_by_dday_am.get((did, day), [])
            pm_vars = assign_by_dday_pm.get((did, day), [])
            if t.works_full_day:
                if am_vars:
                    model.Add(sum(am_vars) == 0).OnlyEnforceIf(oc)
                if pm_vars:
                    model.Add(sum(pm_vars) == 0).OnlyEnforceIf(oc)
            elif t.works_pm_only:
                if am_vars:
                    model.Add(sum(am_vars) == 0).OnlyEnforceIf(oc)
                # PM == 1 on weekdays only (weekend PM vars don't exist
                # for weekday-only stations).
                if pm_vars and not inst.is_weekend(day):
                    model.Add(sum(pm_vars) == 1).OnlyEnforceIf(oc)

    # H8 / weekday on-call coverage — Per-OnCallType `daily_required`.
    # Replaces the legacy weekday_oncall_coverage flag + per-tier H8 exact-1
    # rules with a single per-type-per-active-day equality. The migration of
    # pre-Phase-B sessions creates 5 types (oncall_jr, oncall_sr,
    # weekend_ext_jr, weekend_ext_sr, weekend_consult) so the legacy
    # "1 jr + 1 sr per night, 1 jr-EXT + 1 sr-EXT per weekend, N consultants"
    # behaviour is preserved exactly.
    for t in inst.on_call_types:
        if t.daily_required <= 0:
            continue
        for day in range(inst.n_days):
            if not _day_active_for_type(day, t):
                continue
            day_vars = [v for (_did, dd), v in oc_vars[t.key].items() if dd == day]
            if not day_vars:
                # No eligible doctor available — infeasible on this day.
                model.Add(1 == 0)
                continue
            model.Add(sum(day_vars) == t.daily_required)

    # H9 — Day in lieu for weekend-role on-call types.
    if cfg.h9_lieu_day_enabled:
        oc_to_choices: dict[tuple[int, int, str], list[cp_model.IntVar]] = defaultdict(list)
        for (did, w, type_key, _side), lv in lieu_choice.items():
            oc_to_choices[(did, w, type_key)].append(lv)
            model.Add(lv <= oc_vars[type_key][(did, w)])
        for (did, w, type_key), choices in oc_to_choices.items():
            ev = oc_vars.get(type_key, {}).get((did, w))
            if ev is None:
                continue
            model.Add(sum(choices) == 1).OnlyEnforceIf(ev)
            model.Add(sum(choices) == 0).OnlyEnforceIf(ev.Not())
        # lieu-day ⇒ no activity that day.
        for (did, day), lt in lieu_taken.items():
            for v in _activities_on(did, day, assign_by_dday, oc_vars):
                model.AddImplication(lt, v.Not())

    # H10 — Leave: enforced by omitting vars on leave days.

    # H12 — Call blocks (no on-call across all types that day).
    for did, days in inst.no_oncall.items():
        for day in days:
            for t in inst.on_call_types:
                v = oc_vars[t.key].get((did, day))
                if v is not None:
                    model.Add(v == 0)

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

    # H14 — Per-doctor on-call cap (max_oncalls). Sums across all types.
    for d in inst.doctors:
        if d.max_oncalls is None:
            continue
        doc_oncalls: list[cp_model.IntVar] = []
        for t in inst.on_call_types:
            for (did, _day), v in oc_vars[t.key].items():
                if did == d.id:
                    doc_oncalls.append(v)
        if doc_oncalls:
            model.Add(sum(doc_oncalls) <= int(d.max_oncalls))

    # H15 — Manual overrides. Phase B accepts:
    #   role = "STATION"            (with station + sess kwargs)
    #   role = "ONCALL_<type_key>"  (per-type, post-Phase-B)
    #   role = "ONCALL" / "EXT" / "WCONSULT"  (legacy back-compat;
    #           resolved against any type with matching legacy_role_alias).
    legacy_alias_for: dict[str, str] = {
        "ONCALL": "ONCALL", "EXT": "WEEKEND_EXT", "WCONSULT": "WEEKEND_CONSULT",
    }
    types_by_alias: dict[str, list[str]] = defaultdict(list)
    for t in inst.on_call_types:
        if t.legacy_role_alias:
            types_by_alias[t.legacy_role_alias].append(t.key)
    for override in inst.overrides:
        did, day, station, sess, role = override
        if role == "STATION" and station and sess:
            v = assign.get((did, day, station, sess))
            if v is not None:
                model.Add(v == 1)
            continue
        if role.startswith("ONCALL_"):
            type_key = role[len("ONCALL_"):]
            v = oc_vars.get(type_key, {}).get((did, day))
            if v is not None:
                model.Add(v == 1)
            continue
        legacy_alias = legacy_alias_for.get(role)
        if legacy_alias is None:
            continue
        candidates = [
            oc_vars[type_key].get((did, day))
            for type_key in types_by_alias.get(legacy_alias, [])
        ]
        candidates = [v for v in candidates if v is not None]
        if candidates:
            # Force exactly one type with this alias to fire on this day
            # for this doctor (matches legacy "ONCALL=1" override semantic
            # — picks whichever the doctor is eligible for).
            model.Add(sum(candidates) == 1)

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
    # Phase B: per-doctor on-call totals span all user-defined types.
    by_doc_oncall: dict[int, list[cp_model.IntVar]] = defaultdict(list)
    by_doc_weekend: dict[int, list[cp_model.IntVar]] = defaultdict(list)
    for t in inst.on_call_types:
        for (did, day), v in oc_vars[t.key].items():
            by_doc_oncall[did].append(v)
            if t.counts_as_weekend_role or inst.is_weekend(day):
                by_doc_weekend[did].append(v)

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
                # Any on-call type the doctor holds today counts as working.
                for type_map in oc_vars.values():
                    v = type_map.get((d.id, day))
                    if v is not None:
                        working.append(v)
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
            wk_terms = by_doc_weekend.get(d.id, [])
            if wk_terms:
                model.Add(wk == sum(wk_terms))
            else:
                model.Add(wk == 0)
            weekend_count[d.id] = wk

            # Weighted workload: sum of weighted terms per assignment.
            wl_terms: list[cp_model.IntVar | int] = []
            for (did, day, _st, sess), v in assign.items():
                if did != d.id:
                    continue
                w = (workload_weights.weekend_session
                     if inst.is_weekend(day)
                     else workload_weights.weekday_session)
                wl_terms.append(v * w)
            # On-call assignments: per-type weight resolution. Types with a
            # legacy alias map to the matching legacy weight; others fall
            # back to the weekday/weekend on-call weights.
            for t in inst.on_call_types:
                for (did, day), v in oc_vars[t.key].items():
                    if did != d.id:
                        continue
                    wl_terms.append(v * _oncall_weight(t, day, inst, workload_weights))

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

            # S2 on-call balance. Phase B: consultants now have on-call
            # vars (e.g. weekend_consult), so balance applies to all tiers
            # — but only when at least one doctor in the tier is eligible
            # for any on-call type.
            tier_has_oncall = any(by_doc_oncall.get(i) for i in tier_ids)
            if weights.balance_oncall and tier_has_oncall:
                oc_max = max(2, inst.n_days * len(inst.on_call_types))
                mx = model.NewIntVar(0, oc_max, f"mx_o_{tier}")
                mn = model.NewIntVar(0, oc_max, f"mn_o_{tier}")
                model.AddMaxEquality(mx, [oncall_count[i] for i in tier_ids])
                model.AddMinEquality(mn, [oncall_count[i] for i in tier_ids])
                gap = model.NewIntVar(0, oc_max, f"gap_o_{tier}")
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

        # S7 — Per-doctor role preferences (soft shortfall).
        # For each (doctor, role, min, priority), count actual allocations
        # to the role across the horizon and add a shortfall variable
        # ``max(0, min − actual)``. Penalty weight is ``priority``
        # directly (independent of weights.preference) so two preferences
        # with different priorities can coexist meaningfully; priority = 1
        # is a gentle nudge, priority = 10 is "try hard".
        if inst.role_preferences:
            rp_shortfalls: list[tuple[cp_model.IntVar, int]] = []
            rp_shortfall_ub = 0
            station_names = {s.name for s in inst.stations}
            for did, per_role in inst.role_preferences.items():
                for role, (min_alloc, priority) in per_role.items():
                    if min_alloc <= 0 or priority <= 0:
                        continue
                    # Resolve the actual-allocation vars for this role.
                    actual_vars: list[cp_model.IntVar] = []
                    if role in station_names:
                        for (d, _day, st_name, _sess), v in assign.items():
                            if d == did and st_name == role:
                                actual_vars.append(v)
                    elif role.startswith("ONCALL_"):
                        # Per-type role preference (post-Phase-B form).
                        type_key = role[len("ONCALL_"):]
                        type_map = oc_vars.get(type_key, {})
                        for (d, _day), v in type_map.items():
                            if d == did:
                                actual_vars.append(v)
                    elif role in ("ONCALL", "WEEKEND_EXT", "WEEKEND_CONSULT"):
                        # Legacy back-compat: aggregate across every type
                        # whose `legacy_role_alias` matches the literal.
                        for t in inst.on_call_types:
                            if t.legacy_role_alias != role:
                                continue
                            for (d, _day), v in oc_vars[t.key].items():
                                if d == did:
                                    actual_vars.append(v)
                    else:
                        # Unknown role label — skip silently. UI validates.
                        continue
                    if not actual_vars:
                        # Doctor is ineligible for the role anywhere — the
                        # preference can't ever be met. Record full shortfall
                        # so the audit exposes the mismatch.
                        shortfall_const = min_alloc * priority
                        if shortfall_const > 0:
                            # Materialise a constant var so the component
                            # shows up in penalty_components.
                            zero = model.NewIntVar(0, 0, f"rp_zero_{did}_{role}")
                            penalty_components[
                                f"S7_role_pref_{did}_{role}_missed"
                            ] = (zero, shortfall_const)
                            penalties.append(shortfall_const)
                        continue
                    actual = model.NewIntVar(
                        0, len(actual_vars), f"rp_actual_{did}_{role}"
                    )
                    model.Add(actual == sum(actual_vars))
                    shortfall = model.NewIntVar(
                        0, min_alloc, f"rp_shortfall_{did}_{role}"
                    )
                    # shortfall ≥ min_alloc − actual, shortfall ≥ 0
                    model.Add(shortfall >= min_alloc - actual)
                    penalties.append(shortfall * int(priority))
                    rp_shortfalls.append((shortfall, int(priority)))
                    rp_shortfall_ub += min_alloc
            if rp_shortfalls:
                total_shortfall = model.NewIntVar(
                    0, max(1, rp_shortfall_ub), "rp_total_shortfall",
                )
                model.Add(total_shortfall == sum(s for s, _ in rp_shortfalls))
                # Weight = 1 so the component shows raw shortfall sum; the
                # per-preference `priority` already weights each one in the
                # penalties list above.
                penalty_components["S7_role_pref_shortfall"] = (
                    total_shortfall, 1,
                )

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

    # ------------------------------------------------- Tuning toggles
    # Applied after the model structure is fully built but before warm-
    # start / solve. All three are additive — they don't change which
    # solutions are feasible, only how CP-SAT searches for them.

    if symmetry_break:
        _apply_symmetry_break(
            model, inst, by_doc_oncall, by_doc_assign, by_doc_weekend,
        )

    if redundant_aggregates:
        _apply_redundant_aggregates(model, inst, by_doc_oncall)

    if decision_strategy and decision_strategy != "default":
        # Flatten oc_vars into a single var list for branching priority.
        all_oc_vars: dict[tuple[int, int], cp_model.IntVar] = {}
        for type_map in oc_vars.values():
            all_oc_vars.update(type_map)
        _apply_decision_strategy(
            model, decision_strategy, all_oc_vars, assign,
        )

    # --------------------------------------------------------------- Warm start
    if warm_start:
        # Phase B canonical key: warm_start["oncall_by_type"] = {type_key:
        # {(d, day): 1, ...}, ...}. Legacy keys "oncall" / "ext" / "wconsult"
        # are accepted as back-compat: each routes to whichever types share
        # the matching legacy_role_alias.
        for key, val in (warm_start.get("stations") or {}).items():
            var = assign.get(key)
            if var is not None:
                try:
                    model.AddHint(var, int(bool(val)))
                except Exception:
                    pass
        oct_by_alias: dict[str, list[str]] = defaultdict(list)
        for t in inst.on_call_types:
            if t.legacy_role_alias:
                oct_by_alias[t.legacy_role_alias].append(t.key)
        for type_key, hinted in (warm_start.get("oncall_by_type") or {}).items():
            type_map = oc_vars.get(type_key, {})
            for k, val in hinted.items():
                var = type_map.get(k)
                if var is None:
                    continue
                try:
                    model.AddHint(var, int(bool(val)))
                except Exception:
                    continue
        for legacy_key, alias in (("oncall", "ONCALL"), ("ext", "WEEKEND_EXT"),
                                  ("wconsult", "WEEKEND_CONSULT")):
            hinted = warm_start.get(legacy_key) or {}
            if not hinted:
                continue
            keys_for_alias = oct_by_alias.get(alias, [])
            for k, val in hinted.items():
                # Try each candidate type; first one that has the var wins.
                for type_key in keys_for_alias:
                    var = oc_vars.get(type_key, {}).get(k)
                    if var is None:
                        continue
                    try:
                        model.AddHint(var, int(bool(val)))
                    except Exception:
                        pass
                    break

    # --------------------------------------------------------------- Solve
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit_s
    solver.parameters.num_search_workers = num_workers
    solver.parameters.log_search_progress = log_search_progress
    # Reproducibility / parameter-sweep levers. Map straight onto CP-SAT's
    # protobuf fields. Unknown search_branching values fall back to AUTOMATIC
    # so the solver always has a valid strategy.
    solver.parameters.random_seed = int(random_seed)
    solver.parameters.linearization_level = int(linearization_level)
    solver.parameters.cp_model_presolve = bool(cp_model_presolve)
    solver.parameters.optimize_with_core = bool(optimize_with_core)
    solver.parameters.use_lns_only = bool(use_lns_only)
    # CP-SAT exposes the SearchBranching enum as integer constants on the
    # SatParameters message (accessible via `solver.parameters.<NAME>`).
    # Unknown strings fall back to AUTOMATIC_SEARCH so a typo can't wedge
    # a batch.
    _branching_keys = {
        "AUTOMATIC", "AUTOMATIC_SEARCH",
        "FIXED", "FIXED_SEARCH",
        "PORTFOLIO", "PORTFOLIO_SEARCH",
        "LP", "LP_SEARCH",
        "PSEUDO_COST", "PSEUDO_COST_SEARCH",
        "PORTFOLIO_WITH_QUICK_RESTART", "PORTFOLIO_WITH_QUICK_RESTART_SEARCH",
        "HINT", "HINT_SEARCH",
        "PARTIAL_FIXED", "PARTIAL_FIXED_SEARCH",
        "RANDOMIZED", "RANDOMIZED_SEARCH",
    }
    branching_key = str(search_branching).upper().strip()
    if branching_key in _branching_keys:
        if not branching_key.endswith("_SEARCH"):
            branching_key = f"{branching_key}_SEARCH"
        solver.parameters.search_branching = getattr(
            solver.parameters, branching_key,
            solver.parameters.AUTOMATIC_SEARCH,
        )
    else:
        solver.parameters.search_branching = solver.parameters.AUTOMATIC_SEARCH

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
        # Phase B: snapshot every type's vars so the WebSocket stream can
        # surface partial assignments per type. The IntermediateLogger
        # walks this dict-of-dicts and emits a flat snapshot.
        snapshot_maps = {"stations": assign}
        for t in inst.on_call_types:
            snapshot_maps[f"oncall_by_type::{t.key}"] = oc_vars[t.key]
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
        oncall_by_type: dict[str, dict[tuple[int, int], int]] = {}
        for t in inst.on_call_types:
            picked = {k: solver.Value(v) for k, v in oc_vars[t.key].items() if solver.Value(v)}
            oncall_by_type[t.key] = picked
        # Phase B canonical: `oncall_by_type` keyed by type_key. Legacy
        # back-compat views `oncall` / `ext` / `wconsult` aggregate across
        # types whose `legacy_role_alias` matches; this lets downstream
        # consumers (assignments_to_rows, fairness, coverage, baselines)
        # keep working with the legacy three keys until they're updated.
        result.assignments = {
            "stations": {k: solver.Value(v) for k, v in assign.items() if solver.Value(v)},
            "oncall_by_type": oncall_by_type,
            "oncall": {},
            "ext": {},
            "wconsult": {},
        }
        for t in inst.on_call_types:
            target = {
                "ONCALL": "oncall",
                "WEEKEND_EXT": "ext",
                "WEEKEND_CONSULT": "wconsult",
            }.get(t.legacy_role_alias or "")
            if target is None:
                continue
            for k, v in oncall_by_type[t.key].items():
                if v:
                    result.assignments[target][k] = v
    return result


def _oncall_weight(
    t: OnCallType,
    day: int,
    inst: Instance,
    w: WorkloadWeights,
) -> int:
    """Per-day workload weight for an on-call type assignment. Maps the
    legacy role aliases to their existing per-role weights so old
    scenarios produce identical S0 contributions; new user-defined types
    fall back to the standard weekday/weekend on-call weights."""
    is_we = inst.is_weekend(day)
    alias = t.legacy_role_alias
    if alias == "WEEKEND_EXT":
        return w.weekend_ext
    if alias == "WEEKEND_CONSULT":
        return w.weekend_consult
    return w.weekend_oncall if is_we else w.weekday_oncall


def _activities_on(
    did: int,
    day: int,
    assign_by_dday: dict[tuple[int, int], list[cp_model.IntVar]],
    oc_vars: dict[str, dict[tuple[int, int], cp_model.IntVar]],
) -> list[cp_model.IntVar]:
    """All vars representing activity for a (doctor, day): station + every
    on-call type the doctor could hold. Used by H5/H9 to force a no-work
    day, and by the day-0 prev_oncall seed."""
    out: list[cp_model.IntVar] = list(assign_by_dday.get((did, day), []))
    for type_map in oc_vars.values():
        v = type_map.get((did, day))
        if v is not None:
            out.append(v)
    return out


def _exact_one(model: cp_model.CpModel, vars_: list[cp_model.IntVar]) -> None:
    if not vars_:
        model.Add(1 == 0)
    else:
        model.Add(sum(vars_) == 1)


# =========================================================================
# Model-level tuning helpers — toggled via `solve(symmetry_break=..., etc.)`.
# Each one is additive: it does not change the set of feasible solutions,
# only how CP-SAT searches for them.
# =========================================================================

def _doctor_signature(
    doctor,
    inst: Instance,
) -> tuple:
    """Produce a hashable 'interchangeability signature' for a doctor.

    Two doctors with the same signature are literally identical from the
    solver's point of view: same tier, eligibility, FTE, on-call cap,
    prior-workload carry-in, leave pattern, per-day blocks, and
    preferences. We can safely require a lex-order between them without
    excluding any optimal solution — any "swapped" solution has a valid
    representative in which the ordered pair is satisfied.
    """
    return (
        doctor.tier,
        tuple(sorted(doctor.eligible_stations)),
        tuple(sorted(doctor.eligible_oncall_types)),
        float(doctor.fte),
        -1 if doctor.max_oncalls is None else int(doctor.max_oncalls),
        int(inst.prev_workload.get(doctor.id, 0)),
        tuple(sorted(inst.leave.get(doctor.id, set()))),
        tuple(sorted(inst.no_oncall.get(doctor.id, set()))),
        tuple(sorted(
            (day, tuple(sorted(sess)))
            for day, sess in inst.no_session.get(doctor.id, {}).items()
        )),
        tuple(sorted(
            (day, tuple(sorted(sess)))
            for day, sess in inst.prefer_session.get(doctor.id, {}).items()
        )),
    )


def _apply_symmetry_break(
    model: cp_model.CpModel,
    inst: Instance,
    by_doc_oncall: dict[int, list[cp_model.IntVar]],
    by_doc_assign: dict[int, list[cp_model.IntVar]],
    by_doc_weekend: dict[int, list[cp_model.IntVar]],
) -> None:
    """Kill doctor-level symmetry by ordering interchangeable peers.

    Phase B: collapses the legacy four-counter lex key (oncall, station,
    ext, wconsult) into three counters (oncall-total across types,
    station, weekend-role-total). Behaviour is the same — interchangeable
    doctors get a stable lex order — but the counters are computed off
    the generic per-type aggregators.
    """
    from collections import defaultdict as _defaultdict

    groups: dict[tuple, list] = _defaultdict(list)
    for doctor in inst.doctors:
        is_overridden = any(o[0] == doctor.id for o in inst.overrides)
        if is_overridden:
            continue
        groups[_doctor_signature(doctor, inst)].append(doctor)

    # Lex-key weights. weekend ≤ 2 * len(types) per doctor (each type can
    # fire at most once per weekend day; we cap with a generous bound).
    max_weekend_plus_one = 2 * inst.n_days + 1
    w_we = 1
    w_st = max_weekend_plus_one
    max_st_plus_one = 2 * inst.n_days + 1
    w_oc = w_st * max_st_plus_one

    for members in groups.values():
        if len(members) < 2:
            continue
        members_sorted = sorted(members, key=lambda d: d.id)
        for a, b in zip(members_sorted[:-1], members_sorted[1:]):
            key_a = (
                w_oc * sum(by_doc_oncall.get(a.id, []) or [0])
                + w_st * sum(by_doc_assign.get(a.id, []) or [0])
                + w_we * sum(by_doc_weekend.get(a.id, []) or [0])
            )
            key_b = (
                w_oc * sum(by_doc_oncall.get(b.id, []) or [0])
                + w_st * sum(by_doc_assign.get(b.id, []) or [0])
                + w_we * sum(by_doc_weekend.get(b.id, []) or [0])
            )
            has_any = (
                by_doc_oncall.get(a.id) or by_doc_oncall.get(b.id)
                or by_doc_assign.get(a.id) or by_doc_assign.get(b.id)
                or by_doc_weekend.get(a.id) or by_doc_weekend.get(b.id)
            )
            if has_any:
                model.Add(key_a >= key_b)


def _apply_redundant_aggregates(
    model: cp_model.CpModel,
    inst: Instance,
    by_doc_oncall: dict[int, list[cp_model.IntVar]],
) -> None:
    """Add redundant tier-level aggregate lower bounds.

    Phase B: each on-call type's `daily_required` × number-of-active-days
    pins a lower bound on total assignments of that type. Sum across
    types — restricted to types whose `eligible_tiers` includes a given
    tier — gives a per-tier floor. Materialising it as a single sum
    yields a tighter LP dual bound for CP-SAT.
    """
    floor_per_tier: dict[str, int] = {}
    for t in inst.on_call_types:
        if t.daily_required <= 0:
            continue
        # Count days where the type is active.
        active_days = 0
        for day in range(inst.n_days):
            wd = inst.weekday_of(day)
            if wd in t.days_active:
                active_days += 1
            elif day in inst.public_holidays and (5 in t.days_active or 6 in t.days_active):
                active_days += 1
        type_floor = active_days * t.daily_required
        if type_floor <= 0:
            continue
        for tier in t.eligible_tiers:
            floor_per_tier[tier] = floor_per_tier.get(tier, 0) + type_floor

    for tier, floor_demand in floor_per_tier.items():
        if floor_demand <= 0:
            continue
        tier_vars: list[cp_model.IntVar] = []
        for d in inst.doctors:
            if d.tier != tier:
                continue
            tier_vars.extend(by_doc_oncall.get(d.id, []))
        if not tier_vars:
            continue
        model.Add(sum(tier_vars) >= floor_demand)


def _apply_decision_strategy(
    model: cp_model.CpModel,
    strategy: str,
    oncall: dict[tuple[int, int], cp_model.IntVar],
    assign: dict[tuple[int, int, str, str], cp_model.IntVar],
) -> None:
    """Tell CP-SAT which variables to branch on first.

    CP-SAT's default decision strategy is automatic (pseudo-cost based).
    For rostering problems the on-call variables are usually the best
    first-branch targets: committing to an on-call forces the same-day
    post-call off via H5 and bans on-calls on the ±N surrounding days
    via H4, propagating rapidly to the rest of the schedule.
    """
    strategy = strategy.lower()
    if strategy == "oncall_first":
        oncall_vars = list(oncall.values())
        if oncall_vars:
            model.AddDecisionStrategy(
                oncall_vars,
                cp_model.CHOOSE_FIRST,
                cp_model.SELECT_MIN_VALUE,
            )
    elif strategy == "station_first":
        station_vars = list(assign.values())
        if station_vars:
            model.AddDecisionStrategy(
                station_vars,
                cp_model.CHOOSE_FIRST,
                cp_model.SELECT_MAX_VALUE,
            )
    # "default" / unknown strategies fall through — CP-SAT's automatic
    # var selection stays in effect.
