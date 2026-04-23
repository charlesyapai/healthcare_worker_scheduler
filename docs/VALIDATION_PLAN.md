# Validation Plan — Bridging Visual Product to Research Instrument

**Status:** Draft for the validation agent. Last updated 2026-04-23.

> **Context note:** read [`INDUSTRY_CONTEXT.md`](INDUSTRY_CONTEXT.md)
> first. This plan adopts the Nurse Rostering Problem (NRP)
> terminology, the Curtois + INRC-II benchmark suite, and the
> fairness metrics standard in the literature. Where this doc says
> "benchmark", "fairness metric", or "baseline", the specific choices
> are justified there.

## 0. Why this document exists

The v2 SPA looks polished. A roster coordinator can configure, solve,
edit, and publish a roster end-to-end without leaving the page. That's
the product story — and it's done.

The **research story** is not done. To publish this as an academic
instrument or pilot it inside a hospital, we need to defend three
claims that the current build cannot defend on its own:

1. **Solutions are feasible.** Every roster the solver returns satisfies
   every hard constraint, every time, on instances of arbitrary size.
2. **Solutions are competitive.** The objective scores are at least as
   good as a documented baseline (greedy / MILP / random) on a public
   benchmark.
3. **Solutions are reproducible.** Anyone can re-run the same
   experiments and get the same numbers, given the same inputs and
   solver configuration.

A reviewer or a hospital-procurement officer who can't verify these
won't trust the tool. The Lab tab + its supporting infrastructure
exists to make all three verifiable from one URL.

## 1. The three pillars

### 1.1 Feasibility

What we have today:

- `scheduler/diagnostics.py` provides L1 (pre-solve necessary-
  condition checks) and L3 (soft-relax infeasibility explainer).
- `api/validator.py` checks an arbitrary assignment list against the
  hard constraints (H1–H15 plus the weekday on-call rule).
- Manual edit mode on `/roster` posts every change to
  `POST /api/roster/validate` and shows live violations.

What's missing:

- No automated post-solve check on solver outputs. We trust that
  CP-SAT respects the model. If the model has a bug, we don't catch it.
- No regression suite over historical solved rosters.
- No "constraint coverage" report — we can't say "this run exercised
  H4, H8, H10, H13" so we don't know which rules are routinely
  exercised vs. dormant.

What needs to happen (Phase 1):

- Run the validator inside `solve_sync` and `solve_ws` immediately
  after CP-SAT returns. If any violation is reported, log + flag in
  the response. This is a tripwire, not a soft warning.
- Add `tests/test_validator_against_solver.py`: solve each scenario,
  validate, assert zero violations.
- Surface a "Constraints exercised" badge on the Solve page using the
  validator's per-rule pass list.

### 1.2 Solution quality

What we have today:

- A weighted-objective formulation (S0–S6 with documented weights).
- `Score breakdown` UI explaining where the score comes from.
- Three sample scenarios that solve to FEASIBLE/OPTIMAL.

What's missing:

- No comparison against any baseline. We don't know if our objective
  500 is "good" or "leaving 80% on the table".
- No public-benchmark integration. The Curtois NRP collection,
  INRC-II, and NSPLib are the candidates per
  [`INDUSTRY_CONTEXT.md`](INDUSTRY_CONTEXT.md) §2; none are wired in.
- No multi-seed runs. A single seed's result is anecdote, not data.
- No alternative-formulation comparison. Our soft-weight scheme
  doesn't map 1:1 to the INRC-II penalty function — we need a
  translator (`lib/objective_translator.py`) so we can report both.

What needs to happen (Phase 2):

- Implement three baseline solvers in `scheduler/baselines.py` (in
  priority order — see [`INDUSTRY_CONTEXT.md`](INDUSTRY_CONTEXT.md) §6
  for justification):
  - `milp.py` — PuLP + CBC direct MILP formulation. The "naive
    textbook OR" baseline that NRP papers most commonly compare
    against. Open-source, reproducible, no commercial-licence concern.
  - `greedy.py` — fill stations day-by-day in a fixed priority order;
    sanity floor.
  - `random_repair.py` — random assignment + repair loop; another floor.
