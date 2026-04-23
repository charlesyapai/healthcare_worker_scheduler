# Research Metrics — Formal Definitions

**Status:** Draft for the validation agent. Last updated 2026-04-23.

This document gives the formal definition of every metric the Lab tab
will compute, plus implementation notes. Companion to
[`VALIDATION_PLAN.md`](VALIDATION_PLAN.md) and
[`INDUSTRY_CONTEXT.md`](INDUSTRY_CONTEXT.md). Where a metric is the
field's standard, that fact is noted so we can defend the choice in
publication.

---

## 0. Notation

Throughout this doc:

- `D` = set of doctors (people on the rota).
- `T` = set of tiers (`junior`, `senior`, `consultant`).
- `D_t ⊆ D` = doctors in tier `t`.
- `H` = horizon length in days.
- `H_wd ⊆ H` = weekday days; `H_we ⊆ H` = weekend / holiday days.
- `R` = set of role kinds (`AM`, `PM`, `ONCALL`, `WEEKEND_EXT`,
  `WEEKEND_CONSULT`).
- `x_{d,r,t}` = 1 if doctor `d` is assigned role `r` on day `t`,
  else 0.
- `w_r` = workload weight of role `r` (from `WorkloadWeights`).
- `f_d ∈ (0, 1]` = full-time-equivalent of doctor `d`.

Where a metric is FTE-aware, the formula is given for full-timers and
then in its FTE-normalised form.

---

## 1. Solution-quality metrics

### 1.1 Total objective `Z`

The CP-SAT objective:

```
Z = Σ_k w_k · p_k
```

where `p_k` is the raw value of penalty component `k` (e.g. idle-
weekday count, workload max-min gap per tier) and `w_k` its weight.

Already exposed via `SolveResult.objective` and broken down per-`k` in
`SolveResult.penalty_components`.

### 1.2 Best bound `B`

CP-SAT's proved lower bound on `Z`. Already exposed as
`SolveResult.best_bound`.

### 1.3 Improvement headroom `H_i`

```
H_i = max(0, Z − B)
```

Absolute gap, in objective units. Replaces the standard relative
optimality gap because CP-SAT's bound is often loose for roster
problems (each component's individual minimum is usually 0). See the
explainer on the Solve page.

### 1.4 Status

`OPTIMAL` (B == Z, proved) | `FEASIBLE` (Z found, B not reached) |
`INFEASIBLE` (no solution exists) | `UNKNOWN` (time limit hit before
either).

### 1.5 First-feasible time `t_f`

Wall-clock seconds from solver start to the first feasible solution.
Surfaces how aggressive the model is to find ANY solution, regardless
of optimisation.

### 1.6 Convergence rate

```
ρ(t) = (Z(t) − B) / (Z(0) − B)
```

where `Z(t)` is the best objective at wall time `t` and `Z(0)` is the
first-feasible objective. `ρ → 0` as the solver converges. The
`/lab/sweep` page should plot `ρ(t)` per (instance, config) pair.

---

## 2. Performance metrics

### 2.1 Total wall time `T_w`

Already in `SolveResult.wall_time_s`.

### 2.2 Time to optimal `T_*`

Time at which CP-SAT proved `OPTIMAL`. Equal to `T_w` if proven before
the time limit; `null` otherwise.

### 2.3 Variables `n_v` and constraints `n_c`

Already exposed. Use as a proxy for instance complexity in scaling
plots.

### 2.4 Throughput

For batch runs:

```
T̄ = (1/n) · Σ_i T_w,i
σ_T = std({T_w,i})
```

Reported per (instance, solver, config) cell.

---

## 3. Scalability metrics

For a parameter sweep over instance sizes:

### 3.1 Solve-time scaling exponent

Fit `T_w ≈ α · n^β` where `n` is the number of doctors. Report `β`.
For CP-SAT on roster problems we typically see `β ∈ [1.5, 2.5]`.

### 3.2 Memory footprint (optional, Phase 5+)

`max_rss` from the solver process. Useful for capacity planning.

---

## 4. Fairness / bias metrics

These all answer: "is the solver systematically favouring some
people over others?" Compute per-tier (juniors vs juniors only —
cross-tier comparisons are meaningless).

Let `S_d` = total weighted workload for doctor `d`:

```
S_d = Σ_{r,t} w_r · x_{d,r,t}
```

For FTE-aware versions, define normalised workload:

```
S̃_d = S_d / f_d
```

