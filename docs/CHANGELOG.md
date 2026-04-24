# Changelog

Append-only log. Newest at top. Each entry: date, short title, what/why.

## 2026-04-25 — FULL_DAY sessions, shift labels, rota presets, Rules shape page

**What:** Scheduled days were hard-coded as AM + PM + night on-call.
That covers clinic / ward rotas but can't express a surgeon's all-day
OR list or a 12h day/night shift pattern, and the session keys were
literally "AM" / "PM" in every export — no way to surface real clock
times. This pass closes both gaps (tier 1 + tier 2 from the proposal)
and restructures Rules around the user's mental model.

**FULL_DAY station sessions (backend):**

- New session value `FULL_DAY` alongside `AM` / `PM`. A station with
  `sessions=("FULL_DAY",)` binds one doctor for both halves of the
  day at that station — the shape needed for a surgical OR list or a
  consultant-led clinic day.
- Mutually exclusive with AM/PM (`scheduler/ui_state.py` rejects the
  combo at build time).
- Model-side: FULL_DAY is unpacked into paired AM+PM variables with
  an equality constraint (`AM == PM`), so every existing constraint
  that reasons AM or PM separately (H2, H5, H6, H7, H11) keeps working
  unchanged. H1 (coverage) is the only rule that needed tweaking — it
  counts the AM side alone to avoid double-booking.
- 4 new tests in `tests/test_full_day.py` lock in the pairing, the
  coverage arithmetic, the "consultant on FULL_DAY can't appear on
  another station same day" property, and compatibility with leave.

**Shift labels (cosmetic clock-times):**

- New `ShiftLabels` block on SessionState — human-readable names for
  `am / pm / full_day / oncall / weekend_ext / weekend_consult`.
  Default values match the historic keys so existing exports are
  unchanged. Persists through YAML round-trip.
- Changing them does **not** change solver behaviour — solver keeps
  reasoning over AM / PM / FULL_DAY / Night call.

**Rules UI — new Shape sub-tab + segment restructure:**

- New `/rules/shape` subtab is now the default when you open Rules.
  Two cards: (1) **Pick a rota pattern** — four preset tiles
  (Clinic AM/PM, 12h Day + Night, Surgical lists, 24/7 shifts) that
  set shift labels + hours + weekend toggles in one click; active
  preset is auto-detected from the current state. (2) **Shift labels**
  — direct-edit inputs for each session key. (3) an info card
  spelling out what the solver does and does not support.
- `/rules/constraints` restructured: segments are now **Nights &
  on-call** / **Weekends** / **Weekdays** — mapped to what a
  coordinator actually thinks about, not the internal "succession /
  coverage / utilisation" jargon. Each segment has an icon, a
  plain-English description, and the toggles that belong in it.
  Rules reordered within each segment so the most consequential
  toggles come first.
- Stations on `/rules/teams`: added a "Full day" chip (amber) that's
  mutually exclusive with AM/PM. Picking Full day flips the station
  to the new session shape; picking AM or PM flips it back.

**New scenario: `surgery_week`.**

- 16-doctor surgical department with three consultant-led FULL_DAY
  OR lists (OR_MAIN, OR_DAY_CASE, OR_EMERGENCY), registrar theatre
  cover (AM/PM), and junior coverage for clinic / ward round /
  post-op. First bundled scenario exercising the FULL_DAY shape.
  Solves FEASIBLE in 30 s at build time; labelled "By specialty /
  hard".

**Roadmap (explicitly NOT in this build):**

- Rotas with more than three shifts per day (early / late / twilight /
  night all on the same day) — this is tier 3 from the proposal and
  would need the solver's AM/PM enum replaced with user-defined
  shifts. Flagged in the Shape-page info card so nobody expects it.

**Test headline:** 84/84 pytest pass (was 80). `pnpm build` clean. 17
scenarios shipped (was 16).

## 2026-04-24 — Template library revamp: categories, specialties, stress tests

**What:** The old 7-scenario library was radiology-heavy and gave no
signal about which template fit which use-case. Rebuilt into 16
templates organised into four categories plus an honest difficulty
badge.

**Categories (new `category` + `tags` fields in manifest.json):**

- **Quickstart** (2) — small, solve in seconds. `clinic_week`,
  `radiology_small`.
- **By specialty** (6, new) — department-shaped templates:
  - `cardiology_week` — Invasive / Non-invasive / Electrophysiology
    subspecs; cath lab is consultant-only.
  - `anaesthesia_two_weeks` — General / Cardiac / Obstetric /
    Paediatric subspecs; theatre lists are subspec-restricted.
  - `icu_two_weeks` — single-subspec critical care, `max_oncalls=4`
    cap so the fatigue load spreads evenly.
  - `emergency_week` — 26-doctor ED with `weekend_am_pm=True` so the
    whole week runs weekend-style cover.
  - `paediatrics_two_weeks` — General / Neonatal subspecs; NICU lead
    is consultant-only.
  - `nursing_ward` (re-categorised) — same engine, renamed tiers.
- **Real-world sized** (4) — `busy_month_with_leave`,
  `teaching_hospital_week`, `regional_hospital_month`,
  `hospital_long_month`.
- **Research & benchmarks** (4, new):
  - `benchmark_nrp_small` (11×14) and `benchmark_nrp_medium` (20×28)
    — clean-room reference shapes for `/lab/scaling` + CP-SAT vs
    greedy comparisons.
  - `stress_tight_oncall` (12×28) — intentionally thin senior bench
    to probe H4 + H5 + weekday on-call coverage limits.
  - `stress_dense_leave` (18×14) — two public holidays + heavy
    overlapping leave; shows holiday-and-leave crunch behaviour.

**Honest difficulty badges:** each scenario is solved at build time
(30 s / 4 workers) and the result recorded in the manifest as
`solve_status`, `solve_time_s`, and a three-bucket `difficulty`
(`easy` / `hard` / `stress`). The Dashboard now shows a green "Solves
fast", amber "Long solve", or red "Stress test" pill on each card —
so a first-time user isn't misled into expecting a 20-second OPTIMAL
out of the 35-doctor month.

**Feasibility gate loosened:** `scripts/build_scenarios.py` no longer
aborts when a template fails to solve inside 30 s. Hard / stress-test
scenarios are a legitimate part of the library — they teach users (and
reviewers) where the CP-SAT limits are. Status lands in the manifest
either way.

**Dashboard layout:** scenarios are now rendered as four category
blocks with icon + headline + hint. The featured (first-quickstart)
card still gets a subtle highlight.

**Test headline:** 80/80 pytest still pass. `pnpm build` clean. 16
scenarios shipped (was 7).

## 2026-04-24 — Rules UX pass: 3 subtabs, preset row, fixed toggle, compact stations

**What:** Rules had seven sub-tabs (Tiers, Sub-specs, Stations, Rules,
Hours, Fairness, Priorities) — each a single card. Clicking through
all seven to set up a department was tedious. Consolidated into
three thematic pages:

- **Teams & stations** (`/rules/teams`) — combines Tiers, Sub-specs,
  and Stations as stacked cards on one page. Stations got a compact
  one-row-per-station layout (name + session chips + tier chips +
  required + reporting + delete, all inline, wraps on narrow
  screens). Old station cards were two-column with a lot of padding;
  the new row density doubles what fits on screen.
- **Rules** (`/rules/constraints`) — now grouped into three themes
  (Succession · Coverage · Utilisation) with header hints, so the
  user sees the shape of the ruleset rather than nine undifferentiated
  toggles. Added a **Strict / Balanced / Relaxed preset row** at the
  top right that bulk-sets the toggles to a known-good combo —
  surfaces active preset when the config matches one.
- **Hours & weights** (`/rules/weights`) — combines Hours, Fairness
  (workload weights), and Priorities (soft-weight coefficients).

Old URLs (`/rules/tiers`, `/subspecs`, `/stations`, `/hours`,
`/fairness`, `/priorities`) redirect to the new pages so bookmarks
and external links still work.

**Fixed toggle rendering:** The inline toggle switch used
`translate-x-[22px]` on an absolutely-positioned thumb. In some
layouts the thumb rendered visibly outside the purple track. New
`<Toggle>` primitive in `ui/components/ui/toggle.tsx` uses flex
layout with padding — thumb is clamped to the inner padded box via
`justify-start` / `justify-end`, no translate math, impossible to
overflow. Used on the Rules page; the old toggle is gone.

**Test headline:** 80/80 pytest still pass (backend untouched).
`pnpm build` clean.

## 2026-04-24 — First-user UX pass: nav, dashboard, calendar gestures, export preview

**What:** The app's front-end landed after a long product/engineering
push and it showed — a first-time user's path into the tool was
littered with accordions to expand, tiny date-input boxes to type
into, and button walls with no context. This pass removes the
tone-deaf welcome flow, turns the side nav into a flat always-on
pill, and replaces the most tedious data-entry screens with
calendar-gesture UIs.

**Side nav:**
- Always expanded (no collapse button, no hover-to-reveal). Fits
  comfortably at `w-36` on the right rail.
- Labels only, no subtext. The old "Setup · per-period" / "Rules ·
  department" / "Lab · benchmark" hints read like footnotes and
  added noise.
- `useUIStore.navExpanded` / `toggleNav` deleted as dead state.
- Main content now gets a `md:pr-44` to avoid overlapping the fixed
  pill.

**Dashboard:**
- Scenarios are now the first thing on the page, below a short
  status-aware headline. A first-timer sees "Pick a template" and
  three loadable cards before anything else.
- Two side-by-side cards under the grid: "Load a YAML" (smaller
  drop-zone + Load/Save buttons) and "Next step" (a single big
  context-aware CTA: Setup / Solve / Roster depending on current
  state).
- The old 4-step "Getting started" accordion is now collapsed by
  default and accessible from a dotted link on the Next-step card.
  Default `gettingStartedOpen` flipped from `true` to `false` in
  the persisted UI store.

