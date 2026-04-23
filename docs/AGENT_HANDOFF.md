# Agent Handoff — Validation & Research Tooling

**You are the next agent picking up the v2 fork.** The first agent built
the React SPA + FastAPI rewrite and shipped feature parity with v1 plus
several extensions (manual editing, warm-started Continue solving,
sample scenarios, score breakdown). The Space is live and stable.

**Your job is different.** The product is visually polished and
functionally complete for end users. What's missing is the **validation
& research tooling** required before this can be published as an
academic instrument or trusted in a real hospital. You are building the
"Lab" surface — not more user features.

Read the docs in this order:

1. **This file** (handoff context, rules, first steps).
2. [`INDUSTRY_CONTEXT.md`](INDUSTRY_CONTEXT.md) — literature-grounded
   background: how the field calls our problem (NRP), which benchmarks
   exist, what metrics the literature uses, what regulations govern
   real deployments. Read this BEFORE the validation plan so the
   metric / benchmark choices below have proper context.
3. [`VALIDATION_PLAN.md`](VALIDATION_PLAN.md) — strategic plan: what to validate
   and why.
4. [`RESEARCH_METRICS.md`](RESEARCH_METRICS.md) — formal definitions of every
   metric you'll compute.
5. [`LAB_TAB_SPEC.md`](LAB_TAB_SPEC.md) — concrete UI + API spec for the Lab tab.
6. [`NEW_UI_PLAN.md`](NEW_UI_PLAN.md) — the original v2 plan; still reads true
   for the rest of the app.
7. [`CONSTRAINTS.md`](CONSTRAINTS.md) — formal constraint spec. Single source of
   truth; do not change without escalating.
8. [`CHANGELOG.md`](CHANGELOG.md) — recent commits at the top.

## What's already built (do not rebuild)

- React SPA at `ui/` (Vite + TypeScript strict + Tailwind v4 + TanStack
  Query + Zustand + React Router). 6 routes: Dashboard, Setup, Rules,
  Solve, Roster, Export.
- FastAPI at `api/` exposing `/api/state`, `/api/state/yaml`, `/api/state/seed`,
  `/api/state/scenarios/...`, `/api/diagnose`, `/api/explain`,
  WebSocket `/api/solve`, REST fallback `/api/solve/run`,
  `/api/roster/validate`, `/api/overrides/fill-from-snapshot`.
- Solver at `scheduler/` (CP-SAT). The constraint set covers H1–H15 and
  S0–S6 plus a new weekday on-call coverage rule. Warm-start is supported
  via `solve(..., warm_start=...)`.
- Three pre-built scenarios under `configs/scenarios/` — tested feasible.
- Hard-constraint validator at `api/validator.py`.
- Manual edit mode on `/roster` with live validation.

## What you must NOT do

- **Don't break the SPA.** Users rely on it. New work goes under a new
  `/lab` route; do not refactor existing routes unless absolutely
  necessary, and never as a side-effect of Lab work.
- **Don't churn `scheduler/` lightly.** The previous agent added two
  fields (`weekday_oncall_coverage_enabled`, `warm_start`) and
  documented why. Each new addition needs the same scrutiny — escalate
  before adding constraints. Adding solver-parameter passthrough kwargs
  to `solve()` is encouraged (search_branching, random_seed, etc.) since
  it's purely additive.
- **Don't skip the constraint spec.** Every metric you compute should
  be cross-referenced against `docs/CONSTRAINTS.md`. If you find a
  discrepancy between the spec and the model, raise it before "fixing"
  either.
- **Don't deploy without tests.** `pytest tests/ -x -q` must stay green
  through every commit. Add new tests under `tests/test_lab_*.py` for
  Lab features.

## Rules of the road

- Branch: keep working on `react-ui`. The previous agent has been
  pushing here; do the same.
- Commit + push to GitHub `origin` and HF Space `hf_v2` after each
  meaningful change. The HF Space rebuilds in ~2 min; verify
  `runtime.stage == "RUNNING"` before starting the next phase. The push
  pattern + token live in memory under `hf_token_usage.md`.
- Every Lab-page commit should be accompanied by:
  - A backend test if the change touched `api/`.
  - A pytest run.
  - A `pnpm build` clean of TypeScript errors.
- If you need to expand the constraint model or change the scheduler's
  default behaviour, write a one-paragraph rationale in the commit
  message and update `docs/CONSTRAINTS.md` in the same commit.

## First three things to do

1. Read `VALIDATION_PLAN.md` end to end. Confirm with me whether the
   phased roadmap is the right shape; ask before deviating.
2. Implement Phase 1 of the plan (post-solve validator integration +
   per-tier fairness metrics in the existing Solve flow). This is the
   smallest unit that delivers immediate value and validates your read
   of the scheduler internals.
3. Then start `/lab` per `LAB_TAB_SPEC.md`. Phase by phase, ship
   working surfaces — do not build the entire Lab in one go.

## Sample scenarios are starting points, not benchmarks

The three scenarios in `configs/scenarios/` exist so a user can click
"see the solver work". They are **not** statistical benchmarks. For
research publication you need:

- Multiple seed runs of the same instance (≥30, ideally 100+).
- A wider problem-size sweep (5/10/15/20/30/50/100 doctors × 7/14/28/90
  days).
- Comparison against at least one external benchmark (NSPLib instances
  are public-domain; INRC-II requires licence acknowledgement; check
  per-instance terms before bundling).

`scripts/build_scenarios.py` is the template for how a benchmark
generator looks; the Lab benchmark runner should follow the same
"build → solve → verify → record" shape but at scale.

## Things that are easy to get wrong

- **CP-SAT randomness.** `solver.parameters.random_seed = 0` is the
  default. For multi-seed reporting you must vary this *and* CP-SAT's
  internal portfolio search ordering — see `RESEARCH_METRICS.md` for
  the recipe.
- **WebSocket reliability on HF.** The Lab's batch runs should NOT use
  the WebSocket path — use REST `/api/solve/run` or a new dedicated
  batch endpoint. WS is for live-progress UX, not throughput.
- **Reproducibility bundles must include code revision.** Embed the
  git SHA in every export; researchers can't reproduce anything
  without knowing which version of the solver they're hitting.
- **Fairness metrics need to ignore part-time staff sensibly.** A 0.5-
  FTE doctor doing 50% of the work isn't unfair — see
  `RESEARCH_METRICS.md` §4 for the FTE-normalised formulae.

## Communication rhythm

- **Announce** before each Lab phase ("Starting Phase 2 — fairness
  panel").
- **Summarise** after ("Phase 2 done. /lab/fairness shows Gini, max-
  min, per-individual deltas. Commit `<sha>`. HF rebuild RUNNING.").
- **Escalate** on:
  - Anything that wants to change `docs/CONSTRAINTS.md`.
  - Anything that wants to change the SPA's existing routes.
  - Any benchmark whose licence is unclear.
- Keep intermediate explanations short (≤100 words). I'll ask if I need
  more detail.

## Success criteria

You're done when:

1. A researcher can drop a YAML config + run-config JSON into
   `/lab/benchmark`, hit Run, and get a downloadable report bundle that
   another researcher can re-run end-to-end.
2. Every solve (UI or batch) emits a feasibility check; failures are
   logged not silenced.
3. The fairness panel shows per-tier and per-individual bias metrics
   with documented formulae linked to `RESEARCH_METRICS.md`.
4. CP-SAT's branching strategy, presolve, LNS, and random seed are
   selectable per run.
5. We can point a peer reviewer at one URL and they can verify the
   solver does what we claim — without reading the source.

That's the bar. Ship phase by phase; don't try to clear it in one go.
