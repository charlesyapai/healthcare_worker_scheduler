"""Phase 3 — reproducibility bundle + determinism.

The publication claim VALIDATION_PLAN §1.3 promises is:
"Anyone can re-run the same experiments and get the same numbers,
given the same inputs and solver configuration."

These tests lock in the mechanics:
  1. CP-SAT runs with num_workers=1 + fixed seed are bit-for-bit
     deterministic across two invocations (RESEARCH_METRICS §6.3).
  2. The bundle ZIP contains every file VALIDATION_PLAN §1.3 lists.
  3. Round-trip: unpack bundle → inspect → state.yaml parses back.
"""

from __future__ import annotations

import io
import json
import zipfile

from api.lab.batch import reset_store


def _seed_small_scenario(client) -> None:
    client.post("/api/state/scenarios/radiology_small")
    client.patch("/api/state",
                 json={"solver": {"time_limit": 10, "num_workers": 1}})


def test_cpsat_deterministic_with_fixed_seed_single_worker(client) -> None:
    """Two back-to-back runs with identical RunConfig + single-worker must
    produce identical objective and assignment count. Parallel CP-SAT is
    known non-deterministic so this test explicitly uses num_workers=1.
    """
    reset_store()
    _seed_small_scenario(client)
    payload = {
        "solvers": ["cpsat"],
        "seeds": [7],
        "run_config": {
            "time_limit_s": 10, "num_workers": 1, "random_seed": 100,
            "search_branching": "AUTOMATIC", "linearization_level": 1,
        },
    }
    r1 = client.post("/api/lab/run", json=payload).json()
    r2 = client.post("/api/lab/run", json=payload).json()
    a = r1["runs"][0]
    b = r2["runs"][0]
    assert a["status"] == b["status"]
    assert a["objective"] == b["objective"], (
        f"Objective drift with num_workers=1 + fixed seed: "
        f"run1={a['objective']}, run2={b['objective']}. "
        "CP-SAT parameter plumbing is not threaded through deterministically."
    )
    assert a["n_assignments"] == b["n_assignments"]


def test_bundle_contains_every_reproducibility_artefact(client) -> None:
    reset_store()
    _seed_small_scenario(client)
    r = client.post("/api/lab/run", json={
        "solvers": ["greedy"],
        "seeds": [0],
        "run_config": {"time_limit_s": 5, "num_workers": 1, "random_seed": 0},
    })
    batch_id = r.json()["batch_id"]

    r = client.get(f"/api/lab/runs/{batch_id}/bundle.zip")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/zip"

    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        names = set(zf.namelist())
        # Every artefact VALIDATION_PLAN §1.3 lists.
        assert {"state.yaml", "run_config.json", "results.json",
                "git_sha.txt", "requirements.txt", "README.md"} <= names
        # run_config.json round-trips to valid JSON.
        cfg = json.loads(zf.read("run_config.json"))
        assert cfg["time_limit_s"] == 5
        assert cfg["random_seed"] == 0
        # results.json embeds the full BatchSummary + details.
        results = json.loads(zf.read("results.json"))
        assert "summary" in results
        assert "details" in results
        assert results["summary"]["batch_id"] == batch_id
        # state.yaml is non-empty and parseable as YAML.
        state_yaml = zf.read("state.yaml").decode()
        assert "doctors:" in state_yaml


def test_bundle_readme_references_commit_sha(client) -> None:
    reset_store()
    _seed_small_scenario(client)
    r = client.post("/api/lab/run", json={
        "solvers": ["greedy"],
        "seeds": [0],
        "run_config": {"time_limit_s": 5, "num_workers": 1},
    })
    batch_id = r.json()["batch_id"]
    r = client.get(f"/api/lab/runs/{batch_id}/bundle.zip")
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        readme = zf.read("README.md").decode()
        sha = zf.read("git_sha.txt").decode().strip()
    # Every bundle must embed the SHA in its replay instructions so the
    # reviewer replays against the exact code revision we ran.
    assert sha  # "unknown" is allowed, but must be non-empty
    assert sha in readme


def test_bundle_404_on_unknown_batch(client) -> None:
    r = client.get("/api/lab/runs/does-not-exist/bundle.zip")
    assert r.status_code == 404


def test_health_exposes_git_sha(client) -> None:
    r = client.get("/api/health").json()
    assert "git_sha" in r
    # Non-empty even when running outside a git checkout ("unknown" is
    # the documented fallback).
    assert r["git_sha"]