**Setup → When:**
- Keep the date + number-of-days + end-date inputs (fastest for
  exact input), but add a two-month calendar below:
  - **Drag** across days to set the horizon (start = earliest day,
    n_days = range length, clamped to 90).
  - **Single click outside the current horizon** sets a new start
    date while preserving length — one gesture to "roll the roster
    forward a week".
  - **Single click inside the horizon** toggles the day as a public
    holiday (visible as amber, falls under weekend rules).
  - Month ←/→ nav, "Today" button, colour-coded legend.
  - Works on touch (`onTouchStart` / `onTouchMove` + `elementFromPoint`).

**Setup → Blocks:**
- Replaced the form-heavy table-first layout with a **doctor × day
  grid** as the primary surface. Rows = doctors (filterable),
  columns = days across the current horizon.
- Pick a block type from the chip row (Leave / No on-call / No AM /
  No PM / Prefer AM / Prefer PM), then **drag across a row** to
  apply that type to a range. Single-click a cell of the same type
  to remove it (with auto split/trim when the cell is in the middle
  of a multi-day block).
- The old table + CSV-paste controls moved into a collapsed
  "Advanced" drawer at the bottom. Manual rows still work for the
  5% of cases the grid can't express (e.g., mid-range-type changes).
- Colour-coded per block type so overlaps are legible; weekend
  columns are shaded; month-start columns get a subtle left rule.

**Export:**
- Added a **visible preview card** at the top: roster grid view
  (doctors × days, scrollable, first-of-month ticks, weekend
  shading) with a Grid/List toggle. You can audit the output
  before exporting instead of having to open Roster in a
  second tab.
- The button wall was reorganised into three purpose-labelled
  cards — **Files** (JSON / CSV / Calendar .ics), **Print &
  share** (Print preview / Copy YAML / Copy share link),
  **Distribute** (per-doctor mailto list now lives inline in a
  compact scrollable list rather than its own giant card).
- Empty-state unchanged (still points to Solve).

**Rules:** deliberately unchanged in this pass. The user's "too
tedious" complaint is real but the right fix is a separate
redesign — not part of this increment.

**Test headline:** 80/80 pytest still pass (backend untouched).
`pnpm build` clean. No new dependencies.

## 2026-04-24 — /lab/scaling + UK NHS WTD compliance module

**What:** Two closed gaps from
[`docs/BRIEFING_2026-04-23.md §4`](BRIEFING_2026-04-23.md) — §4.4
(scaling sub-tab) and §4.3 (regulatory-conformance module).

**`/lab/scaling` — solve time vs problem size:**

- New sub-tab in the Lab. User picks doctor counts × day counts × seeds;
  backend runs CP-SAT against each synthetic instance from
  `make_synthetic`, returns (wall_time, objective, first_feasible_s)
  per cell + a log-log power-law fit T = a·N^b (N = doctors × days) with
  R² reported.
- Prediction tool: plug a hypothetical (doctors × days) into the fit
  and read the projected solve time. Flags cells that hit the time
  cap because those bias the exponent downward.
- Fit is ordinary-least-squares in log-log space via stdlib `math`.
  No numpy/scipy dep. Handles the degenerate cases (<2 points, all
  x-values identical, all runs errored).
- New endpoint `POST /api/lab/scaling/run` — deliberately separate
  from `/api/lab/run` because scaling doesn't need the
  fairness/coverage drill-downs. Lightweight response; 40-cell cap so
  nobody accidentally burns a 30-minute wall clock.
- 7 new tests in `tests/test_lab_scaling.py` (fit recovery, degenerate
  inputs, endpoint smoke, empty-grid 422).

**UK junior-doctor + EU WTD compliance module:**

- New package `api/compliance/` with `uk_wtd.py` encoding the six
  statutory rules from [`docs/INDUSTRY_CONTEXT.md §5`](INDUSTRY_CONTEXT.md):
  W1 avg 48 h/week, W2 72 h in any 7 days, W3 13 h per shift, W4 11 h
  rest between shifts, W5 ≤ 4 consecutive long days, W6 ≤ 7
  consecutive nights.
- Shift clock times approximated from `HoursConfig` + conventional
  start times (AM 08:00, PM 13:00, on-call 20:00). AM+PM on same date
  collapse to one shift so W4 doesn't flag the 1 h "lunch" gap.
- New endpoint `POST /api/compliance/uk_wtd` — accepts `{assignments,
  config?}` where `config` is a partial `WtdConfig` override (lets a
  researcher ablate one rule at a time). Returns grouped violations +
  echoed config for the bundle.
- `WtdPanel` component now renders on `/roster` next to the fairness
  card. Green/amber/red based on severity; expandable detail table.
  Reporting-only — the solver does NOT enforce these rules, which is
  documented prominently.
- 17 new tests in `tests/test_uk_wtd.py` (hand-computed fixtures for
  each rule + multi-doctor scoping + endpoint smoke + config patch).

**Gaps this explicitly does not close:**

- **MILP baseline (PuLP+CBC).** Deferred because it needs a CBC
  system-package on HF Space that we can't test locally. Still next
  on the briefing's ranked list.
- **NSPLib / Curtois benchmark adapter.** Requires sourcing instances
  and writing `lib/objective_translator.py`. Separate scope.
- **WTD enforcement inside CP-SAT.** The module is post-solve audit
  only. Making it a hard constraint needs more careful model work —
  e.g. W4 currently surfaces H7's "junior oncall PM" as a genuine
  statutory breach, which is a finding the paper should discuss
  before we start ignoring it.

**Test headline:** 80/80 pytest pass (was 56). `pnpm build` clean.

## 2026-04-23 — Lab: live per-cell progress + persistent batch state

**What:** Two bugs in `/lab/benchmark`:

1. **No progression during a run** — pressing Run sat idle for the
   full CP-SAT time limit then dumped the final result. The entire
   batch was one `POST /api/lab/run` with no intermediate feedback.
2. **Results disappeared on tab switch** — the `useMutation` cache
   was component-local. Leaving `/lab/benchmark` even briefly
   wiped the run.

**Fix — streaming batch execution:**
- Batches are now executed one cell at a time. The client fires
  `POST /api/lab/run` with a single `(solver, seed)` tuple per call,
  updates the store on each completion, and renders the results
  table live as each row lands.
- Baselines (greedy, random_repair) run first inside each batch plan
  so fast cells populate the reliability cards before the slow
  CP-SAT cell starts.
- New per-cell progress card:
  - Overall progress bar (N/M cells done)
  - Elapsed timer + ETA (data-driven — initial estimate uses
    time_limit_s for CP-SAT + ~1s per baseline, then recalculates
    from observed wall times as cells finish)
  - Current cell mini-progress bar with "N seconds / cap seconds max"
  - Coloured by solver (same palette as the comparison chart)

**Fix — persistent state:**
- New Zustand store `ui/src/store/labBatch.ts`. All batch state
  (runs, aggregates, progress, current cell) lives at module scope
  so tab switches no longer lose results.
- Aggregates (feasibility rate, mean objective, mean shortfall,
  quality ratios) are recomputed inside the store on every cell
  completion — reliability banner + comparison charts always show
  the latest numbers, not just what the last `POST` returned.
- Bundle download uses the latest cell's `batch_id`; composite-
  bundle (across all cells in a logical batch) is a follow-up.

**Non-goals (intentionally deferred):**
- No WebSocket / SSE streaming of CP-SAT intermediate solutions
  inside a single cell. CP-SAT runs in the cell's POST and finishes
  in `time_limit_s` either way; the progress bar communicates
  "elapsed of max" clearly enough for now.
- No multi-cell composite bundle. Each cell still makes its own
  bundle on the backend; the UI exposes the most-recent one.

**No backend changes.** 56/56 pytest still pass. `pnpm build` clean.

## 2026-04-23 — Lab UX: intros, comparison charts, richer visuals

**What:** Every Lab sub-tab now has a reading-guide card and real
charts. Fixes "there is really very little given to understand what
is going on" — the Lab used to be table-heavy and assumed you knew
the NRP reliability metrics by heart.

**`/lab/benchmark`:**
- **Reading-guide card** at the top — one-paragraph explanation of
  what the batch does + a bulleted guide to Feasibility rate,
  Coverage shortfall, Objective, and Quality ratio.
- **Solver comparison chart** — three side-by-side bar charts (one
  per metric), bars coloured by solver. A solver that's green on all
  three panels is "production-ready on this instance."
- **Run scatter** — objective vs wall time, one dot per (solver ×
  seed). Tight cluster = stable; big spread = raise the seed count
  before publishing a mean.

**`/lab/sweep`:**
- **Reading-guide card** — what sweeping does, what ΔZ_θ + ΔT_θ
  mean, how to read error-bar ranges.
- **Aggregate bar with whiskers** — mean objective per value,
  whiskers span min → max across seeds. Current winner highlighted
  in emerald with a reference line at its mean.
- **Mean wall-time chart** — same treatment on wall time so the
  user can spot "lower objective AND lower time = free win" cells.
- **All-runs scatter** — one dot per (value × seed), exposes bimodal
  behaviour the summary table hides.
- Summary table now highlights the best-objective + best-time rows.
- Header call-out: best value + its mean objective, fastest value +
  its mean time.

**`/lab/fairness`:**
- **Reading-guide card** — what Gini / CV / range / per-individual
  Δ mean in plain words, with "healthy" vs "smell" thresholds.
- **Per-individual FTE-normalised workload chart** — one bar per
  doctor, coloured by tier, sorted within-tier by Δ (most over-
  worked to most under-worked). Dashed per-tier median reference
  lines so outliers are obvious at a glance. Bars labelled with
  FTE if it's not 1.0.
- Retains the existing `FairnessView` (per-tier cards, DoW bar
  chart, subspec parity) and coverage audit below.

