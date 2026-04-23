"""End-to-end benchmark runner tests.

Exercises the full Phase 2 chain:
  POST /api/state/scenarios/{id}
  POST /api/lab/run              — cross-product of solvers × seeds
  GET  /api/lab/runs             — history list
  GET  /api/lab/runs/{batch_id}  — full detail

The point of these tests is to verify the industry-reliability metrics
from `docs/INDUSTRY_CONTEXT.md §3` are actually computed and exposed,
not just documented:

  - feasibility_rate per method  (§7.3)
  - quality_ratios Q = Z_baseline / Z_cpsat  (§7.1)
  - coverage_shortfall per run   (§5.1b)
  - self_check_ok per run        (validator-in-the-loop, Phase 1)
"""

from __future__ import annotations

import pytest

from api.lab.batch import reset_store


@pytest.fixture(autouse=True)
def _clear_batch_store():
    reset_store()
    yield
    reset_store()


def test_batch_requires_seeded_state(client) -> None:
    r = client.post("/api/lab/run", json={
        "solvers": ["cpsat"],
        "seeds": [0],
        "run_config": {"time_limit_s": 10, "num_workers": 1},
    })
    assert r.status_code == 400, r.text


def test_cpsat_vs_greedy_smoke(client) -> None:
    """3 cells: cpsat + 2 greedy seeds. Checks every reliability metric
    the UI will surface — feasibility rate, mean objective, mean
    shortfall, quality ratio."""
    r = client.post("/api/state/scenarios/radiology_small")
    assert r.status_code == 200
    r = client.post("/api/lab/run", json={
        "solvers": ["cpsat", "greedy"],
        "seeds": [0, 1],
        "run_config": {
            "time_limit_s": 15,
            "num_workers": 2,
            "random_seed": 0,
            "feasibility_only": False,
        },
    })
    assert r.status_code == 200, r.text
    summary = r.json()
    # Structure sanity.
    assert summary["n_doctors"] == 15
    assert len(summary["runs"]) == 4        # 2 solvers × 2 seeds
    solvers_seen = {row["solver"] for row in summary["runs"]}
    assert solvers_seen == {"cpsat", "greedy"}
    # Every run carries the reliability receipts.
    for row in summary["runs"]:
        assert "self_check_ok" in row
        assert "coverage_shortfall" in row
        assert "coverage_over" in row
    # Feasibility rate dict populated per solver.
    assert "feasibility_rate" in summary
    assert "cpsat" in summary["feasibility_rate"]
    assert "greedy" in summary["feasibility_rate"]
    # Mean shortfall — CP-SAT must be zero (feasible). Greedy likely > 0.
    assert summary["mean_shortfall"]["cpsat"] == 0
    # CP-SAT should be 100% self-check feasible.
    assert summary["feasibility_rate"]["cpsat"] == 1.0
    # Quality ratio (Z_greedy / Z_cpsat) — only populated when both have
    # an objective. Greedy has no objective, so ratio should be absent.
    assert "cpsat_vs_greedy" not in summary["quality_ratios"]


def test_batch_history_and_detail_endpoints(client) -> None:
    client.post("/api/state/scenarios/radiology_small")
    r = client.post("/api/lab/run", json={
        "solvers": ["greedy"],
        "seeds": [0],
        "run_config": {"time_limit_s": 5, "num_workers": 1},
    })
    assert r.status_code == 200
    batch_id = r.json()["batch_id"]
    # History includes it.
    history = client.get("/api/lab/runs").json()
    assert any(h["batch_id"] == batch_id for h in history)
    # Detail endpoint returns the same batch + per-run payloads.
    r = client.get(f"/api/lab/runs/{batch_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["summary"]["batch_id"] == batch_id
    # Per-run detail carries fairness + coverage payloads.
    run_id = next(iter(body["details"].keys()))
    detail = body["details"][run_id]
    assert "coverage" in detail
    assert "fairness" in detail
    assert "per_tier" in detail["fairness"]


def test_unknown_batch_returns_404(client) -> None:
    r = client.get("/api/lab/runs/does-not-exist")
    assert r.status_code == 404


def test_random_repair_fails_self_check(client) -> None:
    """Sanity-checks the '*** random_repair is intentionally weak ***'
    claim. random_repair only enforces H1/H3/H10 (eligibility + coverage +
    leave); it skips H4 (1-in-N on-call), H5 (post-call off), H8 (weekend
    coverage), and the weekday on-call rule. So on any realistic scenario
    the self-check should land in the red — that's the whole point of
    having a weak baseline to measure CP-SAT's lift against.

    If this flips green in future, either random_repair got suspiciously
    smart or our self-check got laxer; either way, re-examine."""
    client.post("/api/state/scenarios/radiology_small")
    r = client.post("/api/lab/run", json={
        "solvers": ["random_repair"],
        "seeds": [0],
        "run_config": {"time_limit_s": 5, "num_workers": 1},
    })
    assert r.status_code == 200
    run = r.json()["runs"][0]
    assert run["self_check_ok"] is False, (
        "random_repair should not satisfy all hard constraints (it only "
        "targets coverage/eligibility/leave). Got a green self-check — "
        "inspect whether H4/H5/H8 got weakened or the baseline changed."
    )
    assert run["violation_count"] is not None and run["violation_count"] > 0
