# Changelog

Append-only log. Newest at top. Each entry: date, short title, what/why.

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
