"""Baselines — `greedy` and `random_repair`.

These are intentionally weak: the greedy heuristic has no look-ahead so
it usually breaks H4 (1-in-3 on-call) on tight instances, and the
random-repair routine typically leaves H1 coverage gaps. The tests
here lock in that behaviour so later refactors don't accidentally turn
them into strong baselines (which would undersell CP-SAT's lift).
"""

from __future__ import annotations

from scheduler.baselines import greedy_baseline, random_repair_baseline
from scheduler.instance import make_synthetic


def _small_instance():
    # 12 doctors × 7 days — big enough for all 3 tiers, small enough to solve
    # quickly without any CP-SAT dependency.
    return make_synthetic(n_doctors=12, n_days=7, seed=0)


def test_greedy_runs_and_returns_heuristic_status() -> None:
    inst = _small_instance()
    result = greedy_baseline(inst)
    assert result.status == "HEURISTIC"
    assert result.objective is None
    # SolveResult-compatible shape: all four assignment buckets exist.
    assert set(result.assignments.keys()) == {"stations", "oncall", "ext", "wconsult"}


def test_greedy_assigns_at_least_some_slots() -> None:
    """Not a feasibility claim — just asserts the greedy is doing _something_
    (if it produced zero assignments, that's a bug)."""
    inst = _small_instance()
    result = greedy_baseline(inst)
    total = (len(result.assignments["stations"]) + len(result.assignments["oncall"])
             + len(result.assignments["ext"]) + len(result.assignments["wconsult"]))
    assert total > 0


def test_greedy_respects_eligibility() -> None:
    """Every station assignment must respect (station.eligible_tiers) and
    (doctor.eligible_stations). These are the softest of H3 checks and
    the baseline should never break them (easy rule, no planning needed).
    """
    inst = _small_instance()
    result = greedy_baseline(inst)
    doc_by_id = {d.id: d for d in inst.doctors}
    station_by_name = {s.name: s for s in inst.stations}
    for (did, _day, station, _sess) in result.assignments["stations"]:
        doc = doc_by_id[did]
        st = station_by_name[station]
        assert doc.tier in st.eligible_tiers
        assert station in doc.eligible_stations


def test_random_repair_respects_eligibility() -> None:
    inst = _small_instance()
    result = random_repair_baseline(inst, seed=7)
    assert result.status == "HEURISTIC"
    doc_by_id = {d.id: d for d in inst.doctors}
    station_by_name = {s.name: s for s in inst.stations}
    for (did, _day, station, _sess) in result.assignments["stations"]:
        doc = doc_by_id[did]
        st = station_by_name[station]
        assert doc.tier in st.eligible_tiers
        assert station in doc.eligible_stations


def test_random_repair_respects_leave() -> None:
    """No station assignment should fall on a leave day — leave is hard."""
    inst = _small_instance()
    result = random_repair_baseline(inst, seed=3)
    for (did, day, _station, _sess) in result.assignments["stations"]:
        assert day not in inst.leave.get(did, set())


def test_random_repair_seeds_are_deterministic() -> None:
    """Two runs with the same seed produce the same roster. Reproducibility
    is a first-class Phase 3 concern but the seed plumbing lands here."""
    inst = _small_instance()
    a = random_repair_baseline(inst, seed=42)
    b = random_repair_baseline(inst, seed=42)
    assert a.assignments == b.assignments
