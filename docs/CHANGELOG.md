# Changelog

Append-only log. Newest at top. Each entry: date, short title, what/why.

## 2026-04-18 — v0.1 initial scaffold

**What:** Initial repo layout, constraint spec, CP-SAT model, synthetic
instance generator, benchmark harness.

**Why:** User requested a Phase-1 benchmark to measure CP-SAT solve time
across problem sizes before committing to an ML-predictor architecture.

**Files added:**
- `docs/CONSTRAINTS.md` — v0.1 spec, defaults applied to gaps #1–9.
- `docs/CONTEXT.md` — project context / handoff doc.
- `docs/CHANGELOG.md` — this file.
- `scheduler/__init__.py`, `scheduler/instance.py`, `scheduler/model.py`,
  `scheduler/benchmark.py` — CP-SAT model + benchmark harness.
- `configs/default.yaml` — tier mix, station list, solver settings.
- `tests/test_smoke.py` — 10×7 feasibility smoke test.
- `README.md`, `requirements.txt`, `.gitignore`.

**Decisions:**
- Chose CP-SAT (OR-Tools) over MIP — better fit for channelling constraints.
- Applied defaults for the 9 open gaps rather than blocking on user input;
  defaults documented in `CONSTRAINTS.md §5` and toggleable in config.
- Benchmark sweep: doctors ∈ {30, 50, 100, 200} × days ∈ {7, 14, 28}. Records
  status, wall time, objective, variable count, constraint count.
- Solver time limit defaults to 300 s per run. Can be raised for the
  200-doctor cases if needed.

**First benchmark pass (single seed, 1 worker machine, 8 CP-SAT threads):**

| Doctors | Days | Status   | Wall time | Objective | Vars   | Constraints |
|--------:|-----:|----------|----------:|----------:|-------:|------------:|
| 15      | 7    | OPTIMAL  | 0.29 s    | 60        |  1,009 |        892  |
| 30      | 7    | OPTIMAL  | 0.27 s    | 40        |  1,990 |      1,542  |
| 30      | 28   | OPTIMAL  | 3.98 s    | 40        |  7,727 |      6,605  |
| 50      | 28   | OPTIMAL  | 6.18 s    | 20        | 12,677 |     11,632  |
| 100     | 28   | OPTIMAL  | 9.91 s    | 60        | 25,331 |     22,070  |
| 200     | 28   | FEASIBLE | 120.15 s  | 90        | 50,671 |     44,023  |

Takeaway: CP-SAT is **much faster than expected** on the target range. 30–100
doctors × 28 days solves to proved-optimal in < 10 s. At 200 doctors × 28
days the solver finds a feasible solution within the 120 s limit but doesn't
prove optimality — for interactive use this is still usable (show the first
feasible solution, refine in the background).

**Implication for Phase 2 (ML predictor):** Very likely unnecessary for the
30–100 doctor use case. For the 200-doctor extension we may want it, but the
simpler first move is probably (a) run longer (300–600 s), (b) tighten
symmetry breaking, or (c) relax optimality and accept a high-quality
feasible solution — all of which are cheaper than training a model.

**Not yet done:**
- User confirmation on gaps #1–9.
- Multi-seed benchmark sweep to characterize variance.
- Hugging Face Space / Gradio UI.
- Unit tests beyond the smoke test.
- ML predictor (Phase 2 — looking unlikely based on above).
