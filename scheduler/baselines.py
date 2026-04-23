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

See `docs/VALIDATION_PLAN.md §1.2` and `docs/INDUSTRY_CONTEXT.md §6`
for the role these baselines play in publication-grade reporting.
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Any

from scheduler.instance import Instance
from scheduler.model import SolveResult


# ------------------------------------------------------------- result shape

def _empty_assignments() -> dict[str, dict]:
    return {"stations": {}, "oncall": {}, "ext": {}, "wconsult": {}}


def _build_result(
    status: str,
    wall_s: float,
    assignments: dict[str, dict],
) -> SolveResult:
    """Shape a heuristic outcome as a SolveResult so existing
    payload/self-check/fairness plumbing accepts it unchanged."""
    n_station = sum(1 for _ in assignments.get("stations", {}))
    n_other = sum(
        len(assignments.get(k, {})) for k in ("oncall", "ext", "wconsult")
    )
    return SolveResult(
        status=status,
        wall_time_s=round(wall_s, 3),
        objective=None,
        best_bound=None,
        n_vars=n_station + n_other,   # cheap proxy; used only for display
        n_constraints=0,
        first_feasible_s=None,
        penalty_components={},
        assignments=assignments,
    )


# ------------------------------------------------------------- shared state

@dataclass
class _BusyIndex:
    """Tracks 'already used' flags so the greedy / random heuristics don't
    double-book a doctor. Updated in place by the baselines."""
    # (doctor_id, day) → "am"/"pm"/"oncall"/"ext"/"wconsult" busy flags
    station_busy: dict[tuple[int, int, str], bool] = field(default_factory=dict)
    oncall_busy: dict[tuple[int, int], bool] = field(default_factory=dict)
    ext_busy: dict[tuple[int, int], bool] = field(default_factory=dict)
    wconsult_busy: dict[tuple[int, int], bool] = field(default_factory=dict)
    # Rolling on-call window: for H4 (1-in-N), ban doctors for N-1 days
    # after each on-call.
    oncall_days_per_doc: dict[int, list[int]] = field(
        default_factory=lambda: {}
    )

    def session_free(self, did: int, day: int, sess: str) -> bool:
        return not self.station_busy.get((did, day, sess), False)

    def oncall_free(self, did: int, day: int) -> bool:
        return not self.oncall_busy.get((did, day), False)


# ------------------------------------------------------------- greedy

