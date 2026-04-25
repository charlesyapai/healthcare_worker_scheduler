"""Heuristic baselines for the rostering problem.

Neither baseline is an optimisation method — both exist so the Lab tab
can report "our CP-SAT solver beats greedy by X%, beats random-repair
by Y%" on a given instance. The greedy floor is the mandatory benchmark
in INRC-II-style NRP papers; the random-repair baseline stresses the
constraint structure (many random drafts violate H1/H3 out of the box).

Both return a `SolveResult`-compatible dataclass so downstream code
(solve_result_to_payload, the self-check, fairness metrics) can consume
them identically to a CP-SAT solve. `status="HEURISTIC"`, `objective=None`
(the baselines don't minimise our objective). Feasibility is NOT
guaranteed — the point of the baseline is to measure how often naïve
approaches fail, and by how much.

Phase B: greedy iterates `inst.on_call_types` instead of the hard-coded
oncall/ext/wconsult triple. Each type's `daily_required` worth of slots
is filled per active day with the lowest-loaded eligible doctor,
respecting per-type frequency_cap_days and next_day_off as best-effort.

See `docs/VALIDATION_PLAN.md §1.2` and `docs/INDUSTRY_CONTEXT.md §6`
for the role these baselines play in publication-grade reporting.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from scheduler.instance import Instance, OnCallType
from scheduler.model import SolveResult


# ------------------------------------------------------------- result shape

def _empty_assignments(types: list[OnCallType]) -> dict[str, dict]:
    out: dict[str, Any] = {
        "stations": {},
        "oncall_by_type": {t.key: {} for t in types},
        # Back-compat aggregate views — populated as we book per-type.
        "oncall": {},
        "ext": {},
        "wconsult": {},
    }
    return out


def _build_result(
    status: str,
    wall_s: float,
    assignments: dict[str, dict],
) -> SolveResult:
    """Shape a heuristic outcome as a SolveResult so existing
    payload/self-check/fairness plumbing accepts it unchanged."""
    n_station = sum(1 for _ in assignments.get("stations", {}))
    n_oc = sum(
        len(v) for v in (assignments.get("oncall_by_type") or {}).values()
    )
    return SolveResult(
        status=status,
        wall_time_s=round(wall_s, 6),
        objective=None,
        best_bound=None,
        n_vars=n_station + n_oc,
        n_constraints=0,
        first_feasible_s=None,
        penalty_components={},
        assignments=assignments,
    )


# ------------------------------------------------------------- shared state

@dataclass
class _BusyIndex:
    """Tracks 'already used' flags so the greedy / random heuristics don't
    double-book a doctor."""
    station_busy: dict[tuple[int, int, str], bool] = field(default_factory=dict)
    # (doctor, day) → set of on-call type keys booked.
    oncall_types_busy: dict[tuple[int, int], set[str]] = field(default_factory=dict)
    # Per (doctor, type) → list of days the doctor was on that type.
    oncall_days_per_doc_type: dict[tuple[int, str], list[int]] = field(
        default_factory=dict
    )

    def session_free(self, did: int, day: int, sess: str) -> bool:
        return not self.station_busy.get((did, day, sess), False)

    def has_oncall(self, did: int, day: int) -> bool:
        return bool(self.oncall_types_busy.get((did, day)))


def _day_active_for_type(day: int, t: OnCallType, inst: Instance) -> bool:
    wd = inst.weekday_of(day)
    if wd in t.days_active:
        return True
    if day in inst.public_holidays and (5 in t.days_active or 6 in t.days_active):
        return True
    return False


# ------------------------------------------------------------- greedy

def greedy_baseline(inst: Instance) -> SolveResult:
    """Fill on-call types (heaviest first) → station coverage. Picks the
    lowest-workload eligible doctor at each step. May leave slots empty
    if no eligible doctor is available; gaps surface as H1 / per-type
    coverage shortfall in the post-solve audit, which is the point of the
    baseline."""
    start = time.perf_counter()
    ass = _empty_assignments(inst.on_call_types)
    busy = _BusyIndex()

    leave = inst.leave
    no_session = inst.no_session
    no_oncall = inst.no_oncall
    prev_oncall = inst.prev_oncall

    load: dict[int, int] = {
        d.id: int(inst.prev_workload.get(d.id, 0)) for d in inst.doctors
    }

    def _pick_lowest_load(candidates: list) -> Any:
        if not candidates:
            return None
        return min(candidates, key=lambda d: load[d.id])

    def _can_oncall_for(t: OnCallType, did: int, day: int) -> bool:
        if day in leave.get(did, set()):
            return False
        if day in no_oncall.get(did, set()):
            return False
        if (did, day) in busy.oncall_types_busy:
            return False  # mutual exclusion: 1 type per (doctor, day)
        # Approximate H5 (next-day-off): if any prior type with next_day_off
        # was on yesterday, doctor is post-call today.
        for other in inst.on_call_types:
            if not other.next_day_off:
                continue
            prior = busy.oncall_days_per_doc_type.get((did, other.key), [])
            if day - 1 in prior:
                return False
        if day == 0 and did in prev_oncall and t.next_day_off:
            return False
        # Approximate H4 (frequency cap).
        N = t.frequency_cap_days
        if N is not None and N >= 2:
            prior = busy.oncall_days_per_doc_type.get((did, t.key), [])
            for prev_day in prior:
                if 0 < day - prev_day < N:
                    return False
        # Don't pick a doctor already booked for AM/PM that day if the
        # type's `works_full_day` (no station work) or `works_pm_only`
        # (AM=0). Simple guard: if any session today is busy, skip.
        if t.works_full_day or t.works_pm_only:
            if (busy.station_busy.get((did, day, "AM"))
                    or busy.station_busy.get((did, day, "PM"))):
                return False
        return True

    def _book_oncall(t: OnCallType, did: int, day: int) -> None:
        ass["oncall_by_type"].setdefault(t.key, {})[(did, day)] = 1
        # Back-compat aggregate views.
        if t.legacy_role_alias == "ONCALL":
            ass["oncall"][(did, day)] = 1
        elif t.legacy_role_alias == "WEEKEND_EXT":
            ass["ext"][(did, day)] = 1
        elif t.legacy_role_alias == "WEEKEND_CONSULT":
            ass["wconsult"][(did, day)] = 1
        busy.oncall_types_busy.setdefault((did, day), set()).add(t.key)
        busy.oncall_days_per_doc_type.setdefault((did, t.key), []).append(day)
        if t.works_full_day:
            busy.station_busy[(did, day, "AM")] = True
            busy.station_busy[(did, day, "PM")] = True
        elif t.works_pm_only:
            busy.station_busy[(did, day, "AM")] = True
        if t.next_day_off and day + 1 < inst.n_days:
            busy.station_busy[(did, day + 1, "AM")] = True
            busy.station_busy[(did, day + 1, "PM")] = True
        is_we = inst.is_weekend(day)
        if t.legacy_role_alias == "WEEKEND_EXT":
            inc = 20
        elif t.legacy_role_alias == "WEEKEND_CONSULT":
            inc = 25
        else:
            inc = 35 if is_we else 20
        load[did] += inc

    def _can_station(did: int, day: int, station_name: str, sess: str, doc) -> bool:
        if day in leave.get(did, set()):
            return False
        if station_name not in doc.eligible_stations:
            return False
        if not busy.session_free(did, day, sess):
            return False
        blocked = no_session.get(did, {}).get(day, set())
        if sess in blocked:
            return False
        return True

    def _book_station(did: int, day: int, station_name: str, sess: str) -> None:
        ass["stations"][(did, day, station_name, sess)] = 1
        busy.station_busy[(did, day, sess)] = True
        is_we = inst.is_weekend(day)
        load[did] += 15 if is_we else 10

    # ---- Phase 1: weekend-role types first (scarcest), then nights, then
    # any remaining user-defined types. Within each phase, fill in
    # daily_required order (heaviest demand first) so headcount-tight
    # types don't get starved by lower-priority ones.
    weekend_first = sorted(
        inst.on_call_types,
        key=lambda t: (
            0 if t.counts_as_weekend_role else 1,
            -t.daily_required,
        ),
    )
    for t in weekend_first:
        if t.daily_required <= 0:
            continue
        for day in range(inst.n_days):
            if not _day_active_for_type(day, t, inst):
                continue
            for _slot in range(t.daily_required):
                cands = [
                    d for d in inst.doctors
                    if t.key in d.eligible_oncall_types
                    and _can_oncall_for(t, d.id, day)
                ]
                pick = _pick_lowest_load(cands)
                if pick:
                    _book_oncall(t, pick.id, day)

    # ---- Phase 2: station coverage.
    for day in range(inst.n_days):
        is_we = inst.is_weekend(day)
        for st in inst.stations:
            if is_we and not st.weekend_enabled:
                continue
            if not is_we and not st.weekday_enabled:
                continue
            for sess in st.sessions:
                for _slot in range(st.required_per_session):
                    cands = [
                        d for d in inst.doctors
                        if _can_station(d.id, day, st.name, sess, d)
                    ]
                    pick = _pick_lowest_load(cands)
                    if pick:
                        _book_station(pick.id, day, st.name, sess)

    return _build_result("HEURISTIC", time.perf_counter() - start, ass)


# ------------------------------------------------------------- random-repair

def random_repair_baseline(
    inst: Instance,
    *,
    seed: int = 0,
    max_iterations: int = 500,
) -> SolveResult:
    """Randomise, then repair coverage gaps. Represents 'no planning at all,
    just shuffle people into slots until something sticks'. Stops when
    no improvement is made for a full pass or `max_iterations` hit.

    The repair phase only tries to satisfy H1 + H3 + H10. Higher-level
    structure (H4, H5, per-type daily_required) is left broken — which is
    the point: this baseline is meant to look bad in the Lab's comparison
    table and justify the CP-SAT approach quantitatively."""
    rng = random.Random(seed)
    start = time.perf_counter()
    ass = _empty_assignments(inst.on_call_types)
    used_session: set[tuple[int, int, str]] = set()

    leave = inst.leave
    no_session = inst.no_session

    for _it in range(max_iterations):
        improved = False
        for day in range(inst.n_days):
            is_we = inst.is_weekend(day)
            for st in inst.stations:
                if is_we and not st.weekend_enabled:
                    continue
                if not is_we and not st.weekday_enabled:
                    continue
                for sess in st.sessions:
                    cur = sum(
                        1 for k in ass["stations"]
                        if k[1] == day and k[2] == st.name and k[3] == sess
                    )
                    if cur >= st.required_per_session:
                        continue
                    pool = [
                        d for d in inst.doctors
                        if st.name in d.eligible_stations
                        and day not in leave.get(d.id, set())
                        and (d.id, day, sess) not in used_session
                        and sess not in no_session.get(d.id, {}).get(day, set())
                    ]
                    if not pool:
                        continue
                    pick = rng.choice(pool)
                    ass["stations"][(pick.id, day, st.name, sess)] = 1
                    used_session.add((pick.id, day, sess))
                    improved = True
        if not improved:
            break

    return _build_result("HEURISTIC", time.perf_counter() - start, ass)
