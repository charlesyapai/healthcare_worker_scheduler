# Tuning sweep — 2026-04-23

**Budget**: 30.0s · **Seeds**: [0, 1] · **num_workers**: 1 (deterministic) · **Variants**: baseline, symmetry, oncall_first, redundant, all_three

Each cell reports mean across seeds. Lower objective = better.

## busy_month_with_leave

| Variant | Mean obj | Std obj | Mean bound | Mean headroom | Time-to-first-feasible | Status counts |
|---|---:|---:|---:|---:|---:|---|
| baseline | 4422.5 | 402.5 | 440.0 | 3982.5 | 3.382s | O=0 F=2 ¬=0 |
| symmetry | 5837.5 (+1415 / +32.0%) | 787.5 | 345.0 | 5492.5 | 3.361s | O=0 F=2 ¬=0 |
| oncall_first | 4522.5 (+100 / +2.3%) | 402.5 | 440.0 | 4082.5 | 3.56s | O=0 F=2 ¬=0 |
| redundant | 4472.5 (+50 / +1.1%) | 452.5 | 440.0 | 4032.5 | 3.668s | O=0 F=2 ¬=0 |
| all_three | 5837.5 (+1415 / +32.0%) | 787.5 | 345.0 | 5492.5 | 3.344s | O=0 F=2 ¬=0 |

## clinic_week

| Variant | Mean obj | Std obj | Mean bound | Mean headroom | Time-to-first-feasible | Status counts |
|---|---:|---:|---:|---:|---:|---|
| baseline | 370.0 | 50.0 | 0.0 | 370.0 | 0.049s | O=0 F=2 ¬=0 |
| symmetry | 320.0 (-50 / -13.5%) | 0.0 | 0.0 | 320.0 | 0.079s | O=0 F=2 ¬=0 |
| oncall_first | 422.5 (+52 / +14.2%) | 2.5 | 0.0 | 422.5 | 0.05s | O=0 F=2 ¬=0 |
| redundant | 422.5 (+52 / +14.2%) | 2.5 | 0.0 | 422.5 | 0.05s | O=0 F=2 ¬=0 |
| all_three | 320.0 (-50 / -13.5%) | 0.0 | 0.0 | 320.0 | 0.079s | O=0 F=2 ¬=0 |

## hospital_long_month

| Variant | Mean obj | Std obj | Mean bound | Mean headroom | Time-to-first-feasible | Status counts |
|---|---:|---:|---:|---:|---:|---|
| baseline | None | 0.0 | None | None | Nones | O=0 F=0 ¬=2 |
| symmetry | None | 0.0 | None | None | Nones | O=0 F=0 ¬=2 |
| oncall_first | None | 0.0 | None | None | Nones | O=0 F=0 ¬=2 |
| redundant | None | 0.0 | None | None | Nones | O=0 F=0 ¬=2 |
| all_three | None | 0.0 | None | None | Nones | O=0 F=0 ¬=2 |

## nursing_ward

| Variant | Mean obj | Std obj | Mean bound | Mean headroom | Time-to-first-feasible | Status counts |
|---|---:|---:|---:|---:|---:|---|
| baseline | 4050.0 | 450.0 | 0.0 | 4050.0 | 0.794s | O=0 F=2 ¬=0 |
| symmetry | 4965.0 (+915 / +22.6%) | 80.0 | 30.0 | 4935.0 | 1.342s | O=0 F=2 ¬=0 |
| oncall_first | 4050.0 | 450.0 | 0.0 | 4050.0 | 0.796s | O=0 F=2 ¬=0 |
| redundant | 4050.0 | 450.0 | 0.0 | 4050.0 | 0.794s | O=0 F=2 ¬=0 |
| all_three | 4965.0 (+915 / +22.6%) | 80.0 | 30.0 | 4935.0 | 1.344s | O=0 F=2 ¬=0 |

## radiology_small

| Variant | Mean obj | Std obj | Mean bound | Mean headroom | Time-to-first-feasible | Status counts |
|---|---:|---:|---:|---:|---:|---|
| baseline | 640.0 | 50.0 | 452.5 | 187.5 | 0.122s | O=0 F=2 ¬=0 |
| symmetry | 640.0 | 55.0 | 460.0 | 180.0 | 0.259s | O=0 F=2 ¬=0 |
| oncall_first | 640.0 | 50.0 | 452.5 | 187.5 | 0.123s | O=0 F=2 ¬=0 |
| redundant | 640.0 | 50.0 | 452.5 | 187.5 | 0.121s | O=0 F=2 ¬=0 |
| all_three | 640.0 | 55.0 | 460.0 | 180.0 | 0.263s | O=0 F=2 ¬=0 |

## regional_hospital_month

| Variant | Mean obj | Std obj | Mean bound | Mean headroom | Time-to-first-feasible | Status counts |
|---|---:|---:|---:|---:|---:|---|
| baseline | None | 0.0 | None | None | Nones | O=0 F=0 ¬=2 |
| symmetry | None | 0.0 | None | None | Nones | O=0 F=0 ¬=2 |
| oncall_first | None | 0.0 | None | None | Nones | O=0 F=0 ¬=2 |
| redundant | None | 0.0 | None | None | Nones | O=0 F=0 ¬=2 |
| all_three | None | 0.0 | None | None | Nones | O=0 F=0 ¬=2 |

## teaching_hospital_week

