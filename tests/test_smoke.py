"""Smoke tests: 10 doctors × 7 days, default settings, must find a solution."""

from scheduler.instance import make_synthetic
from scheduler.model import solve


def test_tiny_feasible():
    inst = make_synthetic(n_doctors=12, n_days=7, seed=0)
    res = solve(inst, time_limit_s=30, feasibility_only=True)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.status


def test_tiny_optimize():
    inst = make_synthetic(n_doctors=12, n_days=7, seed=1)
    res = solve(inst, time_limit_s=30)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.status
    assert res.objective is not None


def test_respects_leave():
    inst = make_synthetic(n_doctors=12, n_days=7, seed=2)
    # Force doctor 0 off on day 0.
    inst.leave.setdefault(0, set()).add(0)
    res = solve(inst, time_limit_s=30, feasibility_only=True)
    assert res.status in ("OPTIMAL", "FEASIBLE"), res.status
    for key in res.assignments["stations"]:
        did, day, _, _ = key
        if did == 0:
            assert day != 0, f"doctor 0 assigned on leave day: {key}"


if __name__ == "__main__":
    test_tiny_feasible()
    test_tiny_optimize()
    test_respects_leave()
    print("OK")