so a 0.5-FTE doctor doing 50% of the work has the same `S̃` as a
full-timer doing 100%.

### 4.1 Range (max − min) per tier

```
R_t = max_{d ∈ D_t} S̃_d − min_{d ∈ D_t} S̃_d
```

The simplest "is anyone getting screwed?" number. Already roughly what
the Score breakdown exposes for S0/S1/S2/S3, but unaware of FTE.

### 4.1b Coefficient of variation per tier

Standard in NRP literature ([`INDUSTRY_CONTEXT.md`](INDUSTRY_CONTEXT.md)
§3); adopt alongside Gini so we're cross-comparable with both
econ-flavoured and OR-flavoured papers.

```
CV_t = σ_t / S̃̄_t
```

where `S̃̄_t` is the mean of `S̃_d` over `D_t` and `σ_t` is the std
deviation. Dimensionless; <0.10 is "tight", >0.30 is "high
variance" in workforce-scheduling context.

### 4.2 Gini coefficient per tier

```
G_t = Σ_i Σ_j |S̃_i − S̃_j| / (2 · |D_t|² · S̃̄_t)
```

where `S̃̄_t` is the mean of `S̃_d` over `D_t`. Range [0, 1]; 0 = perfect
equality; >0.2 is concerning in workforce contexts.

### 4.3 Standard deviation per tier

```
σ_t = sqrt( (1/|D_t|) · Σ_d (S̃_d − S̃̄_t)² )
```

Less interpretable than Gini but standard in scheduling literature; we
report both.

### 4.4 Per-individual deviation

For each doctor `d ∈ D_t`:

```
Δ_d = S̃_d − median_{d' ∈ D_t} S̃_{d'}
```

The Workload table on `/roster` already shows this column; the Lab
fairness panel should highlight doctors with `|Δ_d|` above the
top-quartile threshold.

### 4.5 On-call distribution per tier

Same as the workload metrics but restricted to on-call assignments
only. Important because on-call is the most-disliked role and
imbalances here are politically charged.

### 4.6 Day-of-week load distribution

For each tier `t` and day-of-week `dow ∈ {Mon, Tue, …, Sun}`:

```
L_{t, dow} = Σ_{d ∈ D_t, day(t')=dow} S_d
```

normalised by the number of `dow` days in the horizon. Surfaces "are
Mondays disproportionately loaded?" If the variance over `dow` is high,
the solver may be exploiting a structural day-of-week bias.

### 4.7 Subspec parity (consultants only)

For each subspec `s` of consultants:

```
S̃̄_s = (1/|D_s|) · Σ_{d ∈ D_s} S̃_d
```

Then check max-min over subspecs. If one subspec is consistently
loaded harder than another, the solver or the configuration has an
imbalance.

---

## 5. Coverage metrics

### 5.1 Required-vs-actual coverage per (day, station, session)

```
C_{t, s, sess} = (# doctors assigned to (t, s, sess)) / required_per_session
```

For a feasible solution, `C ≡ 1`. Used as a sanity check: if any cell
≠ 1, the validator will catch it; this metric just makes the
distribution visible.

### 5.1b Coverage shortfall and over-coverage

Standard in NRP literature; track separately from idle-weekday count.

```
Shortfall = Σ_{t,s,sess} max(0, required − assigned)
Over     = Σ_{t,s,sess} max(0, assigned − required)
```

For a feasible solution under H1, both should be 0. They surface only
when running with relaxed constraints (e.g., the L3 explainer) or
under heuristic baselines that may over- or under-staff.

### 5.2 Idle-weekday rate

```
I = (# (d, t) ∈ D × H_wd s.t. d has no duty and no excuse on t) / (|D| · |H_wd|)
```

Interpretable as "what fraction of doctor-weekdays were left empty
under our soft mandatory-weekday rule".

### 5.3 Weekend-coverage compliance

For each weekend day, did we actually staff 1 junior EXT, 1 senior
EXT, 1 junior on-call, 1 senior on-call, and 1 consultant per
subspec? Should be 100% under H8. Measure to detect regressions.

---

## 6. Robustness / reproducibility metrics

### 6.1 Multi-seed variance

For a fixed instance and config, run with seeds `s_1, …, s_n`:

```
Z̄ = (1/n) · Σ_i Z(s_i)
σ_Z = std({Z(s_i)})
CV = σ_Z / Z̄
```