**Shared:**
- New Lab colour palette — each solver has one colour across all
  Lab charts (CP-SAT indigo, greedy teal, random_repair amber),
  each tier has one colour on fairness charts. Makes
  cross-chart tracking trivial.
- No backend changes; no test changes; 56/56 pytest still pass.
  Frontend build 884 KB JS / 259 KB gzip (~35 KB larger for the
  extra chart code, acceptable).

## 2026-04-23 — Tuning sweep: symmetry / decision-strategy / redundant aggregates

**What:** Added three model-level tuning toggles to `scheduler.solve()`:
`symmetry_break`, `decision_strategy`, `redundant_aggregates`. Plumbed
them through `RunConfig` → `api/lab/batch.py` and exposed checkboxes
in `/lab/benchmark`'s Advanced panel. Wrote a systematic sweep runner
at `scripts/benchmark_tuning.py` and ran it across all 7 scenarios × 5
variants × 2 seeds × 30s budget (70 cells, ~35 min).

**Honest null result.** Full report at
[`docs/TUNING_RESULTS.md`](TUNING_RESULTS.md). TL;DR:

- **`symmetry_break`** actively *hurts* on every scenario with tier-level
  fairness weights (nursing_ward +22.6%, busy_month +32%,
  teaching_hospital +192%). Only helps on `clinic_week` (−13.5%) where
  H8 + weekday-on-call are disabled and the fairness max−min terms
  have no grip. Root cause: count-based lex-order directly conflicts
  with the objective's preference for equal workload. Assignment-
  matrix-level lex-order would be the proper fix but that's a
  multi-day rewrite.
- **`oncall_first`** and **`redundant_aggregates`** produced zero lift
  on these scenarios at `num_workers=1` + 30s. No regression either.
- **`regional_hospital_month`** (30×28) and **`hospital_long_month`**
  (35×28) returned `UNKNOWN` on every variant at `num_workers=1`.
  Deterministic single-worker runs aren't viable for month-scale
  problems — the Lab UI's default `num_workers=8` stays the right
  production setting.

**Recommendation:** all three toggles default OFF. Kept exposed for
researchers measuring on differently-shaped instances, with clear
experimental labelling and a pointer to `TUNING_RESULTS.md`.

**Deliverable value:** the sweep itself is the win — we now have
honest baseline data against which any future tuning work can be
measured, not guessed at.

## 2026-04-23 — Split GitHub ↔ HF deploy (docs stripped from Space)

**What:** HF Space deploys now go through `scripts/deploy_hf.sh`,
which rebuilds a local `hf-deploy` branch from `react-ui` with the
entire `docs/` tree removed and force-pushes it to HF's `main`.
GitHub stays the canonical source of truth with full docs; HF
ships only what the running app needs.

**Why:** The HF Space is public-facing and should expose the minimum
surface — research notes, validation plans, internal briefings, and
the CHANGELOG are valuable in the GitHub repo but not on the hosted
app. Manual web-UI deletions kept getting stomped by `git push`; the
new script makes the split automatic.

**Workflow:**
```bash
git push origin react-ui          # GitHub — full repo
./scripts/deploy_hf.sh             # HF — docs-stripped, polls to RUNNING
```

The script:
1. Fails if the working tree has uncommitted changes.
2. Rebuilds `hf-deploy` from the latest `react-ui` (or a named branch).
3. `git rm -r docs`, single commit with a `Deploy <sha> to HF` message.
4. Force-pushes `hf-deploy:main` → HF (canonical history is on
   GitHub; HF's history is intentionally disposable).
5. Polls `huggingface.co/api/spaces/…/runtime` until
   `stage == RUNNING`.
6. Returns to the caller's original branch.

No scheduler / solver / UI changes — pure deploy plumbing.

## 2026-04-23 — Scenario refresh: 7 scenarios, rescaled stations

**What:** Reorganised the scenario picker so every pre-built scenario
renders with the same styling (no NRP-benchmark chip, no caveat
banner), fixed station-demand mismatches on the 30-doctor scenarios,
and added two more shapes so the picker covers tiny team → very-large
team.

**Final scenario list (7):**
1. `clinic_week` · 10 doctors × 7 days · outpatient clinic (NEW)
2. `radiology_small` · 15 × 7 · unchanged
3. `nursing_ward` · 17 × 14 · unchanged
4. `busy_month_with_leave` · 22 × 14 · unchanged
5. `teaching_hospital_week` · 30 × 7 · renamed from `nsplib_shaped_n30_7`
6. `regional_hospital_month` · 30 × 28 · renamed from `curtois_shaped_bcv`
7. `hospital_long_month` · 35 × 28 · biggest bundled scenario (NEW)

**Bugs fixed:**
- The 30-doctor scenarios inherited the 8-station setup from the
  15-doctor `radiology_small`, producing ~18 weekday station slots
  vs ~30 doctors needing duty under H11. Half the team was forced
  idle, dominating the objective (teaching_hospital was 5475 pre-fix).
  Station demand rescaled via `_big_radiology_stations` to ~28
  weekday slots, matching the team size. New objective ~1580 — a
  3.4× improvement. Same fix applied to `regional_hospital_month`:
  objective went from 16005 → 4550.
- `clinic_week` turns off H8 (weekend coverage) and the weekday
  on-call rule, because a 10-person outpatient clinic can't
  realistically staff overnight + weekend cover. Previously
  INFEASIBLE; now solves to OPTIMAL in 0.4s.

**Removed:**
- The "NRP benchmark" / "Industry-benchmark-shaped" dedicated UI
  section with violet chips, reference lines, and caveat expanders.
  `BenchmarkScenariosSection`, `benchmark_family` / `_reference` /
  `_caveat` fields on `ScenarioSummary`, and the amber "honest
  framing" banner are all gone. Every scenario renders in the same
  3-column card grid now.

**Tests:** `test_self_check.py` parametrize list updated to the 7
new IDs. Heavy scenarios (`regional_hospital_month`,
`hospital_long_month`) run with `feasibility_only + 40s`. Total
56/56 pytest pass. `pnpm build` clean.

## 2026-04-23 — Benchmark-shaped scenarios (NSPLib + Curtois envelopes)

**What:** Two new scenarios in the Dashboard's scenario picker so a
reviewer can click "Curtois-shaped · BCV 4-week" and immediately see
an NRP-literature-sized problem go through CP-SAT + baselines +
fairness + coverage. Addresses part of BRIEFING §4.1 — not a full
NSPLib/Curtois adapter, but a legible "this tool handles
industry-sized problems" demo.

**New scenarios:**
- `nsplib_shaped_n30_7` — 30 doctors × 7 days, NSPLib's Vanhoucke &
  Maenhout (2007) n30/d7/s3 parameter envelope. Three skill classes
  (our tiers), ~5% leave density, one preferred-shift request.
  Solves to FEASIBLE in <30s.
- `curtois_shaped_bcv` — 30 doctors × 28 days, Curtois NRP
  collection's BCV (Belgian Children's Valentine) family envelope.
  Mixed leave + call blocks + soft preferences + one 0.5-FTE
  part-timer + one `max_oncalls=3` cap. The stress-test scenario
  for fairness and coverage (first bundled scenario that exercises
  FTE-normalisation non-trivially). Solves to FEASIBLE in <30s with
  num_workers=4.

**Honest framing:** Both scenarios are shaped to match the published
family's parameter envelope — NOT bit-for-bit imports of any
specific instance. The Dashboard card carries a "⚠ Shaped, not
imported" expander with the full caveat so nobody mistakes this
for a native benchmark adapter. The true adapter with penalty-score
translation remains BRIEFING §4.1 follow-up.

**Manifest schema extended** with three optional fields:
`benchmark_family`, `benchmark_reference`, `benchmark_caveat`.
Unchanged for the three original scenarios.

**Dashboard UI:**
- Benchmark-shaped scenarios now render in a dedicated
  "Industry-benchmark-shaped scenarios" section below the original
  three, with a violet family-name chip, reference line, and an
  always-visible amber "honest framing" banner at the section top.
- Per-card "⚠ Shaped, not imported" details expander.

**Tests:** `test_self_check.py` parametrize list grows to 5 — all
scenarios, benchmark-shaped and original, must land OPTIMAL/FEASIBLE
with a green self-check. Heavy scenarios run with feasibility_only +
40s time-limit so the regression suite stays under ~2min on CI.
Total: 54/54 pytest pass; `pnpm build` clean.

## 2026-04-23 — Validation Phase 5: research docs + briefing

**What:** Closing docs pass for the validation work.
- `docs/HOW_TO_REPRODUCE.md` — step-by-step replay of a Lab bundle
  on a fresh checkout, with determinism guarantees and a list of
  what replay does NOT verify.
- `docs/CITING.md` — BibTeX stubs (solver + OR-Tools) plus
  methodological citation pointers and the regulatory caveat.
- `README.md` gains a **Research usage** section pointing at
  `/lab/*` and summarising the self-check / bundle workflow.
- `docs/BRIEFING_2026-04-23.md` — single-doc progress summary for
  the user after the multi-phase push: what shipped, commit list,
  goal-vs-actual against `VALIDATION_PLAN §4`, metric-by-metric
  reliability scorecard (17 of 20 first-class NRP metrics green),
  and three recommended follow-ups (NSPLib adapter, PuLP+CBC MILP
  baseline, regulatory-conformance module).

**Tests:** unchanged (52/52 pass). No code changes.

## 2026-04-23 — Validation Phase 4: /lab/sweep + /lab/fairness subtabs

**What:** Two new Lab sub-tabs flesh out the research surface per
[`docs/LAB_TAB_SPEC.md §§3–4`](LAB_TAB_SPEC.md).

**/lab/sweep — parameter sensitivity (RESEARCH_METRICS §6.2):**
- Sweeps one CP-SAT lever (search_branching / linearization_level /
  random_seed / num_workers / time_limit_s) across a user-specified
  value list.
