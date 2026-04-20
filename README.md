---
title: Healthcare Roster Scheduler
emoji: 🏥
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# Healthcare Roster Scheduler

An interactive monthly roster generator for hospital departments — designed
around radiology but applicable anywhere you have doctors, stations, on-call
shifts, leave, and a fairness requirement. Built on Google OR-Tools CP-SAT,
with a Streamlit UI that lets a single roster coordinator configure the
problem, watch the solver stream improving solutions in real time, and
publish a balanced roster.

## What it does

Given a list of doctors, a list of stations, a horizon, and a set of rules,
the app produces a roster that:

- Covers every clinical slot (stations, on-call, weekend duty) that must be
  covered.
- Respects every doctor's unavailability — leave, call blocks, session blocks.
- Follows the rules you turned on — on-call caps, post-call off, weekend
  rotation, mandatory weekday utilisation.
- Spreads workload fairly across each tier using a weighted score that
  counts weekend work as heavier than weekday work.
- Factors in **prior-period carry-in** — doctors who worked more last month
  get less this month.
- Handles **per-doctor FTE** and **per-doctor on-call caps**.
- Honours **positive preferences** ("Prefer AM on Tuesday") as soft goals.

The solver streams improving solutions while it searches, so you can watch
the roster get better in real time and stop early once it looks good.

## Try it

- **Hugging Face Space** (pre-built):
  <https://huggingface.co/spaces/charlesyapai/doctor_roster_solver>
- **Local**: `pip install -r requirements.txt && streamlit run app.py`,
  then open `http://localhost:8501`.

The Space is private; run locally for a no-login demo.

## The four tabs

| Tab | What for |
|---|---|
| **Setup** | Per-period inputs: dates, doctors on the team, leave and blocks, manual overrides. Edit this every roster cycle. |
| **Department rules** | One-time setup for your department: tier labels, sub-specialties, stations, constraint toggles, shift-length table, fairness weights, solver priorities. Save as YAML and reuse. |
| **Solve & Roster** | Run the solver, watch it stream, review the doctor × date grid (colour-coded), per-doctor workload headline + breakdown, alternative views (station × date, per-doctor calendar, today's roster), diff against another snapshot. |
| **Export** | Download JSON, CSV, or a print-friendly HTML of the final roster. |

Sidebar: **Save / Load YAML** (persist a full configuration across Space
restarts), **Import prior-period workload** (auto-fill `prev_workload`
from last month's JSON export), solver settings, L1 / L3 diagnostics.

## Key features

- **Plain-English UI**. Every rule and weight is labelled by what it *does*,
  not by internal codes like `S0` or `H11`.
- **Soft mandatory-weekday rule**: every doctor gets a duty every weekday
  unless they're on leave, post-call, or a lieu day. Prevents "optimal"
  rosters with idle doctors.
- **Verdict banner** tells you at a glance whether the roster is any good:
  status + optimality gap + idle count + cross-tier-hours-gap warning.
- **Colour-coded roster grid**: green = station work, purple = on-call,
  teal = weekend EXT/WC, grey = leave, amber = no-duty weekday.
- **Per-doctor workload**: weighted score, Δ-vs-tier-median (red/blue),
  hours/week, leave days, days without duty. Breakdown expander for the
  full per-role counts.
- **Lock-and-re-solve**: "Copy this roster to overrides", delete the rows
  you want to change, re-solve. Everything else stays fixed.
- **Multi-day leave in one row** + **CSV bulk-paste** of leave requests.
- **FTE scaling** — a 0.5-FTE doctor carries half a full-timer's workload
  and can be idle more without penalty.
- **Positive preferences** (Prefer AM / Prefer PM) as soft bonus.
- **Stop button** accepts the current best solution via CP-SAT's
  StopSearch().

## Install (local)

```bash
pip install -r requirements.txt
streamlit run app.py
```

Python 3.10+. No GPU needed. Dependencies: `ortools`, `streamlit`,
`pandas`, `plotly`, `PyYAML`.

## Tests

```bash
python -m pytest tests/ -x -q
```

Six tests across two files: a smoke test for feasibility, and a regression
test that verifies H11 (mandatory weekday assignment) actually reduces
idle doctor-weekdays compared to the legacy behaviour. Run time ≈ 2 min.

## Benchmarks

Still available — the solver harness that started this project lives at
`scheduler/benchmark.py`:

```bash
python -m scheduler.benchmark --smoke      # 10 doctors × 7 days
python -m scheduler.benchmark              # full sweep
```

Results land in `results/benchmark_<timestamp>.csv`. On an 8-thread
machine, 30–100 doctor × 28 day instances solve to OPTIMAL in under 10 s;
the 200-doctor case reaches FEASIBLE within the 120 s default. See
`docs/CHANGELOG.md` for the full methodology — these numbers are what
convinced us CP-SAT alone is fast enough for the target range and an
ML-predictor layer is unnecessary.

## Repo layout

```
app.py                   Streamlit UI (four tabs + sidebar)
scheduler/
  instance.py            Doctor / Station / Instance data classes + synthetic gen
  model.py               CP-SAT model (H1–H15, S0–S6, ConstraintConfig,
                         WorkloadWeights, HoursConfig, stop_event)
  diagnostics.py         L1 pre-solve sniff + L3 soft-relax explainer
  metrics.py             problem / solve / solution metrics, workload breakdown
  persistence.py         YAML dump/load + prior-period workload recovery
  plots.py               10 Plotly figure builders
  ui_state.py            DataFrame ↔ Instance adapter, date helpers
  benchmark.py           Sweep CLI
configs/default.yaml     Station / tier / weight defaults (legacy)
docs/
  FEATURES.md            Full feature reference (read this first)
  CONSTRAINTS.md         Authoritative constraint spec (H1–H15, S0–S6)
  CHANGELOG.md           What changed, when, and why
  CONTEXT.md             Handoff notes
tests/                   pytest suite
results/                 Benchmark CSVs (gitignored)
```

## Documentation

- [`docs/FEATURES.md`](docs/FEATURES.md) — every control, every output column,
  colour key, export schemas. Start here if you're a new user.
- [`docs/CONSTRAINTS.md`](docs/CONSTRAINTS.md) — the formal spec. Start here
  if you're modifying the solver.
- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — release history.
- [`docs/CONTEXT.md`](docs/CONTEXT.md) — project context for a new
  contributor.
- [`docs/plots/`](docs/plots/) — per-plot explanations (what the chart
  shows, how to read it, what to focus on).

## License

MIT.