`CV` (coefficient of variation) <0.05 is "stable", >0.20 is "highly
seed-sensitive". For publication we report `Z̄ ± σ_Z` over `n ≥ 30`.

### 6.2 Parameter sensitivity

For one CP-SAT parameter `θ` (e.g., `search_branching`), run the same
instance with each value and report:

```
ΔZ_θ = max_θ Z(θ) − min_θ Z(θ)
ΔT_θ = max_θ T_w(θ) − min_θ T_w(θ)
```

Big deltas = sensitive to that parameter; the paper should discuss
why.

### 6.3 Determinism check

For `num_search_workers=1` and a fixed `random_seed`, two runs of the
same instance must produce identical `assignments`. The Lab benchmark
runner should assert this; failure indicates non-deterministic
behaviour we need to track down.

---

## 6b. Benchmark-native scoring

When running on an external benchmark (Curtois, INRC-II, NSPLib),
report the benchmark's native penalty score *in addition* to our own
objective. This is the de-facto common currency that makes us
comparable to ~20+ published papers (see
[`INDUSTRY_CONTEXT.md`](INDUSTRY_CONTEXT.md) §3).

### 6b.1 INRC-II penalty score

Per the INRC-II problem definition. Implement in
`lib/objective_translator.py` as `inrc2_penalty(solution, instance)`.
Aggregate over all soft constraints with the per-instance weights
from the benchmark's JSON.

### 6b.2 Curtois penalty score

Per Curtois's collection conventions. Each instance family (BCV,
Musa, Ozkarahan, Valouxis, etc.) has its own scoring function;
implement per-family adapters in `lib/objective_translator.py`.

### 6b.3 Translator audit

The mapping from our SessionState + assignments to a benchmark's
expected solution format is non-trivial. Every translator must:

- Have a docstring explaining the mapping decision (e.g., "Our
  'No on-call' block maps to Curtois's `<UnwantedShift>` element").
- Have a unit test that round-trips a known-good solution: load the
  benchmark instance, generate a Curtois-format solution, parse it
  back, assert our validator returns zero violations.
- Cite the benchmark's documentation for any non-obvious choice.

## 7. Comparison metrics (vs baselines)

For our solver `S` and a baseline `B`:

### 7.1 Quality ratio

```
Q = Z_B / Z_S
```

`Q > 1` means our solver is better (lower objective). Report per-
instance and as a geometric mean across the benchmark suite.

### 7.2 Time-to-equivalent

How long the baseline takes to reach our objective. If the baseline
never reaches it within a generous budget (e.g., 30× our time limit),
report as `∞`.

### 7.3 Feasibility rate

For each method, fraction of instances it solves to feasibility. A
greedy baseline often fails on tight instances; we should solve 100%.

---

## 8. Implementation notes

### 8.1 Where each metric lives

- Solution quality + performance: `scheduler/metrics.py` already has
  `solve_metrics(...)`; extend with the new fields above.
- Fairness: new module `api/metrics/fairness.py`. Pure functions, no
  side effects, easy to test.
- Coverage: new module `api/metrics/coverage.py`.
- Robustness: aggregator function in `api/lab/aggregate.py` that takes
  a list of `SolveResult` from a multi-seed run.

### 8.2 Storage

- Single-run metrics inline in the `SolveResult` payload (existing
  shape).
- Batch-run metrics in a structured store. Simplest: write
  `lab_runs/<run_id>/{config.yaml, results.json, metrics.json}` to disk
  and serve via `GET /api/lab/runs/{id}`.
- Bundle export = ZIP of that directory plus `git_sha.txt`.

### 8.3 Visualisation

- Single-instance fairness: bar chart per tier with Gini overlay.
- Multi-seed: box plot of `Z` per config.
- Scaling: log-log line of `T_w` vs `n`.
- Sweep: heatmap of metric × parameter value.
- Use the existing `recharts` dependency — no new chart libs.

### 8.4 Test fixtures

- A 3-doctor synthetic instance with hand-computable Gini, range, and
  std. Use as a smoke test for `api/metrics/fairness.py`.
- A known-INFEASIBLE instance for the validator-in-the-loop test.

---

## 9. Reporting templates

For publication, every reported number should be paired with:

- **Instance ID** (link to YAML or benchmark name).
- **Solver version** (git SHA).
- **Run config** (random_seed, branching, workers, time limit, etc.).
- **Sample size** (n seeds).
- **Statistical summary** (mean ± std, or median + IQR if non-normal).

The bundle export must include all five so reviewers can replicate.
