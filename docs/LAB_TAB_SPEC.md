# Lab Tab — UI + API Specification

**Status:** Draft for the validation agent. Last updated 2026-04-23.

This is the implementation spec for the new `/lab` route. It assumes
you've read [`VALIDATION_PLAN.md`](VALIDATION_PLAN.md) and
[`RESEARCH_METRICS.md`](RESEARCH_METRICS.md).

---

## 0. Why a separate tab?

The existing 6 routes (Dashboard / Setup / Rules / Solve / Roster /
Export) serve roster coordinators producing a real schedule. The Lab
serves a different audience — researchers, hospital procurement
officers, and us when we're tuning the solver — running batches,
comparing configs, exporting reproducibility bundles.

Mixing those audiences would clutter both. A separate route lets us
ship rich diagnostic surfaces without distracting end users. Hide it
under a bottom-of-nav "Lab" link with a beaker icon (`FlaskConical`
already used on Dashboard scenarios).

---

## 1. Page structure

```
/lab                 → redirect to /lab/benchmark
/lab/benchmark       → batch runner: instance × config × seeds
/lab/sweep           → parameter sweep over a single instance
/lab/fairness        → deep-dive bias view for one result
/lab/scaling         → solve time vs problem size
/lab/runs/:run_id    → single-run detail page
```

### 1.1 Layout

Same `<Layout>` shell as the rest of the app. Inside the main column:

- Sub-tabs at the top (`Benchmark | Sweep | Fairness | Scaling`).
- Right rail (collapsable) holding the run history list — last 20
  runs across all sub-tabs, click to jump to detail.

---

## 2. Sub-tab — Benchmark

The most important surface. Lets a researcher run one or more
instances, with one or more solver configs, with N seeds each, and
view the aggregate.

### 2.1 Inputs panel (left rail)