- Add a benchmark runner in `api/lab/` (see `LAB_TAB_SPEC.md`) that
  takes (instance, solver, params, seed) tuples and records results
  to a structured store.
- Adapt at least one **Curtois NRP collection** instance and one
  **INRC-II** instance into our YAML format. Document the mapping
  decisions in [`RESEARCH_METRICS.md`](RESEARCH_METRICS.md) §8 (e.g.,
  how we represent "preferred shifts", how Curtois "patterns" map to
  our blocks). Cite licence terms inline.

### 1.3 Reproducibility

What we have today:

- YAML save/load on the SPA gives bit-identical config persistence.
- Git SHA is implicit (whatever's deployed).

What's missing:

- No "run config" object that captures solver parameters (seed,
  branching, workers, time limit, etc.) per solve.
- No bundled export that ties (config + run-config + result) to a git
  SHA so a reviewer can rebuild the exact same environment.
- No statistical aggregation across runs. The user can do one solve
  but can't say "of 30 runs, mean objective 482 ± 23".

What needs to happen (Phase 3):

- Define a `RunConfig` Pydantic model holding every CP-SAT parameter
  we expose (random_seed, search_branching, num_workers, presolve,
  linearization_level, optimize_with_core, use_lns_only,
  time_limit_s).
- Pass it through to `scheduler.solve(...)` via new kwargs (additive,
  scheduler/ change is small and documented).
- Add `POST /api/lab/run` that accepts `(yaml_state, run_config,
  seeds: list[int])` and returns `(results: list[SolveResult],
  aggregate_stats)`.
- Add reproducibility-bundle export: ZIP with `state.yaml`,
  `run_config.json`, `results.json`, `git_sha.txt`, `requirements.txt`,
  and a `README.md` describing how to replay.

## 2. Phased roadmap

### Phase 1 — Validator-in-the-loop + bias panel (~2 days)

- Wire `api.validator.validate` into both solve paths post-solve.
- Add `api/metrics/fairness.py` computing per-tier Gini, max-min,
  range, std deviation; per-individual deviation from tier mean;
  day-of-week load distribution.
- Show a "Solver self-check" badge on the Solve page (green if
  validator returned zero violations).
- Add a "Fairness" tab on `/roster` (or a new section in the Workload
  card) that surfaces the bias metrics.
- Tests:
  - Solver output → validator → must be zero-violation for all three
    scenarios. Run as part of pytest.
  - Fairness metric formulae spot-checked against hand-computed
    examples.

**Deliverable:** every solve carries an automated feasibility receipt
and visible bias metrics. Reviewers can trust the SPA's outputs.

### Phase 2 — Baselines + benchmark adapter (~3 days)

- Implement `greedy_baseline` and `random_repair` in
  `scheduler/baselines.py`. Both should solve any Instance and return
  a SolveResult-compatible object (status="HEURISTIC").
- Build `api/lab/benchmark.py` that takes a list of (instance, solver,
  params, seed) and runs them serially, writing results to disk.
- Adapt one NSPLib instance into our YAML format. Document the mapping
  in `docs/RESEARCH_METRICS.md` §6. Verify our solver and the greedy
  baseline both produce a feasible solution.

**Deliverable:** we can point at a benchmark instance and say "our
solver scores X, greedy scores Y, here's the gap". First publishable
quality datum.

### Phase 3 — RunConfig + parameter exploration (~2 days)

- Add Pydantic `RunConfig` and pass through to scheduler.solve.
- Expose CP-SAT levers in the Solve page's existing settings rail
  (or a new "Advanced" subsection).
- Add `POST /api/lab/run` for batch runs.
- Reproducibility bundle export.

**Deliverable:** a researcher can vary the random seed and document
mean ± std. Can pick branching=PORTFOLIO_SEARCH vs FIXED_SEARCH and
see how it affects time-to-feasible.

### Phase 4 — Lab UI surfaces (~3 days)

Build the `/lab` route per `LAB_TAB_SPEC.md`:

- `/lab/benchmark` — run a benchmark suite, see results in a sortable
  table, download bundle.
- `/lab/sweep` — parameter sweep over a single instance.
- `/lab/fairness` — deep-dive bias view for a specific result.
- `/lab/scaling` — solve time vs. problem size chart.

**Deliverable:** the research-facing tab is live. End-of-phase review
should pit our solver against the greedy baseline on the NSPLib
instance, and produce a publication-grade comparison plot.

### Phase 5 — Documentation pass (~1 day)

- Update `README.md` with research-usage instructions.
- Update `docs/CHANGELOG.md`.
- Add `docs/HOW_TO_REPRODUCE.md` — step-by-step replay instructions
  for a downloaded bundle.
- Add `docs/CITING.md` — the cite-us text and a BibTeX entry stub.

**Deliverable:** ready for first peer-review submission.

Total budget: ~11 days for a single agent.

## 3. Known gaps and risks

### 3.1 Our objective formulation is custom

Most NRP literature uses a shared "soft penalty" formulation but the
specific weights and components differ. Our S0–S6 won't map 1:1 to any
benchmark's scoring. Plan: report results in our metric AND in the
benchmark's native metric (translate via `lib/objective_translator.py`).
Document the mapping explicitly so reviewers can audit it.

### 3.2 INRC-II licence terms

INRC-II instances are publicly available but require academic-use
acknowledgement. We must not ship them inside the Docker image without
checking the licence text. NSPLib (Vanhoucke 2007) is more permissive —
start there.

### 3.3 CP-SAT determinism

Even with a fixed `random_seed`, CP-SAT's parallel search can produce
non-deterministic results unless `num_search_workers=1`. For
reproducibility runs we must clamp to single-worker mode. Multi-worker
runs are still valuable for performance but must be flagged as
"non-deterministic".

### 3.4 FTE handling in fairness

A 0.5-FTE doctor doing 50% of the work isn't unfair — they're
deliberately part-time. Naive Gini will flag them as outliers. We must
normalise by FTE before computing bias metrics. Formulae are in
`RESEARCH_METRICS.md` §4.

### 3.5 No real-world data yet

All three sample scenarios are synthetic. Before publication we need
at least one anonymised real-hospital dataset to validate the
formulation isn't a thought experiment. The **Curtois NRP collection
includes anonymised real-hospital instances** (see
[`INDUSTRY_CONTEXT.md`](INDUSTRY_CONTEXT.md) §2) — adopting them
addresses this risk for free.

### 3.6 No regulatory-conformance test suite

A roster that is mathematically feasible but violates statutory limits
(UK WTD, ACGME duty hours, California nurse:patient ratios) is
unusable in production. The Lab tab should include at least one
**regulatory-conformance module** as a pluggable hard-constraint
suite. Recommended: UK NHS junior-doctor + WTD as the first one
(covers EU + Commonwealth + UK academic audience). See
[`INDUSTRY_CONTEXT.md`](INDUSTRY_CONTEXT.md) §5 for the full rule list
to encode.

### 3.7 Constraint taxonomy not yet mapped

Our H1–H15 set is mainstream but reviewers will ask "how does this
map to the De Causmaecker / Vanden Berghe taxonomy?". The mapping is
already worked out in [`INDUSTRY_CONTEXT.md`](INDUSTRY_CONTEXT.md) §4;
copy it into `docs/CONSTRAINTS.md` as an appendix during Phase 5.

## 4. What success looks like

A reviewer reads our submission. They:

1. Clone the repo at the cited git SHA.
2. Pull the bundled benchmark instance.
3. Run `pnpm install && python -m pytest tests/` → green.
4. Run `python scripts/run_benchmark.py instance=NSPLib_001 seed=0..29`
   → reproduces our reported mean ± std within rounding.
5. Open the Lab tab, run the same instance with our solver and the
   greedy baseline, see the gap we claim.
6. Walk away convinced the system works as we say it does.

That's the success criterion. Everything in this plan exists to clear
that bar.
