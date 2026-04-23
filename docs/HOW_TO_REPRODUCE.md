# How to reproduce a Lab benchmark

This guide walks a reviewer from a downloaded bundle ZIP to a clean
replay verdict (zero divergences). It is the operational counterpart to
[`VALIDATION_PLAN.md §1.3`](VALIDATION_PLAN.md) — the "solutions are
reproducible" pillar.

## What a bundle contains

When a Lab user clicks **Download bundle** on
[`/lab/benchmark`](LAB_TAB_SPEC.md), the server returns a ZIP:

| File | Purpose |
|---|---|
| `state.yaml` | Session state — doctors, stations, weights, constraints, horizon. |
| `run_config.json` | Exact CP-SAT parameters used: `random_seed`, `search_branching`, `linearization_level`, `cp_model_presolve`, `optimize_with_core`, `use_lns_only`, `num_workers`, `time_limit_s`, `feasibility_only`. |
| `results.json` | The `BatchSummary` we are claiming + every `SingleRunDetail` (coverage + fairness + self-check). |
| `git_sha.txt` | Code revision used. Matches `GET /api/health`'s `git_sha`. |
| `requirements.txt` | Frozen Python runtime deps. |
| `README.md` | Abridged replay walkthrough, SHA-stamped. |

## Replay walkthrough

```bash
# 1. Check out the exact code revision the bundle was produced from.
git clone https://github.com/charlesyapai/healthcare_worker_scheduler.git
cd healthcare_worker_scheduler
git checkout <sha from git_sha.txt>

# 2. Fresh Python environment.
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 3. Replay.
python scripts/replay_bundle.py path/to/bundle.zip
```

A clean run prints:

```
[replay] bundle: lab_bundle_<id>.zip
[replay] N expected run(s)
[replay] git_sha (recorded): <sha>
[replay] OK — all N runs reproduce.
```

A divergent run prints a list of `(solver, seed).<field>` mismatches
with expected vs actual values and exits non-zero. Common causes:

| Mismatch | Likely cause |
|---|---|
| `objective` | `num_workers > 1` (CP-SAT portfolio is non-deterministic) or different git SHA. |
| `self_check_ok` | Validator or model changed between capture and replay. Check `api/validator.py` + `scheduler/model.py`. |
| `coverage_shortfall` | Same as above — one of the two diverged from `docs/CONSTRAINTS.md`. |

## Determinism guarantees

- With `num_workers=1` + a fixed `random_seed`, two runs of CP-SAT on
  the same instance return identical assignments, objective, and
  coverage metrics. Tested in
  [`tests/test_lab_bundle.py::test_cpsat_deterministic_with_fixed_seed_single_worker`](../tests/test_lab_bundle.py).
- With `num_workers > 1`, CP-SAT's parallel portfolio is **not**
  deterministic even with a fixed seed. This is an OR-Tools property,
  not a bug in our code. For strict replay, always use
  `num_workers = 1`.
- The greedy baseline is deterministic by construction.
- The random-repair baseline is deterministic per seed; two runs with
  the same seed produce identical assignments
  ([`tests/test_baselines.py::test_random_repair_seeds_are_deterministic`](../tests/test_baselines.py)).

## What the replay does NOT verify

- **Byte-for-byte assignment equality.** Multiple optima with
  identical objective / fairness / coverage metrics are valid
  solutions; the replay compares summary stats, not raw variable
  bindings. This mirrors what a reviewer can reasonably audit from a
  published paper.
- **Wall-clock time.** Hardware + concurrent load affect wall time;
  we compare `objective` + `status` + `self_check_ok` +
  `coverage_shortfall` + `coverage_over`, not `wall_time_s`.
- **Cross-platform floating-point stability.** CP-SAT is
  integer-valued, so this is a non-issue for us, but if you see an
  unexpected `objective` mismatch across Linux/macOS, open an issue.

## Verifying a published claim

For a paper that reports a number like "CP-SAT solves radiology_small
to OPTIMAL in X seconds with fairness Gini = 0.07":

1. Ask the authors for the bundle ZIP (or use the one we publish).
2. Run `scripts/replay_bundle.py bundle.zip`.
3. In the output, look for `status=OPTIMAL` and
   `self_check_ok=true` on every cell.
4. Open the Lab tab, load the same state.yaml, rerun the batch with
   identical RunConfig, and inspect the fairness payload on
   [`/lab/fairness`](LAB_TAB_SPEC.md).

A green replay plus a matching fairness payload is the whole chain
of evidence.