- Fires one `POST /api/lab/run` per value (reusing the Phase 2
  endpoint; no new backend required). Each value contributes one
  BatchSummary to the history list.
- Surfaces ΔZ_θ and ΔT_θ — the sensitivity metrics from
  `docs/RESEARCH_METRICS.md §6.2` — plus per-value mean objective /
  min / max / mean wall-time and a line chart of objectives.

**/lab/fairness — deep-dive (LAB_TAB_SPEC §4):**
- Run-picker (batch dropdown → solver × seed dropdown) over the
  in-memory history.
- Renders the SingleRunDetail's already-computed `fairness` payload
  via the refactored `FairnessView` pure-render component. No extra
  backend roundtrip.
- Bonus: Coverage-audit panel showing shortfall / over / top-10 gap
  list per result — the §5.1b counterpart that was only aggregated
  (mean) on the main benchmark table.
- `components/FairnessPanel.tsx` refactored to export `FairnessView`
  for reuse; the old Panel still works on `/roster`.

**Front-end:** `Lab` layout now shows three sub-tabs
(Benchmark / Sweep / Fairness). Scaling sub-tab is deferred.

**Reliability posture after Phase 4:**
- Parameter sensitivity is testable (ΔZ_θ / ΔT_θ exposed).
- Every run's coverage + fairness drill-downs are reachable with
  one click from the Lab run history — reviewers can audit any
  published claim at the per-individual level.

## 2026-04-23 — Validation Phase 3: reproducibility bundle + CP-SAT lever exposure

**What:** A Lab batch now downloads as a replayable ZIP and exposes
every CP-SAT parameter a reviewer needs to reproduce a run. Closes
Phase 3 of [`docs/VALIDATION_PLAN.md`](VALIDATION_PLAN.md).

**Scheduler — additive CP-SAT kwargs (`scheduler/model.py`):**
- `random_seed`, `search_branching`, `linearization_level`,
  `cp_model_presolve`, `optimize_with_core`, `use_lns_only`. Each
  maps straight onto `solver.parameters.*`. Defaults unchanged, so
  every existing call site behaves identically.
- `search_branching` accepts the SearchBranching enum names
  (AUTOMATIC / FIXED_SEARCH / PORTFOLIO_SEARCH / LP_SEARCH /
  PSEUDO_COST_SEARCH / PORTFOLIO_WITH_QUICK_RESTART_SEARCH); unknown
  values fall back to AUTOMATIC.

**API — RunConfig + bundle export:**
- `api/models/lab.py` `RunConfig` expanded with the six CP-SAT levers.
- `api/lab/batch.py` threads every lever through to `scheduler.solve`.
  Per-seed adjustment: `random_seed_effective = base_seed + iter_seed`
  so one RunConfig can sweep seeds without mutating the record.
- `api/lab/bundle.py` + `GET /api/lab/runs/{batch_id}/bundle.zip`:
  returns a ZIP with `state.yaml`, `run_config.json`, `results.json`,
  `git_sha.txt`, `requirements.txt`, and a README with the exact
  `git checkout <sha> && python scripts/replay_bundle.py` workflow.
- `api/main.GIT_SHA` resolved once at import time from
  `$GIT_SHA` → `$SPACE_COMMIT` → `git rev-parse HEAD` → `"unknown"`.
  Exposed via `/api/health`.
- `_StoredBatch` now freezes the YAML at batch-run time so later
  state edits don't poison the bundle.

**Replay (`scripts/replay_bundle.py`):**
- Unpacks a bundle, re-runs every (solver × seed) cell against the
  recorded RunConfig, diffs status / objective / self_check_ok /
  coverage_shortfall / coverage_over. Zero divergences = bit-for-bit
  reproduction (with `num_workers=1`).

**Front-end:**
- `/lab/benchmark` gains a collapsible **Advanced CP-SAT knobs**
  section (search_branching dropdown, linearization 0–2, three
  presolve/core/lns checkboxes) and a **Download bundle** button
  that fires `GET /api/lab/runs/.../bundle.zip`.

**Tests:** 5 new (`tests/test_lab_bundle.py`) —
  - Determinism: two back-to-back runs with num_workers=1 + fixed seed
    produce identical objective + assignment count.
  - Bundle manifest: ZIP contains every artefact VALIDATION_PLAN §1.3
    specifies.
  - Bundle README embeds the batch's git SHA.
  - `/api/health` exposes `git_sha`.
  - 404 on unknown batch.
- 52/52 pytest pass; `pnpm build` clean.

**Reliability posture after Phase 3:** Bundle + replay script deliver
the "solutions are reproducible" pillar from VALIDATION_PLAN §1.
Determinism is documented + tested; a reviewer reading
`HOW_TO_REPRODUCE.md` (Phase 5) can now re-generate any published
number.

## 2026-04-23 — Validation Phase 2: baselines + /lab/benchmark + coverage metrics

**What:** The research tab's first real surface. Researchers can now
pick a scenario, press Run, and see CP-SAT vs a greedy / random-repair
baseline with the full set of industry-standard reliability metrics.
This closes Phase 2 of [`docs/VALIDATION_PLAN.md`](VALIDATION_PLAN.md).

**Baselines (`scheduler/baselines.py`):**
- `greedy_baseline(inst)` — weekend H8 → weekday on-call → station
  coverage, picking the lowest-load eligible doctor at each step.
  Respects H3 / H10 / H12 / H13 exactly; approximates H4 / H5 with
  no look-ahead.
- `random_repair_baseline(inst, seed)` — random assignment +
  fill-in-the-blanks repair loop. Only targets H1 / H3 / H10; H4 / H5 /
  H8 are ignored by design (this is the weak baseline).
- Both return `SolveResult`-compatible dataclasses with
  `status="HEURISTIC"` and `objective=None`. The post-solve self-check
  flags their violations exactly as it would for CP-SAT, so the Lab's
  feasibility rate is directly comparable across methods.

**Coverage metrics (`api/metrics/coverage.py`, `POST /api/metrics/coverage`):**
- Shortfall / over-coverage per [`docs/RESEARCH_METRICS.md §5.1b`](RESEARCH_METRICS.md)
  and [`docs/INDUSTRY_CONTEXT.md §3`](INDUSTRY_CONTEXT.md).
- Per-station breakdown + top-20 (date, station, session) gap list so
  the UI can drill into where a heuristic is failing.

**Lab batch runner:**
- `api/models/lab.py` — `RunConfig`, `BatchRunRequest`, `SingleRun`,
  `BatchSummary`, `SingleRunDetail`, `RunHistoryEntry`.
- `api/lab/batch.py` — single-process serial execution over a
  cross-product of solvers × seeds. Each run computes self-check +
  coverage + fairness and stores them. Aggregates feasibility rate,
  mean objective, mean shortfall, and quality ratio
  Q = Z<sub>baseline</sub> / Z<sub>ours</sub> per
  [`docs/RESEARCH_METRICS.md §7`](RESEARCH_METRICS.md).
- In-memory LRU store (cap 50 batches). Disk persistence + bundle
  export land in Phase 3.
- Endpoints: `POST /api/lab/run`, `GET /api/lab/runs`,
  `GET /api/lab/runs/{batch_id}`, `GET /api/lab/runs/{batch_id}/details/{run_id}`.

**Front-end (`/lab/benchmark`):**
- New top-level `/lab` route (beaker icon in side + bottom nav).
- Benchmark MVP: solver multi-select + comma-separated seed list +
  time-limit / workers / feasibility-only knobs; per-batch
  reliability cards (feasibility rate %, mean objective, mean
  shortfall) coloured green when the method satisfies all industry
  reliability thresholds; quality-ratio chips; per-run results table
  with self-check ✓ / ✗ and coverage shortfall / over columns;
  recent-batches sidebar.

**Industry-reliability metrics status (the question you asked):**
- **Feasibility rate per method** — computed, tested, surfaced
  (`test_lab_batch::test_cpsat_vs_greedy_smoke`).
- **Quality ratio Q** — computed per batch, surfaced in the
  reliability banner. Only populated when both solvers return an
  objective; greedy / random_repair return `None`, so for now Q is
  only meaningful when comparing CP-SAT against a future MILP
  baseline (Phase 2.5 / 4).
- **Coverage shortfall + over-coverage** — first-class metric, tested
  against a hand-constructed fixture (4 tests), reported per-run in
  the Lab table, per-station breakdown stored in the batch detail.
- **Gini + CV + range + std + FTE normalisation** — already shipped
  in Phase 1, tested.
- **Absolute headroom** (replaces relative optimality gap) — already
  shipped.
- **INRC-II penalty score + Curtois translator** — not yet
  implemented (needs a benchmark-instance adapter; flagged for
  Phase 4/5).
- **Regulatory-conformance (UK WTD / ACGME)** — still future work;
  current coverage + fairness are not a substitute.
- **PuLP + CBC MILP baseline** — not yet implemented. It's the #1
  priority baseline in [`docs/INDUSTRY_CONTEXT.md §6`](INDUSTRY_CONTEXT.md);
  scoped as Phase 2.5 because it requires a new runtime dep + a full
  MILP encoding of H1–H15. Will enable the meaningful Q metric.

**Tests:** 47/47 pytest pass (32 existing + 6 baselines + 4 coverage +
5 lab-batch). `pnpm build` clean (824 KB / 244 KB gzip).

## 2026-04-23 — Validation Phase 1: self-check + fairness audit

**What:** Every solve now carries an automated hard-constraint audit,
and `/roster` grows an FTE-aware fairness/bias panel. This is Phase 1
of [`docs/VALIDATION_PLAN.md`](VALIDATION_PLAN.md).

**Feasibility receipt (validator-in-the-loop):**
- `api.sessions.build_self_check(...)` runs `api.validator.validate`
  over the solver's output and returns a structured
  `SolverSelfCheck { ok, violation_count, rules_passed, rules_failed,
  violations[] }`.
