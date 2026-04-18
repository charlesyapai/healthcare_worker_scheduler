# Project Context — Healthcare Worker Scheduler

**Read this first if you are a new agent or a human picking up this project.**

## 1. Goal

Build a roster-generation service for a radiology department (initial user:
CGH-style setup, ~30–50 consultants, expanding toward ~200 pax). The user
inputs doctors, stations, and constraints; the system returns a monthly roster
that satisfies hard constraints and optimizes soft ones.

Deployment target: **Hugging Face Spaces** (or GitHub Pages + a small API).

## 2. Strategy

Two-phase plan:

- **Phase 1 — CP-SAT baseline (this repo, in progress).** Use Google OR-Tools
  CP-SAT to solve the scheduling problem directly. Benchmark solve time across
  problem sizes to find out whether the solver is already fast enough that no
  ML layer is needed.
- **Phase 2 — Optional ML predictor.** If CP-SAT is too slow for interactive
  use, train a model (e.g. a transformer or GNN) on solver-generated rosters
  to predict a seed solution, then let CP-SAT polish it with a warm start or
  a local-search neighbourhood around the prediction. The solver's output
  from Phase 1 becomes the training data for Phase 2 — so Phase 1 is never
  wasted work even if we proceed to ML.

The key open question that Phase 1 answers:
**For N doctors × D days, how long does CP-SAT take to find (a) a feasible
solution, (b) a proved-optimal solution?**

## 3. Where we are right now (v0.1)

- Branch: `claude/healthcare-roster-scheduler-P5QLa`.
- Constraint spec frozen in `docs/CONSTRAINTS.md`, with defaults applied for
  9 open gaps (user can override).
- CP-SAT model implemented in `scheduler/model.py`.
- Synthetic instance generator in `scheduler/instance.py`.
- Benchmark harness in `scheduler/benchmark.py` that sweeps
  `(30, 50, 100, 200)` doctors × `(7, 14, 28)` days and logs
  `{status, wall_time_s, objective, n_vars, n_constraints}` to `results/*.csv`.
- No ML yet. Hugging Face Space not yet created.

## 4. How to pick up where we left off

1. Read `docs/CONSTRAINTS.md` — this is the spec.
2. Read `docs/CHANGELOG.md` — this is the running log.
3. `pip install -r requirements.txt`.
4. `python -m scheduler.benchmark --smoke` — runs a 10-doctor × 7-day sanity
   check. Should finish in seconds.
5. `python -m scheduler.benchmark` — full sweep. Writes
   `results/benchmark_<timestamp>.csv`.
6. Check the CSV: if the 30-doctor × 28-day row solves in < 60s with
   `OPTIMAL` or high-quality `FEASIBLE`, CP-SAT alone is probably enough and
   the ML phase may be skippable.

## 5. Key files

| Path | Purpose |
|---|---|
| `docs/CONSTRAINTS.md` | The single source of truth for the model. |
| `docs/CONTEXT.md` | This file. |
| `docs/CHANGELOG.md` | Append-only log of what changed, when, and why. |
| `scheduler/instance.py` | `Instance`, `Doctor`, `Station` dataclasses + synthetic generator. |
| `scheduler/model.py` | `build_model(instance) -> (model, vars)` and `solve(...)`. |
| `scheduler/benchmark.py` | CLI sweeping problem sizes, writing CSV. |
| `configs/default.yaml` | Default config for stations / tier mix / weights. |
| `results/` | CSVs and solution dumps. Gitignored except `.gitkeep`. |

## 6. Decisions made so far (rationale)

- **CP-SAT over MIP.** CP-SAT handles the channelling constraints (post-call
  off, on-call 1-in-3) and symmetry breaking better than a typical MIP for
  this style of problem, and it's free + well-maintained.
- **Defaults applied for 9 gaps.** The user said "Continue where it left
  off" after my gap list, so v0.1 bakes in defaults rather than blocking on
  answers. Each default is documented so it is easy to flip.
- **Separate balance terms per tier.** Juniors and consultants do different
  work; balancing them in one pool would give weird results.
- **Weekend stations disabled by default.** The conversation implied weekend
  work *is* the on-call / extended / subspec-consultant roles, not AM/PM
  station coverage. Flip `weekend_am_pm_enabled=True` in the config to
  re-enable.
- **No public-holiday calendar hardcoded.** Pass a list of day indices.

## 7. Known risks and open items

- **Solver blow-up.** At 200 doctors × 28 days × 8 stations × 2 sessions, the
  variable count is ~90k. CP-SAT can usually handle this but it may need
  aggressive symmetry breaking or redundant constraints. If the 200-doctor
  case blows up, fall back to feasibility-only (no objective) and measure.
- **Default list still needs user sign-off.** The 9 gaps in
  `CONSTRAINTS.md §5`. Running the benchmark does not require sign-off, but
  the user-facing UI later will.
- **No unit tests yet.** There's a smoke test; that's it. Add tests before
  wiring to a UI.

## 8. Running in a different environment

The entire project is pure Python. Dependencies:

```
ortools >= 9.10
pyyaml
```

Python 3.10+. No GPU needed for Phase 1. No network needed once deps are
installed. All paths are relative to repo root.

If you are picking this up in a Hugging Face Space, the Space only needs
`requirements.txt` and whatever Gradio app wraps `scheduler.solve`. The Space
has not been created yet.
