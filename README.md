# Healthcare Worker Scheduler

CP-SAT based roster generator for a radiology department. Phase 1 of the
project: **measure how long CP-SAT takes** across realistic problem sizes, so
we can decide whether a downstream ML-predictor layer is actually needed.

## Start here

- `docs/CONTEXT.md` — what this project is and how to pick it up.
- `docs/CONSTRAINTS.md` — the authoritative constraint spec (v0.1).
- `docs/CHANGELOG.md` — what changed, when, and why.

## Install

```bash
pip install -r requirements.txt
```

Python 3.10+. No GPU needed.

## Run a smoke test

```bash
python -m scheduler.benchmark --smoke
```

10 doctors × 7 days, ≤ 30 s limit. Should finish in a few seconds and report
`FEASIBLE` or `OPTIMAL`.

## Run the full sweep

```bash
python -m scheduler.benchmark
```

Defaults: doctors ∈ {30, 50, 100, 200} × days ∈ {7, 14, 28}, 300 s per run.
Results land in `results/benchmark_<timestamp>.csv` with columns:

| Column | Meaning |
|---|---|
| `n_doctors` / `n_days` / `seed` | Instance size. |
| `status` | `OPTIMAL`, `FEASIBLE`, `INFEASIBLE`, `UNKNOWN`. |
| `wall_time_s` | Time spent in `solver.Solve`. |
| `objective` / `best_bound` | For optimization runs; gap = `(obj − bound) / obj`. |
| `n_vars` / `n_constraints` | Model size. |

Tighter time limit or larger sweeps:

```bash
python -m scheduler.benchmark --doctors 30 50 --days 28 --time-limit 60
python -m scheduler.benchmark --feasibility-only        # skip objective
python -m scheduler.benchmark --seeds 0 1 2             # average over 3 seeds
```

## Call the solver directly

```python
from scheduler import make_synthetic, solve

inst = make_synthetic(n_doctors=30, n_days=28, seed=0)
res  = solve(inst, time_limit_s=60)
print(res.status, res.wall_time_s, res.objective)
```

## Layout

```
scheduler/
  instance.py      Doctor / Station / Instance + synthetic generator
  model.py         CP-SAT model (H1–H10, S1–S4)
  benchmark.py     Sweep CLI
configs/
  default.yaml     Station list, tier mix, weights
docs/
  CONSTRAINTS.md   The spec
  CONTEXT.md       Handoff notes
  CHANGELOG.md     Change log
tests/
  test_smoke.py    Tiny feasibility + leave test
results/           Benchmark CSVs (gitignored)
```

## Initial benchmark snapshot (8-thread CP-SAT, single seed)

| Doctors | Days | Status   | Wall time | Objective |
|--------:|-----:|----------|----------:|----------:|
| 30      | 28   | OPTIMAL  | 3.98 s    | 40        |
| 50      | 28   | OPTIMAL  | 6.18 s    | 20        |
| 100     | 28   | OPTIMAL  | 9.91 s    | 60        |
| 200     | 28   | FEASIBLE | 120.15 s  | 90        |

Full table and methodology in `docs/CHANGELOG.md`. Headline: CP-SAT alone
is fast enough for the primary 30–100 doctor target. The ML-predictor phase
may not be needed.

## Status

- v0.1 scaffold: complete.
- User sign-off on the 9 gaps in `CONSTRAINTS.md §5`: pending.
- First benchmark pass collected (above).
- Multi-seed sweep + symmetry-breaking tuning for 200+ doctors: open.
- Hugging Face Space / UI: not yet built.
- ML predictor: not started (evidence leans toward "not needed").