- `SolveResultPayload` gains `self_check` (non-null whenever the
  solver returned assignments).
- A failed self-check is logged at WARNING — it means the CP-SAT model
  and the validator disagree, which is always a bug to investigate.
- Front-end: `SelfCheckBadge` on `/solve` shows green-with-rule-chips
  on pass and a loud red violations list with the failed-rule names
  on fail.
- Test: `tests/test_self_check.py` runs all three scenarios end-to-end
  and asserts the self-check is green; a second test deliberately
  tampers with the output and asserts the validator catches it.

**Fairness metrics:**
- New `api/metrics/fairness.py` computes per-tier Gini + CV + range +
  std + mean over FTE-normalised weighted workload. Formulae follow
  [`docs/RESEARCH_METRICS.md §4`](RESEARCH_METRICS.md). CV added
  alongside Gini so reports are cross-comparable with both
  econ-flavoured and OR-flavoured NRP papers
  (see [`docs/INDUSTRY_CONTEXT.md §3`](INDUSTRY_CONTEXT.md)).
- Per-individual: delta from tier median, flagged as outliers if
  outside the top/bottom quartile. FTE normalisation flattens
  part-timers correctly (hand-computed test fixture).
- Day-of-week load distribution per tier (surfaces structural
  "Mondays are heavy" bias). Consultant subspec-parity table.