- **Instance source** — radio:
  - "Current session state" (whatever's loaded in /setup)
  - "Pre-built scenario" → dropdown of `configs/scenarios/*.yaml`
  - "Upload YAML" → file picker
  - "Paste YAML" → textarea
- **Solver(s)** — multi-select chips:
  - "CP-SAT (this app)" (default on)
  - "Greedy baseline"
  - "Random + repair baseline"
- **Run config** — collapsible `Advanced` panel:
  - Time limit (s) — number
  - CPU workers — number (default 1 for reproducibility)
  - `random_seed` — `auto` (CSV of seeds) or `single` (one number)
  - `search_branching` — dropdown
    (`AUTOMATIC | FIXED | PORTFOLIO | LP | PSEUDO_COST`)
  - `linearization_level` — 0 / 1 / 2
  - `cp_model_presolve` — checkbox (default on)
  - `optimize_with_core` — checkbox
  - `use_lns_only` — checkbox
- **Seeds** — number of seeds (default 1; ≥30 for stats)
- **Run** button (kicks off the batch)

### 2.2 Results table

Columns:

| Run | Instance | Solver | Seed | Status | Objective | Headroom | t_first | t_total | n_violations |

- One row per (instance × solver × seed) tuple.
- Sortable / filterable.
- Click a row → `/lab/runs/:run_id`.
- "Aggregate" toggle collapses by (instance × solver) and shows
  mean ± std, including a histogram thumbnail of objectives.

### 2.3 Bundle export

- "Download bundle" button under the results table.
- Downloads a ZIP containing:
  - `state.yaml` for each instance.
  - `run_config.json` for each unique config.
  - `results.json` (full SolveResult payloads).
  - `metrics.json` (aggregate metrics per RESEARCH_METRICS.md).
  - `git_sha.txt` with the deployed git SHA.
  - `requirements.txt` snapshot.
  - `README.md` with replay instructions.

### 2.4 Backend

- `POST /api/lab/run` — body: `{instance: <state-or-yaml>, solvers:
  list[str], run_config: RunConfig, seeds: list[int]}`. Returns
  `{run_id: str, results: list[SingleRun]}`. Synchronous; long-running
  batches should warn user not to close the tab. (Phase-3 polish:
  background job + status polling.)
- `GET /api/lab/runs/{run_id}` — return the full results bundle.
- `GET /api/lab/runs/{run_id}/bundle.zip` — return the export ZIP.
- `GET /api/lab/runs` — list recent run IDs with metadata.

---

## 3. Sub-tab — Sweep

Single instance, single solver, sweep one CP-SAT parameter across its
allowed values.

### 3.1 Inputs panel

- Instance source (same as Benchmark).
- Solver = CP-SAT (no baseline option here; sweep is internal-tuning).
- Parameter to sweep: dropdown
  (`search_branching | linearization_level | num_workers |
  random_seed | time_limit_s`).
- Value list: comma-separated input. Pre-fill with sensible defaults
  for the chosen parameter.
- Seeds per value: 1 by default, ≥10 for variance check.
- Run button.

### 3.2 Output

- Heatmap: parameter value × seed → objective (or time, toggleable).
- Box plot of objective per parameter value.
- Convergence chart (multi-line, one line per parameter value).

### 3.3 Backend

Same `POST /api/lab/run` endpoint; client constructs the cross-product
locally and submits as a flat list of (instance, solver, config) cells.

---

## 4. Sub-tab — Fairness

Deep-dive on a single solved roster's bias profile.

### 4.1 Layout

- Top: instance + solver + config metadata.
- Three-column grid:
  - **Per tier** — Gini, std, range (FTE-normalised). Each as a small
    metric card.
  - **Per individual** — sortable table: doctor, tier, FTE, weighted
    workload, deviation from tier median, on-call count, weekend count.
    Outliers highlighted (>p75 or <p25 of tier deviation).
  - **By day-of-week** — bar chart of total weighted workload per dow.
- Bottom: subspec parity panel (consultants only). Bar chart of mean
  workload per subspec.

### 4.2 Inputs

- Result picker: dropdown of recent runs from `/api/lab/runs` plus
  "current solved roster on /roster".

### 4.3 Backend

- `POST /api/metrics/fairness` — body: `{assignments: list[Row]}`,
  returns the full fairness payload.
- Or include in `/api/roster/validate` extension — but keep them
  separate for clarity.

---

## 5. Sub-tab — Scaling

Plot solve-time vs instance size.

### 5.1 Layout

- Inputs: which size sweep to run (e.g., 10 / 20 / 30 / 50 / 100
  doctors × 7 / 14 / 28 days), seeds per size.
- Run button.
- Output: log-log scatter of `T_w` vs (n_doctors × n_days). Power-law
  fit overlay with reported exponent.
- "Predict from this data" — small input where user enters a
  hypothetical instance size and reads the projected solve time.

### 5.2 Backend

`POST /api/lab/run` with the cross-product of synthetic instances
generated via `scheduler.instance.make_synthetic`. The client builds
the instances, posts the batch, displays results.

---

## 6. Sub-tab — Single run detail (`/lab/runs/:run_id`)

Reachable from the Benchmark or Fairness tab when you click a row.

### 6.1 Layout

- Header: instance name, solver, config, seed, timestamp, git SHA.
- ObjectiveBreakdown card (re-use existing component).
- ValidationPanel card (re-use existing component) showing the post-
  solve self-check result.
- RosterHeatmap (re-use existing) for visual inspection.
- "Download as bundle" button (single-run version of the batch
  bundle).

---

## 7. Backend additions

### 7.1 `RunConfig` Pydantic model

In `api/models/lab.py`:

```python
class RunConfig(BaseModel):
    time_limit_s: float = 30
    num_workers: int = 1
    random_seed: int = 0
    search_branching: Literal[
        "AUTOMATIC", "FIXED", "PORTFOLIO", "LP", "PSEUDO_COST"
    ] = "AUTOMATIC"
    linearization_level: int = 1
    cp_model_presolve: bool = True
    optimize_with_core: bool = False
    use_lns_only: bool = False
    feasibility_only: bool = False
    snapshot_assignments: bool = False
```

### 7.2 Extend `scheduler.solve(...)`

Additive kwargs:

```python
def solve(
    inst,
    *,
    ... existing kwargs ...,
    random_seed: int = 0,
    search_branching: str = "AUTOMATIC",
    linearization_level: int = 1,
    cp_model_presolve: bool = True,
    optimize_with_core: bool = False,
    use_lns_only: bool = False,
):
```

Each maps directly to a `solver.parameters.*` field. No behaviour
change at default values.

### 7.3 New endpoints

```
POST   /api/lab/run                 → run a batch, return results
GET    /api/lab/runs                → list recent runs
GET    /api/lab/runs/{id}           → single run detail
GET    /api/lab/runs/{id}/bundle.zip → reproducibility bundle
POST   /api/metrics/fairness        → compute fairness payload
POST   /api/metrics/coverage        → compute coverage payload
```

### 7.4 Persistence

- In-memory dict for the run history; LRU-cap at 50 runs to bound
  memory.
- Optional Phase-5: persist to disk under `lab_runs/` if HF Spaces
  permanent storage is configured.

---

## 8. Implementation phases (mirrors VALIDATION_PLAN)

### Phase 1 — wiring + Fairness panel (~2 days)

- Backend: `api/metrics/fairness.py` + `POST /api/metrics/fairness`
  endpoint.
- Backend: post-solve validator wired into `solve_ws` and `solve_sync`,
  attaching the validator's per-rule pass list to the SolveResult
  payload.
- Frontend: Fairness card on `/roster` (and a placeholder `/lab`
  route saying "coming soon").
- Tests: `tests/test_fairness.py` with hand-computable inputs.

### Phase 2 — `/lab/benchmark` MVP (~3 days)

- Backend: `RunConfig`, baselines, `POST /api/lab/run`,
  `GET /api/lab/runs`.
- Frontend: `/lab/benchmark` with input panel + results table. No
  bundle export yet.
- Test: 3 instances × 2 solvers × 5 seeds = 30 runs end-to-end in <60s.

### Phase 3 — bundle export + `/lab/runs/:id` (~1 day)

- Backend: `GET /api/lab/runs/{id}/bundle.zip`.
- Frontend: download button on benchmark + run-detail page.

### Phase 4 — `/lab/sweep` + `/lab/scaling` + `/lab/fairness` (~3 days)

- Implement remaining sub-tabs.
- Add coverage metric endpoint.
- Polish charts.

### Phase 5 — docs + first benchmark adapter (~2 days)

- Adapt one NSPLib instance into our YAML format.
- Add `docs/HOW_TO_REPRODUCE.md`.
- Update README with research-usage section.

---

## 9. Things to think about while building

### 9.1 Don't block the UI

Long benchmark runs (30 seeds × 30s = 15 minutes) will block the
synchronous `POST /api/lab/run`. Two options:

- **Phase-2 simplification:** show a progress toast, accept the wait,
  warn user not to close the tab.
- **Phase-3 polish:** background job + `GET /api/lab/runs/{id}` polls
  a status field. Cleaner but more code.

Start with the simple path; promote when needed.

### 9.2 Feasibility-only baselines

The greedy and random baselines won't hit our objective. They should
return SolveResult with `status="HEURISTIC"` and `objective=None`,
plus a flag indicating they're not optimisation methods. The
fairness/coverage metrics still apply.

### 9.3 Bundle replayability

The bundle needs a script to actually replay. Include
`scripts/replay_bundle.py` that:

```python
python scripts/replay_bundle.py path/to/bundle.zip
```

Unzips, reads `run_config.json`, reads each `state.yaml`, runs the
configured solver(s), compares output to `results.json`. Reports any
divergence. This script is the integration test that proves the
bundle works.

### 9.4 Don't break existing solve flow

The Solve page's existing UX is fine. The Lab is additive. Resist the
urge to "unify" the Solve and Lab solve paths — they serve different
audiences and the divergence is intentional.

---

## 10. Out of scope

- Real-time multi-user collaboration on a Lab run. Single user per
  tab is the v2 model.
- Cloud GPU. CP-SAT is CPU-bound; 8 cores on HF Spaces is fine.
- ML-based heuristic suggestions. Possibly v3 territory.
- Custom DSL for new constraints. Existing rules are toggleable;
  adding a new hard constraint requires a code change + escalation.
- Anything that requires changing the SPA shell (top bar, side nav,
  top-bar YAML menu, etc.) unless explicitly required by a Lab feature.