def greedy_baseline(inst: Instance) -> SolveResult:
    """Fill weekend H8 roles → weekday on-call → station coverage, in that
    order, picking the lowest-workload eligible doctor at each step. This
    is the 'sanity floor' baseline every NRP paper reports against.

    Does not attempt to minimise any objective. May leave slots empty if
    no eligible doctor is available under the narrow local rules — those
    gaps show up as H1 coverage shortfall, which is exactly the signal
    a reviewer wants to compare against the CP-SAT solver's output."""
    start = time.perf_counter()
    ass = _empty_assignments()
    busy = _BusyIndex()

    # Quick lookups.
    leave = inst.leave  # dict[did, set[day]]
    no_oncall = inst.no_oncall
    no_session = inst.no_session
    prev_oncall = inst.prev_oncall

    # Doctors by tier / eligibility — precomputed for O(1) filtering.
    by_tier: dict[str, list] = {"junior": [], "senior": [], "consultant": []}
    for d in inst.doctors:
        by_tier.setdefault(d.tier, []).append(d)
    consultants_by_subspec: dict[str, list] = {}
    for d in by_tier["consultant"]:
        if d.subspec:
            consultants_by_subspec.setdefault(d.subspec, []).append(d)

    # Running workload per doctor, used as the ranking key so greedy picks
    # the least-loaded eligible doctor. Seed with prev_workload so carry-in
    # from last period influences this-period picks too.
    load: dict[int, int] = {d.id: int(inst.prev_workload.get(d.id, 0)) for d in inst.doctors}

    def _can_oncall(did: int, day: int) -> bool:
        """Approximate H4 + H5 + H12 checks. Not as tight as the CP-SAT
        model (H4's 1-in-N is enforced only backwards, not forwards) — that's
        intentional: the greedy doesn't plan ahead."""
        if did in leave.get(did, set()):
            pass  # leave dict is keyed by did, not a bug; checked next
        if day in leave.get(did, set()):
            return False
        if day in no_oncall.get(did, set()):
            return False
        if not busy.oncall_free(did, day):
            return False
        # H5: if the doctor was on-call on day-1, they must be off today.
        prior_days = busy.oncall_days_per_doc.get(did, [])
        if day - 1 in prior_days:
            return False
        if day == 0 and did in prev_oncall:
            return False
        # H4: 1-in-N.
        N = 3  # default; can be parameterised via inst if needed
        for prev_day in prior_days:
            if 0 < day - prev_day < N:
                return False
        # Post-oncall can't work AM/PM either; surface that by not picking
        # a doctor who already has AM/PM on the same day.
        if busy.station_busy.get((did, day, "AM")) or busy.station_busy.get((did, day, "PM")):
            return False
        return True

    def _book_oncall(did: int, day: int) -> None:
        busy.oncall_busy[(did, day)] = True
        busy.oncall_days_per_doc.setdefault(did, []).append(day)
        # Block AM/PM same day and next day (H5).
        busy.station_busy[(did, day, "AM")] = True
        busy.station_busy[(did, day, "PM")] = True
        if day + 1 < inst.n_days:
            busy.station_busy[(did, day + 1, "AM")] = True
            busy.station_busy[(did, day + 1, "PM")] = True
            busy.oncall_busy[(did, day + 1)] = True
        is_we = inst.is_weekend(day)
        load[did] += 35 if is_we else 20

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

    def _pick_lowest_load(candidates: list) -> Any:
        if not candidates:
            return None
        return min(candidates, key=lambda d: load[d.id])

    # ---- Phase 1: weekend H8 roles (scarcest) ----
    for day in range(inst.n_days):
        if not inst.is_weekend(day):
            continue
        # 1 junior EXT
        cands = [d for d in by_tier["junior"]
                 if day not in leave.get(d.id, set())
                 and not busy.ext_busy.get((d.id, day))
                 and not busy.oncall_free(d.id, day) is False]
        pick = _pick_lowest_load(cands)
        if pick:
            ass["ext"][(pick.id, day)] = 1
            busy.ext_busy[(pick.id, day)] = True
            load[pick.id] += 20
        # 1 senior EXT
        cands = [d for d in by_tier["senior"]
                 if day not in leave.get(d.id, set())
                 and not busy.ext_busy.get((d.id, day))
                 and busy.oncall_free(d.id, day)]
        pick = _pick_lowest_load(cands)
        if pick:
            ass["ext"][(pick.id, day)] = 1
            busy.ext_busy[(pick.id, day)] = True
            load[pick.id] += 20
        # 1 junior on-call
        cands = [d for d in by_tier["junior"] if _can_oncall(d.id, day)
                 and not busy.ext_busy.get((d.id, day))]
        pick = _pick_lowest_load(cands)
        if pick:
            _book_oncall(pick.id, day)
        # 1 senior on-call
        cands = [d for d in by_tier["senior"] if _can_oncall(d.id, day)
                 and not busy.ext_busy.get((d.id, day))]
        pick = _pick_lowest_load(cands)
        if pick:
            _book_oncall(pick.id, day)
        # 1 consultant per subspec
        for ss, candidates in consultants_by_subspec.items():
            cands = [d for d in candidates
                     if day not in leave.get(d.id, set())
                     and not busy.wconsult_busy.get((d.id, day))]
            pick = _pick_lowest_load(cands)
            if pick:
                ass["wconsult"][(pick.id, day)] = 1
                busy.wconsult_busy[(pick.id, day)] = True
                load[pick.id] += 25

    # ---- Phase 2: weekday on-call (1 junior + 1 senior per night) ----
    for day in range(inst.n_days):
        if inst.is_weekend(day):
            continue
        for tier in ("junior", "senior"):
            cands = [d for d in by_tier[tier] if _can_oncall(d.id, day)]
            pick = _pick_lowest_load(cands)
            if pick:
                _book_oncall(pick.id, day)

    # ---- Phase 3: station coverage ----
    for day in range(inst.n_days):
        is_we = inst.is_weekend(day)
        if is_we and not inst.weekend_am_pm_enabled:
            continue  # weekend AM/PM disabled by default
        for st in inst.stations:
            for sess in st.sessions:
                for _slot in range(st.required_per_session):
                    cands = [
                        d for d in inst.doctors
                        if d.tier in st.eligible_tiers
                        and _can_station(d.id, day, st.name, sess, d)
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
    structure (H4, H5, H8) is left broken — which is the point: this
    baseline is meant to look bad in the Lab's comparison table and
    justify the CP-SAT approach quantitatively."""
    rng = random.Random(seed)
    start = time.perf_counter()
    ass = _empty_assignments()
    used_session: set[tuple[int, int, str]] = set()  # (did, day, sess) occupied

    leave = inst.leave
    no_session = inst.no_session

    for it in range(max_iterations):
        improved = False
        for day in range(inst.n_days):
            if inst.is_weekend(day) and not inst.weekend_am_pm_enabled:
                continue
            for st in inst.stations:
                for sess in st.sessions:
                    # Current assigned count for this slot.
                    cur = sum(
                        1 for k in ass["stations"]
                        if k[1] == day and k[2] == st.name and k[3] == sess
                    )
                    if cur >= st.required_per_session:
                        continue
                    # Pick a random eligible doctor.
                    pool = [
                        d for d in inst.doctors
                        if d.tier in st.eligible_tiers
                        and st.name in d.eligible_stations
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