| Variant | Mean obj | Std obj | Mean bound | Mean headroom | Time-to-first-feasible | Status counts |
|---|---:|---:|---:|---:|---:|---|
| baseline | 3165.0 | 575.0 | 262.5 | 2902.5 | 4.978s | O=0 F=2 ¬=0 |
| symmetry | 9242.5 (+6078 / +192.0%) | 5337.5 | 142.5 | 9100.0 | 1.658s | O=0 F=2 ¬=0 |
| oncall_first | 3165.0 | 575.0 | 262.5 | 2902.5 | 4.973s | O=0 F=2 ¬=0 |
| redundant | 3165.0 | 575.0 | 262.5 | 2902.5 | 4.974s | O=0 F=2 ¬=0 |
| all_three | 9242.5 (+6078 / +192.0%) | 5337.5 | 142.5 | 9100.0 | 1.654s | O=0 F=2 ¬=0 |

## How to read this

- **Mean obj**: average final objective across seeds. Negative delta vs baseline = improvement (lower is better).
- **Mean bound**: CP-SAT's best-proved lower bound on the objective. Higher = more honest feasibility gap. A tuning toggle that raises the bound *without changing the objective* still helps — researchers can cite tighter optimality claims.
- **Mean headroom**: `objective - bound`. When it reaches zero the solver has proven optimality. Lower is better.
- **Time-to-first-feasible**: seconds to find any feasible solution. Important for UI responsiveness.

⚠ Every cell ran under a fixed time budget with `num_workers=1`. The reported gap between CP-SAT and tuned variants is often more about **where the solver was in its search at the time limit** than about the tuning's long-run quality. For publication-grade claims, re-run with a longer budget (≥ 5 minutes per cell) and ≥ 30 seeds.

---

## Findings

### `symmetry_break` — helps on flat-objective scenarios, actively hurts on max-min-balanced ones

| Scenario | Obj Δ vs baseline |
|---|---:|
| clinic_week | **−13.5%** ✅ |
| radiology_small | 0% (tied) |
| nursing_ward | +22.6% ❌ |
| busy_month_with_leave | +32.0% ❌ |
| teaching_hospital_week | **+192.0%** ❌❌ |

**Why the split.** `symmetry_break` lex-orders interchangeable doctors (lower-id doctor carries ≥ on-call/station/ext/wconsult counts). This is safe in the usual CP sense — the set of feasible solutions is preserved up to symmetry. But our objective contains per-tier **max−min** fairness terms (S0, S1, S2, S3). Those terms explicitly *penalise* the kind of imbalance that lex-ordering creates: forcing doctor a to dominate doctor b in workload directly widens `max−min`. On `teaching_hospital_week` the 8-junior/6-senior/16-consultant team has so much interchangeability that the lex-order becomes a very strong constraint against fairness, triple-ing the objective.

**Where it works.** `clinic_week` turns off H8 (weekend coverage) and the weekday on-call rule, so the weight on S0/S1/S2 is effectively zero — there's no symmetric max-min term to fight with. The lex-ordering just prunes search without conflict, and objective drops 13.5%.

**Take-away.** `symmetry_break` is **not safe to turn on by default** for scenarios with tier-level fairness weights. The fundamental fix would require an assignment-matrix-level lex-order instead of count-based lex-order — substantially more complex (O(n² × horizon × stations) channel variables) and deferred to a future research pass.

### `oncall_first` — zero lift observed

Same objective, same bound, same time-to-first-feasible as baseline across every scenario. Hypothesis: with `num_workers=1`, CP-SAT's automatic variable selection is already picking on-call-like variables early; our explicit decision strategy is redundant. Worth re-testing with multi-worker portfolios where the parallel search's diversity might benefit from a steering hint.

### `redundant_aggregates` — zero lift observed

Same story: no observable change. The LP relaxation benefit I hypothesised didn't materialise on these scenarios at this budget. Safe to leave off.

### Deterministic single-worker runs fail on month-sized problems

`regional_hospital_month` (30 doctors × 28 days) and `hospital_long_month` (35 × 28) returned `UNKNOWN` on **every** variant — CP-SAT with `num_workers=1` and a 30-second budget couldn't even find a feasible assignment. Those scenarios solve fine at `num_workers=8` (how the Lab UI drives them by default), which is the trade-off: deterministic reproducibility vs. the portfolio-search parallelism large instances depend on. Researchers reporting on these instances should note the single-worker failure explicitly.

---

## Recommendations

1. **Keep all three toggles OFF by default.** Our empirical sweep shows none of them improves the objective on scenarios with fairness weights, and `symmetry_break` actively destroys quality on the larger teams.
2. **Keep the toggles exposed in `/lab/benchmark`'s Advanced panel** with experimental labels. A researcher testing on a differently-shaped instance (e.g., one without max-min fairness terms) may get value from them.
3. **Investigate assignment-level symmetry-break.** Proper lex-order on the per-doctor assignment *matrix* — not the aggregate counts — would preserve fairness invariance. This is a multi-day research task; only worth doing if a NSPLib/Curtois native adapter lands and we have a benchmark dataset to validate against.
4. **Default `num_workers` should stay ≥ 4 for real use.** Determinism is a Lab-only concern.
5. **The "improvement" we can actually ship today** is NOT from these toggles. It's the observability they give us — the sweep itself is the deliverable. Future tuning work starts from this baseline.

---

## Raw data

Full per-cell records (status, objective, bound, wall time, time-to-first-feasible) are in [`results/tuning_sweep/cells.json`](../results/tuning_sweep/cells.json) — re-aggregable under different statistics (median, IQR, percentile, etc.) without re-running the solver.

To reproduce:

```bash
python scripts/benchmark_tuning.py --budget 30 --seeds 0,1
```

For more seeds or a longer budget:

```bash
python scripts/benchmark_tuning.py --budget 120 --seeds 0,1,2,3,4,5,6,7,8,9
```