- `POST /api/metrics/fairness` endpoint (pure function over
  assignments, uses current session's doctor/weight metadata).
- Front-end: `FairnessPanel` on `/roster` below the Workload +
  Objective cards. Re-fires on any snapshot or draft-edit change.
- Test: `tests/test_fairness.py` covers Gini (hand-computed 10/60),
  CV, FTE normalisation, DoW bucketing, subspec parity.

**Non-changes (on purpose):**
- Scheduler internals untouched.
- Existing 6 SPA routes unchanged — validator output is additive.
- No backwards-incompatible API changes; `self_check` is optional
  on the payload.

**Tests:** 32/32 pytest pass (21 legacy + 7 fairness + 4 self-check).
`pnpm build` clean.

## 2026-04-23 — Validation & research-tooling planning

**What:** Five new design docs scoping the validation work needed
before this can be published as a research instrument:

- `docs/AGENT_HANDOFF.md` — entry-point brief for the next agent
  (mirrors `AGENT_PROMPT.md` style).
- `docs/INDUSTRY_CONTEXT.md` — literature-grounded background. NRP
  terminology, public benchmarks (Curtois NRP collection + INRC-II +
  NSPLib), standard fairness metrics (CV alongside Gini),
  De Causmaecker / Vanden Berghe constraint taxonomy mapped onto our
  H1–H15, regulatory frameworks (UK WTD, ACGME, California AB394),
  baseline solution methods, recent (2020–2025) trends. Synthesised
  from a research-agent literature review; URLs flagged for
  pre-publication verification.
- `docs/VALIDATION_PLAN.md` — strategic plan: three pillars
  (feasibility, quality, reproducibility), what we have today, gaps
  and risks, phased roadmap (~11 days for one agent). Updated to
  adopt INRC-II / Curtois / NSPLib as the benchmark suite and
  PuLP+CBC MILP as the headline baseline.
- `docs/RESEARCH_METRICS.md` — formal definitions of every metric to
  be computed: solution-quality, performance, scalability, fairness
  (FTE-normalised Gini AND CV — both reported), coverage (with
  shortfall + over-coverage as separate metrics), multi-seed
  robustness, parameter-sensitivity, baseline-comparison metrics, and
  benchmark-native scoring (INRC-II + Curtois translators).
- `docs/LAB_TAB_SPEC.md` — concrete UI + API spec for a new `/lab`
  route with sub-tabs Benchmark / Sweep / Fairness / Scaling and a
  reproducibility-bundle export.

**Why:** v2 is feature-complete from an end-user perspective. Before
academic publication or hospital pilot, three things need to be
defensible:
1. Solutions are feasible (post-solve validator-in-the-loop).
2. Solutions are competitive (vs greedy / random baselines on a
   public benchmark like NSPLib).
3. Solutions are reproducible (RunConfig with CP-SAT parameter
   exposure, bundle export with git SHA + deps).

The next agent picks up from `AGENT_HANDOFF.md`.

## 2026-04-23 — Continue solving uses real warm-start

**What:** `scheduler.model.solve()` gains a `warm_start` kwarg
(additive). When provided, hints CP-SAT via `model.AddHint(var,
value)` for each matched bool variable. The WS `/api/solve` start
message and the REST `/api/solve/run` body both gained a
`mode: "new" | "continue"` field; on continue, the server rebuilds
the warm-start dict from `session.last_solve.assignments` and feeds
it through.

**Why:** Previous Continue behaviour was 'search again from scratch'.
With warm-start, the first improving event in the new stream matches
the previous best, and subsequent events push lower. Combined with
the no-regress guard from earlier (store rolls back if the new search
ends higher), Continue truly continues.

**Tests:** 21/21 pytest pass. `warm_start` defaults to `None` so
legacy callers (existing tests, benchmark script) are untouched.

## 2026-04-23 — Manual edit mode + hard-constraint validator

**What:** Users can now edit a solved roster manually and see
violations live.

- `api/validator.py` — pure-Python validator over hard constraints
  (H1, H2, H3, H4, H5, H8, H10, H12, H13 + weekday on-call rule).
  Walks an arbitrary AssignmentRow list, returns structured
  `{rule, severity, location, message}` violations.
- `POST /api/roster/validate` — thin REST wrapper.
- `ui/src/store/draft.ts` — Zustand store for draft assignments and
  validation state.
- `components/CellEditor.tsx` — modal popover for swapping per-cell
  assignments. Filters role options by tier × eligible_stations.
- `components/ValidationPanel.tsx` — green chips for rules satisfied,
  red list for violations.
- `Roster.tsx` — "Edit a new version" button forks the current
  snapshot into a draft; debounced 400ms revalidation on every edit;
  Reset / Exit buttons return to solver result.

**Why:** Researchers and roster coordinators wanted to test
"what if we swap A and B?" without a full re-solve, and immediately
see whether the change breaks any hard constraint.

## 2026-04-23 — Optimality gap → "Improvement headroom"

**What:** Replaced the relative optimality-gap percentage with an
absolute "Improvement headroom" (objective − bound, in score units).
Verdict banner and ObjectiveBreakdown card both updated.

**Why:** Relative gap routinely showed ~59% even when objective and
bound looked close, because CP-SAT's bound is structurally loose for
roster problems (each component's individual minimum is usually 0).
Absolute headroom is honest and avoids the misleading percentage.

## 2026-04-23 — Closed scheduler gap #4: weekday on-call coverage

**What:** Added `weekday_oncall_coverage_enabled` to ConstraintConfig
in `scheduler/model.py`. Default OFF for legacy callers (preserves
existing tests). v2 API's Pydantic ConstraintsConfig defaults the
mirror field to True so SPA users always get on-call coverage every
weekday night, matching CONSTRAINTS.md §5 gap #4.

**Why:** Pre-fix, with H11 off (Minimal staffing mode), weekday
on-call could be left empty because no hard constraint required it.
H8 covered weekends only.

## 2026-04-23 — Solve UX hardening

**What:** Several small fixes on the Solve flow:

- Server-side WS heartbeat every 8s + initial heartbeat on connect
  to survive HF Spaces proxy idle-timeout drops.
- Catch-all exception handler in the WS handler so errors become
  proper `{type:error}` messages instead of 1006 close codes.
- Silent REST fallback when WS drops mid-solve.
- After 2 consecutive WS failures in a session, skip WS and go
  straight to REST (auto-disable, sessionStorage-backed).
- Continue button no longer regresses: store retains previous best
  if new run is worse.
- Banner during REST fallback shows honest progress instead of
  "0 solutions found".

## 2026-04-23 — UX polish round

**What:**
- Three pre-built scenarios (radiology, busy hospital, nursing ward)
  exposed via `GET /api/state/scenarios` and `POST /api/state/scenarios/{id}`.
  Dashboard shows them as featured cards.
- Right-side collapsable nav (vertically-centered floating pill).
- Collapsable "Getting started" stepper.
- Score breakdown with main-drivers panel and human-readable raw units.
- Roster heatmap distinguishes public holidays (amber header), block
  types (rose cells), preferences (★ marker).
- Workload + score breakdown moved below the roster grid in a 2-col
  layout.
- Dark mode finally works in light mode (Tailwind v4 class-based
  variant fix).
- Empty-state CTAs on Setup / Doctors and Rules / Stations.
- Save indicator pill in the top bar.
- "People" replaces "Doctors" as the page title (nursing-friendly).

## 2026-04-22 — v2.0 React SPA + FastAPI rewrite (branch `react-ui`)

**What:** A parallel v2 branch replaces the Streamlit app with a React
SPA backed by FastAPI. The solver core in `scheduler/` is unchanged;
all v0.7.1 feature parity is preserved. Deployed as a separate Hugging
Face Space (`charlesyapai/healthcare_workforce_scheduler_v2`) so the v1
Streamlit Space remains available on `main`.

**Why:** Streamlit imposed UX ceilings that the v1 app had outgrown:
clumsy data-table editing, no drag between cells, `st.rerun()` for
live streaming, single-column desktop-only layout. The v2 fork
addresses these while keeping the proven CP-SAT model intact. See
[`docs/NEW_UI_PLAN.md`](NEW_UI_PLAN.md) for the full rationale.

**Architecture:**
- Backend: FastAPI + Uvicorn on port 7860. Pydantic v2 models mirror
  the YAML shape so `scheduler.persistence.dump_state` / `load_state`
  round-trip losslessly with v1 files.
- Frontend: React 18 + TypeScript (strict) + Vite + Tailwind v4 +
  TanStack Query + Zustand + React Router.
- Session model: cookie-keyed in-memory store per browser; SPA also
  persists UI preferences (theme) in localStorage.
- Deployment: multi-stage Dockerfile (Node builds the SPA, Python runs
  uvicorn serving `/` from the built bundle and `/api/*` from FastAPI).

**Backend API (`api/`):**
- `GET/PUT/PATCH /api/state` — full session state, cookie-keyed.
- `POST /api/state/seed` — populate 20-doctor default problem.
- `POST /api/state/prev_workload` — compute carry-in from a prior JSON.
- `GET/POST /api/state/yaml` — import/export via `scheduler.persistence`.
- `POST /api/diagnose` — L1 necessary-condition checks.
- `POST /api/explain` — L3 soft-relax infeasibility report.
- `WS /api/solve` — streams `{type:event, wall_s, objective, best_bound,
  components, assignments}` per improving solution; accepts
  `{action:stop}`. CP-SAT runs in a thread; events pushed back to the
  event loop via `loop.call_soon_threadsafe`.
- `POST /api/overrides/fill-from-snapshot` — clones a solved roster
  (final or any intermediate) into the overrides list.

**Frontend pages:**
- `/` Dashboard — live /api/health, session summary, "Start with
  defaults" button.
- `/setup/{when,doctors,blocks,overrides}` — per-period inputs with
  500ms debounced auto-save via PATCH. Doctors table with inline edit,
  tier/subspec/FTE/max-oncalls. Blocks table + CSV bulk-paste drawer.
- `/rules/{tiers,subspecs,stations,constraints,hours,fairness,priorities}`
  — once-per-department config. Station card grid, toggle switches for
  H4–H11, live-bar hours chart.
- `/solve` — WebSocket live solve with convergence chart (recharts),
  verdict banner, stop button.
- `/roster` — doctor × date heatmap (colour-coded by role), station ×
  date view, snapshot slider across intermediate solutions, diff view,
  workload table (client-side computed), lock-to-overrides button, CSV
  download.
- `/export` — JSON / CSV / ICS / print-preview / copy-YAML / share-link
  / per-doctor mailto previews.
- Top-bar: Save/Load YAML, dark-mode toggle.
- Keyboard: `g d/s/r/p/o/e` nav, Ctrl+S save, Ctrl+Enter solve/stop.

**Tests:**
- `tests/test_api_state.py` — 10 REST tests (health, seed, PUT/PATCH,
  YAML round-trip, prev_workload, session isolation, diagnose).
- `tests/test_api_solve.py` — 5 WebSocket tests (completes, streams
  events, stops <60s under 120s budget, overrides clone, 400 on no-solve).
- Legacy `test_smoke.py`, `test_h11.py`, `test_stress.py` remain green.
- Total: 21 pytest pass.

**Deviations from `docs/NEW_UI_PLAN.md`:**
- FullCalendar library deferred — the heatmap + station × date + per-
  doctor workload drawer cover the calendar use case with a lighter
  dep footprint.
- shadcn/ui CLI not used; hand-wrote minimal `Button`/`Card`/`Input`/
  `Select` primitives with cva for variants.
- Per-doctor drag-to-move on the roster grid not wired — the
  lock-and-re-solve flow covers the "swap one cell" use case.
- OpenAPI-driven types commit both `openapi.json` and `types.ts` so
  Docker builds don't need a running API at build time.
- WebSocket message schemas manually defined in TypeScript (FastAPI
  doesn't emit WS schemas into OpenAPI).

**Files of note:**
- `api/main.py`, `api/routes/*`, `api/models/*`, `api/sessions.py`
- `ui/src/{App,main}.tsx`, `ui/src/routes/*`, `ui/src/components/*`,
  `ui/src/api/*`, `ui/src/store/*`, `ui/src/lib/*`
- `Dockerfile` (multi-stage), `scripts/dump_openapi.py`

**Verified:**
- HF Space rebuilds to RUNNING in ~2 min per push.
- `pytest tests/` — 21/21 pass in ~105s.
- `pnpm build` — 730 KB JS / 219 KB gzipped, 32 KB CSS / 7 KB gzipped.

## 2026-04-20 — v0.7.1 Split Configure into Setup + Department rules

**What:** The single "Configure" tab is now two tabs — **Setup** (per-
period) and **Department rules** (per-department). Four top-level tabs
total: Setup · Department rules · Solve & Roster · Export.

**Why:** User asked for the split because the things you touch every
period (doctors, leave, overrides) were mixed in with the things you
set up once (stations, rules, hours, fairness weights). Keeping them on
separate tabs reduces scroll distance on the common path.

**Setup** (frequently edited, 4 sections):
1. When — dates + horizon + public holidays.
2. Doctors — the per-period roster.
3. Leave, blocks, and preferences (+ CSV bulk-paste).
4. Manual overrides.

**Department rules** (rarely edited, 7 sections A–G):
- A. Tier labels — rename junior/senior/consultant.
- B. Sub-specialties — comma-separated list.
- C. Stations — name, sessions, required, eligible tiers, reporting.
- D. Rules for the roster — H4–H11 toggles + H4's N parameter.
- E. Hours per shift — 8 adjustable shift lengths.
- F. How fairness is measured — workload weights.
- G. Solver priorities — objective weights.

The Department rules are preserved across save/load of the YAML config,
so a hospital's setup transfers to next period's Setup tab automatically.

**Docs:** FEATURES.md restructured — section 3 is now Setup (per-period
only), new section 4 is Department rules (A–G). Sidebar renumbered to 5,
Solve & Roster to 6, Export to 7, What's NOT to 8, Architecture to 9.

**Tests:** unchanged (6/6 pass — no schema or solver changes).

## 2026-04-20 — v0.7 Persistence, FTE, preferences, overrides, views

**What:** Four-phase rosterer-UX overhaul shipped in a single release.

**Why:** The v0.6.x tool was usable but missing the things a real roster
coordinator does every day — saving config across sessions, entering
multi-day leave, modeling part-timers and per-doctor call caps,
handling preferences, locking parts of the roster and re-solving, and
viewing the output in more than one orientation.

**Phase 1 — Persistence & data entry:**
- New `scheduler/persistence.py`: `dump_state(ss) -> YAML string`, `load_state
  (yaml_text) -> dict of session updates`, `prev_workload_from_roster_json`.
- Sidebar "💾 Save YAML" / "Load YAML" buttons for config round-trip.
- Sidebar "Import prior-period workload" expander: upload last month's
  JSON export, auto-fills each doctor's `prev_workload` column.
- Blocks table gains an `end_date` column; a single row can now represent
  a multi-day leave span (inclusive).
- "Bulk-add blocks from CSV" expander in Configure: paste
  `doctor,start,end,type` lines, one per row.

**Phase 2 — Fit your hospital:**
- **Editable tier labels** (new Configure section 2): map Junior/Senior/
  Consultant to your hospital's terminology (e.g. Registrar / Fellow /
  Consultant). Labels flow through the workload table, metric strip, and
  verdict banner. Internal solver logic still reasons about the three
  semantic tiers.
- **Editable sub-specialty list** (same section): comma-separated list;
  defaults to `Neuro, Body, MSK`. Flows through `Instance.subspecs` and
  the H8 weekend coverage rule.
- **Per-doctor FTE** column on the Doctors table (default 1.0). Scales
  the S0 workload-balance target so a 0.5-FTE doctor is balanced against
  half a full-timer's score, and the S5 idle-weekday penalty so part-
  timers aren't forced into full utilisation.
- **Per-doctor `max_oncalls`** column (new H14 hard constraint). Caps a
  doctor's on-call count for the horizon.
- **Positive preferences**: new block types "Prefer AM" / "Prefer PM".
  Soft bonus (new S6 penalty term, default weight 5) for honouring them.

**Phase 3 — Iterate on the roster:**
- **Manual overrides table** in Configure section 6. Each row is a
  `(doctor, date, role)` that becomes a hard constraint in the solver
  (new H15). Supports `STATION_<name>_AM|PM`, `ONCALL`, `EXT`, `WCONSULT`.
- **"📌 Copy this roster to overrides"** button on the Solve & Roster tab.
  Dumps every current assignment into the overrides table so users can
  delete the specific rows they want to change and re-solve. This is the
  lock-and-re-solve workflow: everything stays fixed except what you
  explicitly free.
- **Diff view** between two snapshots (expander). Cells that differ are
  highlighted yellow with `old → new` text; bottom-count tells you how
  many cells changed.

**Phase 4 — Views & publishing:**
- **Alternative views** expander with three toggles:
  - **Station × date**: transposed grid, rows are station·session, cells
    list doctors covering.
  - **Per-doctor calendar**: pick a doctor → see their horizon as weekly
    rows × Mon–Sun columns. What you'd hand a doctor.
  - **Today's roster**: pick any date → summary table of who's doing what.
- **Print-friendly HTML export** in the Export tab. Single-file HTML
  with embedded CSS, colour-coded cells, print media rules. Open in your
  browser and use File → Print → Save as PDF.

**Infrastructure:**
- Solver time-limit max raised from 600s to 3600s.
- Tests green (6/6); streamlit boot verified.

## 2026-04-20 — v0.6.1 Rebalance defaults, colour-code roster, cross-tier hint

**What:** Fix the "consultants work 50h/week but juniors only work 10h/week"
default-config bug, colour-code the roster grid by role, and surface a
cross-tier-hours warning in the verdict banner + metric strip.

**Why:** User ran a solve and saw consultants scheduled every weekday +
weekends while juniors/seniors were idle most days. Root cause: the default
station list had only 6 junior/senior-eligible slots per weekday (US, XR,
GEN_AM, GEN_PM at required=1) vs 14 consultant-eligible slots (all 8
stations × 2 sessions). With ~10 juniors/seniors, that's a guaranteed
4 idle per day. The solver was doing its job — the defaults were wrong.

**Changed — defaults:**
- `DEFAULT_STATIONS` now puts CT and MR in `{senior, consultant}` (were
  consultant-only). Seniors can read cross-sectional in this hospital.
- `US` and `XR_REPORT` go from `required=1` to `required=2` each (high-
  volume reading stations).
- `GEN_AM` and `GEN_PM` stay at required=1.
- Net: 18 slot-assignments per weekday (was 14). Junior-eligible slots
  go from 6 to 10; senior-eligible from 6 to 14. For ~20 doctors, each
  doctor averages ~1 session per weekday plus on-call — realistic clinical
  time across all tiers.

**Added — UI:**
- **Colour-coded roster grid.** Cells are tinted: 🟢 green for station
  work (darker when AM+PM), 🟣 purple for on-call, 🔵 teal for weekend
  EXT/WC, ⚪ grey for leave, 🟡 amber for no-duty weekdays. Legend line
  above the grid. Applies to both the live roster (during solve) and the
  final roster.
- **Avg hours / week (by tier)** in the metric strip: shows a
  `J 45h · S 48h · C 43h` summary. Makes cross-tier imbalance visible
  at a glance.
- **Cross-tier gap warning** in the verdict banner when the lowest-hours
  tier averages under 60% of the highest. Points the user at station
  eligibility / required_per_session as the likely fix.

**Docs:**
- FEATURES.md updated: default-stations table, colour key for the roster
  grid, cross-tier warning behaviour, metric-strip refresh.

**Tests:** 6/6 pass (test_smoke's 12-doctor capacity + test_h11's 22-
doctor scenarios both remain feasible under the new station defaults).

## 2026-04-20 — v0.6 Blocks + hours/week + workload headline + plain-English UI

**What:** Second UX pass. Add call blocks + session blocks (distinct from
leave), add hours-per-week display with adjustable shift lengths, split the
per-doctor workload table into a headline (Score + Δ median + Hours/week)
plus a detailed breakdown expander, rewrite all Configure-tab labels in
plain English, and fix the data_editor "edit two cells, only one saves" bug.

**Why:** User feedback — (1) the UI still reads too "engineering"; numbers
like *idle-weekday penalty* don't tell a non-engineer what they mean; (2)
the per-doctor workload table buries the most important numbers (score, Δ
median) underneath the per-role counts; (3) hospitals also want an "hours
per week" view; (4) *call block* and *session block* are real requirements
distinct from leave — a doctor can be unavailable for on-call while still
doing station work; (5) the data editor was losing cell commits when users
edited two cells quickly.

**Added — model:**
- `HoursConfig` dataclass with 8 adjustable shift lengths (weekday AM/PM,
  weekend AM/PM, weekday/weekend on-call, weekend EXT, weekend consultant).
  Does not affect solver — feeds the 'Hours / week' report column only.
- `Instance.no_oncall: dict[doctor_id, set[day]]` — per-doctor call blocks.
- `Instance.no_session: dict[doctor_id, dict[day, set[session]]]` — per-doctor
  AM/PM session blocks.
- **H12** (call block) and **H13** (session block) hard constraints in
  `scheduler/model.py`.

**Added — metrics:**
- `metrics.hours_per_doctor(inst, assignments, hours)` — total hours and
  average hours per week, per doctor.

**Changed — ui_state.py:**
- `build_instance(...)` now accepts `block_entries` (iterable of
  `(name, date, kind)`) in addition to `leave_entries`. Parses kind into
  the appropriate Instance field. Accepted kinds: `Leave`, `No on-call`,
  `No AM`, `No PM` (+ synonyms).

**Changed — app.py (Configure tab rewrite):**
- Section-numbered layout: **1. When**, **2. Doctors**, **3. Leave, blocks,
  and preferences**, **4. Rules for the roster**, **5. Hours per shift**,
  **6. How 'fairness' is measured**, **7. Solver priorities (advanced)**.
- Unified **Blocks** table replaces the Leave-only table. Columns: Doctor
  (TextColumn — type the name), Date, Type (Leave / No on-call / No AM / No PM).
  Eliminates the dynamic SelectboxColumn that was triggering editor rebuilds
  on every doctors_df edit.
- All constraint toggles rewritten in plain English (e.g. "Cap on-call
  frequency (no more than once every N days)" instead of "H4 — On-call cap
  (1-in-N rolling)").
- Soft-objective weights labelled by what they *do*, not by S0-S5.
- New **5. Hours per shift** form (8 numeric inputs).

**Changed — app.py (Solve & Roster result display):**
- Per-doctor workload table split into two:
  - **Headline** (always visible): Doctor, Tier, Sub-spec, **Workload score**,
    **Δ vs. tier median** (red/blue colour), **Hours / week**, Leave days,
    Days without duty.
  - **Full breakdown by shift type** (expander): per-role counts, prev-period
    score, this-period score, total.
- Metric strip renames: "Idle weekdays" → "Days without duty", "Objective"
  → "Penalty score (lower = better)", "First feasible" → "First valid
  roster found at".
- Snapshot picker label: "Which roster to view" (was "Snapshot").

**Fixed:**
- **data_editor "edit two cells, only one saves" bug.** Root cause: the old
  pattern `ss.X = st.data_editor(ss.X, ...)` reassigned session state
  mid-render for multiple interdependent editors, and the Leave table's
  Doctor SelectboxColumn rebuilt on every doctors_df change. New pattern:
  capture each editor's return value as a local, and assign all three
  back to session_state in a single block at the **end** of the Configure
  tab. Blocks' Doctor column is now a plain TextColumn (with a "Known
  doctors: …" caption above for reference) — no more dependent dropdown.

**Tests:**
- 6/6 pass (test_smoke + test_h11 unchanged; the new constraints are
  no-ops when `no_oncall` and `no_session` are empty, which is the default).

**Known follow-ups:**
- Positive preferences ("Dr X prefers AM on Tuesday") — a soft-preference
  term. Deferred: adds scope and isn't yet requested as hard need.
- Save/load instance to YAML/JSON for persistence across HF Space rebuilds.
- Per-doctor calendar grid for leave/blocks (currently: one row per entry).

## 2026-04-20 — v0.5 H11 + constraint toggles + weighted workload + carry-in + UX rework

**What:** Fix the "solver said OPTIMAL but 3 doctors did zero coverage" bug
by adding H11 mandatory-weekday-assignment (soft); add toggles and a
parameter for every hard constraint; introduce a weighted workload model
(weekend call > weekday call) that drives both the UI's per-doctor score
and the solver's primary fairness objective; add prior-period carry-in so
doctors who did more last month get less this month; collapse the 7-tab UI
to 3 tabs with a verdict banner.

**Why:** User feedback — (1) "it said OPTIMAL but 3 doctors did 0 coverage"
meant H1 only enforced station coverage, not doctor utilisation; (2) "we
need the constraints to be options, adjustable" meant toggleable rules
with editable parameters; (3) "weekend call is more work than weekday call"
meant weighted workload rather than raw counts; (4) "someone who worked a
lot last month should get less this month" meant prior-period carry-in;
(5) "the UI is not intuitive" meant too many tabs with the solution
verdict buried.

**Added — model:**
- `ConstraintConfig` dataclass: H4 `oncall_gap_days` (parameter); H4–H9 and
  H11 on/off toggles. Defaults match prior behaviour except H11 is new and
  on by default.
- `WorkloadWeights` dataclass: per-role weights (weekday/weekend × session/
  on-call, EXT, weekend-consult). Integer-valued; defaults reflect "weekend
  costs more" (15/10 sessions, 35/20 on-call, etc.).
- `Instance.prev_workload: dict[doctor_id, int]` — carry-in from prior
  period, same units as the weighted workload score.
- New **H11** soft constraint (surfaced as S5 penalty): per-idle-doctor-
  weekday cost, default weight 100. Excuses: leave / post-call / lieu.
  On-call counts as working (not idle) for both juniors and seniors.
- New **S0** weighted-workload balance: per tier, minimises
  `max(weighted_workload[d] + prev_workload[d]) − min(…)`. This is the
  primary fairness term (default weight 40); S1–S3 remain available but
  defaults lowered.
- `solve(..., constraints=..., workload_weights=...)` new kwargs.

**Added — metrics:**
- `metrics.workload_breakdown(inst, assignments, weights)` — per-doctor
  breakdown (weekday/weekend sessions, weekday/weekend on-call, EXT, WC,
  leave days, prev_workload, final score). Mirrors the solver's S0 formula
  so the UI table shows what the solver balanced on.
- `metrics.count_idle_weekdays(inst, assignments)` — per-doctor count of
  weekdays with no role and no leave (drives the UI's "Idle wd" column).

**Changed — ui_state.py:**
- `doctors_df` gains a `prev_workload` column (default 0).
- `build_instance(...)` parses `prev_workload` into `Instance.prev_workload`.

**Changed — app.py (rewritten for UX):**
- **Three tabs** (down from seven): **Configure** (dates, doctors with
  prev_workload column, stations, leave, hard-constraint toggles + H4
  parameter, workload weighting, soft weights), **Solve & Roster**
  (streaming solve + verdict banner + snapshot picker + colour-coded
  workload table + Advanced analytics accordion), **Export** (JSON/CSV).
- **Sidebar** holds solver settings (time limit / workers / feasibility-
  only) and both diagnostics buttons (L1 pre-solve + L3 infeasibility
  explainer), plus a role-code legend.
- **Verdict banner** computes severity from status + optimality gap + idle
  count + coverage-violation check; one sentence that tells the user
  whether the roster is OK and why.
- **Per-doctor workload table**: weekday/weekend sessions, weekday/weekend
  on-call, EXT, WC, leave, idle-weekdays, prev_workload, **Score**, and
  **Δ median** column colour-graded red/blue for over/under-worked.
- **Snapshot picker** kept from v0.4.
- Constraints tab + Analytics tab + Diagnostics tab removed (folded in).

**Added — tests:**
- `tests/test_h11.py`: H11 off vs on (on reduces idle), H11 respects
  leave as excuse.

**Verified:**
- `pytest tests/` — 6/6 pass in ~2 min (3 smoke + 3 H11 scenarios).

**Known follow-ups:**
- Save/load instance to YAML (download/upload) — HF storage is ephemeral.
- Per-doctor calendar grid for leave (today: doctor + date rows).
- `prev_oncall` editor in the UI (today only exposed via the `Instance`
  field; build_instance takes names but no UI widget exposes it).

## 2026-04-20 — v0.4 Interactive UI: real doctors, real dates, snapshot picker

**What:** Pivot from the benchmarking-oriented UI (numeric inputs →
synthetic doctors) to a real configuration interface keyed to named
doctors, real calendar dates, and per-solution roster snapshots.

**Why:** User feedback — "the settings don't make sense… aren't we
supposed to have some kind of interface where we dictate who are the
actors and then show the rostered schedule when it's generated?" The
v0.3 app was really a benchmark harness with a viewer bolted on.

**Added:**
- `scheduler/ui_state.py` — defaults (`default_doctors_df`,
  `default_stations_df`), date helpers
  (`dates_for_horizon`, `format_date`, `day_index`),
  `build_instance(...)` that turns editable DataFrames + leave entries
  + public holidays into an `Instance`, and `doctor_name_map(...)`
  for id→name translation.
- `scheduler.model.solve(..., snapshot_assignments: bool = False)` —
  when True, each intermediate-solution event carries a full
  `assignments` snapshot (stations/oncall/ext/wconsult) so the UI can
  render the roster for *any* solution CP-SAT found, not just the final.

**Changed — `app.py` rewritten:**
- Seven tabs: **Setup**, **Constraints**, **Solve**, **Roster**,
  **Analytics**, **Diagnostics**, **Export**.
- **Setup**: date picker + horizon, public-holiday multi-select over
  real dates, `st.data_editor` for the doctors table (name / tier /
  sub-spec / eligible stations), a collapsible stations editor, a
  leave-entry table (doctor + date rows).
- **Constraints**: weekend-AM/PM toggle, four soft-weight inputs
  (S1–S4), solver time limit + workers + feasibility-only.
- **Solve**: Diagnose (L1) / Solve / Clear buttons. Streaming status
  line shows elapsed time, solution count, objective, best bound, and
  live optimality gap; live convergence chart; live intermediate-
  solutions table (`#, t, objective, bound, + penalty components as columns`).
- **Roster**: snapshot picker — any of the improving solutions or the
  final. Renders a **doctor-name × real-date** grid with role codes
  (`AM:CT`, `OC`, `EXT`, `WC`, `LV`) + a per-doctor workload summary.
- **Analytics**: final-solution metrics strip plus the six charts.
- **Diagnostics**: dedicated L1 + L3 buttons that use the current
  editable state (not the last solve's instance).
- **Export**: JSON + CSV with doctor names and ISO dates instead of
  numeric ids and day indices.

**Verified:**
- `tests/test_smoke.py` — OK.
- `tests/test_stress.py` — all 10 scenarios OPTIMAL, no verifier violations.
- `streamlit run app.py` — HTTP 200 + `/_stcore/health` OK.
- End-to-end with the new `build_instance` path: 20 doctors × 14 days
  OPTIMAL in ~1.4s with 10 snapshots captured, each containing full
  stations/oncall/ext/wconsult assignments.

**Known follow-ups (Phase B):**
- Per-doctor calendar grid for leave (today: doctor + date rows).
- Save/load instance to YAML (download/upload buttons since HF storage is ephemeral).
- `prev_oncall` editor.
- Hard-constraint toggles beyond weekend AM/PM (e.g. parametrise 1-in-N on-call gap).
- Colour-coded roster cells (would need a Plotly heatmap-with-text swap-in).

## 2026-04-19 — v0.3 Metrics, diagnostics, plots, real-time streaming

**What:** Three new modules (`scheduler/metrics.py`,
`scheduler/diagnostics.py`, `scheduler/plots.py`), a rewritten
`app.py` with a threaded-streaming solve loop, and per-plot
explanation docs under `docs/plots/`.

**Why:** User asked for (a) real-time streaming of intermediate
solutions with a breakdown of *which* soft constraints each solution
is still paying for, (b) a three-tier infeasibility story (pre-solve
sniff → solver status → soft-relax explainer), (c) plots that cover
solution quality, problem ease, solver behaviour, and constraint
complexity, and (d) a short explanation bundled with each plot so a
reader knows what to focus on.

**Added — modules:**
- `scheduler/metrics.py`
  - `problem_metrics(inst)` — scale, tier/subspec mix, eligibility
    density, leave density, per-day coverage slack, on-call capacity.
  - `solve_metrics(result, events)` — status, wall time, time-to-first
    feasible, objective, best bound, optimality gap, convergence
    timeline, per-component weighted penalty.
  - `solution_metrics(inst, result)` — per-tier session/on-call/weekend
    balance, on-call spacing histogram (flags gaps under 3 days),
    reporting-station spread, coverage/post-call/eligibility
    violations (sanity check).
- `scheduler/diagnostics.py`
  - `presolve_feasibility(inst)` — five L1 necessary-condition
    checks: tier headcount, per-station eligibility, subspec weekend
    coverage, on-call capacity under 1-in-3, coverage slack per day.
    Runs in milliseconds.
  - `explain_infeasibility(inst)` — L3 soft-relax. Rebuilds the model
    with slack variables on H1 (station coverage) and H8 (weekend
    subspec roles), minimises total slack, reports exactly which
    constraints had to be broken and by how much.
- `scheduler/plots.py` — 10 Plotly figure builders, each returning
  `(figure, explanation_md)`. Covers convergence, penalty breakdown,
  workload histogram, on-call spacing, roster heatmap, coverage
  heatmap, pre-solve coverage slack, and three dashboard views
  (time-vs-size heatmap, first-feasible-vs-optimal bars, complexity
  scaling log-log).

**Added — docs:**
- `docs/plots/*.md` — one short markdown per plot (convergence,
  penalty_breakdown, workload_histogram, oncall_spacing, roster_heatmap,
  coverage_heatmap, coverage_slack, time_size_heatmap,
  first_feasible_vs_optimal, complexity_scaling). Each has three
  sections: **What it shows**, **How to read it**, **What to focus
  on**. `plots.py` hot-loads them at call time so edits are reflected
  immediately without a code change.

**Changed — model.py:**
- `SolveResult` gains `first_feasible_s` and `penalty_components`.
- Intermediate-solution callback now always records wall time + per
  component weighted penalty (no more loss of information when the
  user supplies their own callback — we chain ours first).
- Soft-constraint terms are registered in a `penalty_components` dict
  during model build: `S1_sessions_gap_<tier>`, `S2_oncall_gap_<tier>`,
  `S3_weekend_gap_<tier>`, `S4_reporting_count`. S4 uses an aggregated
  `rep_total` IntVar so the callback can read it at each step.

**Changed — app.py (rewritten for streaming):**
- Background solver thread + `Queue` pattern. Worker puts
  `("event"|"done"|"error", payload)` on the queue; main thread polls
  at `POLL_INTERVAL_S=0.2` and updates `st.empty()` placeholders for
  the status line, live convergence chart, and live components table.
- Tabs: **Summary**, **Analytics** (all charts, each under an
  expander with its explanation), **Roster**, **Workload**,
  **Why infeasible?** (button → L3 soft-relax), **Export**.
- Sidebar gains a **Diagnose** button that runs the L1 pre-solve
  sniff and shows any necessary-condition violations before the user
  burns solver time.

**Changed — requirements.txt:** adds `plotly>=5.20`.

**Verified:**
- `tests/test_smoke.py` — passes.
- `tests/test_stress.py` — all 10 scenarios OPTIMAL, no verifier
  violations.
- `streamlit run app.py` — boots cleanly, streaming loop observed
  capturing ≥10 intermediate solutions with populated components
  dict on the 20-doctor × 14-day default.

**Known follow-ups (deferred):**
- GitHub Pages dashboard was scoped out: `ortools` does not run in
  the browser, and the user chose HF-only. A static dashboard via
  GitHub Actions remains possible but is not in this release.
- L3 explainer only covers H1 and H8 today. H2 (one-slot-per-session)
  and H4 (1-in-3 on-call) can be added by the same pattern.

## 2026-04-18 — v0.2 Streamlit UI + HF Spaces config

**What:** Streamlit app at `app.py`, HF Spaces frontmatter in `README.md`,
intermediate-solution callback hooked through `scheduler.solve`, 10-scenario
stress test under `tests/test_stress.py`.

**Why:** User asked for a Streamlit UI on Hugging Face Spaces and wanted
evidence the model holds up across varied constraints.

**Added:**
- `app.py` — sidebar config (doctors, days, start weekday, leave rate,
  public holidays, time limit, workers, weights), Solve button, tabs for
  Summary / Roster / Workload / Export.
- `tests/test_stress.py` — 10 scenarios (baseline, heavy leave, public
  holidays, Saturday start, higher headcount, prev-oncall seed, tight N,
  custom station list, short horizon, long horizon). Independent verifier
  re-checks H1–H10 on the returned roster. All pass.
- `scheduler.solve(on_intermediate=...)` — optional callback fired by
  CP-SAT's `CpSolverSolutionCallback` each time a new improving solution
  is found. The UI uses this for the "intermediate solutions" chart.
- `requirements.txt` gains `streamlit`, `pandas`.

**Deployment:**
- HF Spaces frontmatter in `README.md` — deploy this repo as a Streamlit
  Space, no extra config needed.
- Local: `streamlit run app.py`.

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
