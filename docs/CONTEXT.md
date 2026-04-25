# Project Context — Healthcare Worker Scheduler

**Read this first if you are a new agent or a human picking up this
project.** Last refreshed 2026-04-26.

## 1. Goal

Build a roster-generation service for a hospital department —
initial target was a radiology team (~30–50 consultants, scaling
toward ~200 staff), but the model now generalises to any
department whose week splits into AM / PM / on-call shifts.

The user inputs:
- Doctors / nurses / staff (with tier and per-person eligibility),
- Stations (the work that needs covering, with sessions and tiers),
- Constraints (rest periods, weekend cover, sub-spec parity, etc.),
- A horizon (start date, number of days, public holidays),

and the system returns a feasible roster that satisfies hard
constraints and optimises soft ones (workload balance, on-call
spread, idle-time minimisation, role preferences).

The product has **two faces** sharing one solver:

1. **Coordinator UI** — clinic / hospital users producing a real
   schedule. Setup → Solve → Roster → Export. Live now at
   `https://charlesyapai-healthcare-workforce-scheduler-v2.hf.space`.
2. **Lab / research surface** — `/solve/lab/*` (under Solve in the
   nav). Benchmark, Capacity, Sweep, Fairness, Scaling. Used by us
   when tuning the solver and intended to support a peer-reviewed
   submission.

## 2. Architecture (current — v2)

```
┌────────────────────────────────────────────────────────────────────┐
│ React SPA (ui/src/)                                                 │
│  Vite + TypeScript strict + Tailwind v4                              │
│  TanStack Query (server cache) + Zustand (client UI state)           │
│  Routes: / · /setup/* · /solve · /solve/lab/* · /roster              │
└────────────────────────────────────────────────────────────────────┘
            │ apiFetch (cookie session)
            ▼
┌────────────────────────────────────────────────────────────────────┐
│ FastAPI (api/)                                                      │
│  Routers: state, solve, roster, metrics, lab, compliance, …         │
│  Per-session state held in memory (sessions.py)                      │
│  WebSocket /api/solve streams CP-SAT intermediate solutions          │
└────────────────────────────────────────────────────────────────────┘
            │ session_to_instance
            ▼
┌────────────────────────────────────────────────────────────────────┐
│ Solver (scheduler/)                                                 │
│  CP-SAT model in scheduler/model.py                                  │
│  Hard rules: H1–H15 + weekday on-call coverage                       │
│  Soft objective S0 (workload) … S7 (role prefs)                      │
│  Heuristic baselines: greedy, random_repair (scheduler/baselines.py) │
└────────────────────────────────────────────────────────────────────┘
```

The Streamlit-era `app.py` is gone — the v2 build replaced it
entirely. The solver layer (`scheduler/`) is the same one from
v0.x with significant additions; the Pydantic + UI layers are
new.

## 3. Where we are right now

**Branch:** `react-ui` (the project ships from this branch — there's
no separate `main` rollout).

**Last shipped commit:** `0c7edb8` — "Fix H1 validator: recognise
FULL_DAY paired AM+PM rows".

**Live HF Space:** `charlesyapai/healthcare_workforce_scheduler_v2`
(private Docker Space). Deploys via
`bash scripts/deploy_hf.sh` which force-pushes a docs-stripped
branch to HF main.

### What's built and stable

- **Setup** absorbed Rules in the 2026-04-25 IA pass — `/setup/*`
  has both per-period inputs (Templates · When · People · Leave &
  blocks · Role preferences · Manual overrides) and department
  inputs (Shape · Teams & stations · Rules · Hours & weights).
- **Solve** hosts Lab as a sub-section — `/solve/lab/*` —
  with Benchmark, Capacity, Sweep, Fairness, Scaling tabs.
- **Roster** absorbed Export — `/roster` shows the heatmap +
  fairness panel + WTD compliance card + RosterExport inline.
- 17 bundled scenarios in `configs/scenarios/` covering quickstart
  (radiology · clinic), specialty (cardiology · ICU · ED · surgery
  with FULL_DAY OR lists · paeds · anaesthesia · nursing), realistic
  (busy month · teaching · regional · large), research (NRP-shaped
  benchmarks), and stress (tight on-call · dense leave).
- **Validator parity** — every hard constraint enforced by
  `scheduler/model.py` is mirrored in `api/validator.py`. A solve
  emits a self-check audit; manual roster edits hit the same
  validator over `/api/roster/validate`.
- **Per-doctor role preferences (S7)** — soft shortfall penalty
  for "Dr A wants ≥ N of role X this period". Editor at
  `/setup/preferences`. Soft, never blocks feasibility.
- **FULL_DAY station sessions** — paired AM+PM encoding for
  surgical-list-style "one doctor holds the whole day" stations.
- **UK NHS WTD compliance audit** — post-solve module under
  `api/compliance/uk_wtd.py`, surfaced as a card on `/roster`.
- **93/93 tests passing** on the full suite.

### What's in flight (active forward plan)

**Read [`docs/SCHEDULE_MODEL_REVAMP.md`](SCHEDULE_MODEL_REVAMP.md)
end-to-end before starting any solver / model work.** §11.10 is the
live handoff brief for the next agent.

1. **Phase A — DONE (2026-04-26).** Decoupled tier from station
   eligibility, dropped subspec, per-station weekend toggles,
   `<NumberInput>` primitive. Schema 1 → 2.
2. **Phase B1 — DONE (2026-04-27).** Backend on-call rewrite. The
   solver now drives every on-call constraint off user-defined
   `OnCallType` entries; H4/H6/H7/H8/weekday_oncall_coverage/
   weekend_consultants_required are all per-type fields. Schema 2 → 3.
   Migration creates 5 default types (`oncall_jr`, `oncall_sr`,
   `weekend_ext_jr`, `weekend_ext_sr`, `weekend_consult`) so existing
   scenarios keep producing identical role strings.
3. **Phase B2 — TODO.** UI editor at `/setup/oncall` for on-call
   types + per-doctor `eligible_oncall_types` chip group on the
   Doctors page. Removes the placeholder card from
   `/setup/constraints`. See revamp doc §11.10.
4. **Phase C — TODO.** Variable tier count: replace the literal
   `("junior", "senior", "consultant")` triple with a user-defined
   `Tier` list (key + classification). Schema 3 → 4.
5. **Phase D — TODO.** Clock-time AM/PM with auto-computed hours.

Current `schema_version`: **3**. Loaders accept any older version
and migrate forward; saves always write the current version.

### What was once on the roadmap and is no longer

- **Phase 2 — ML predictor** (mentioned in old context as a "if
  CP-SAT is too slow" fallback). Tabled. CP-SAT solves the 200×28
  case fast enough for interactive use; ML adds risk + reproducibility
  pain that a peer-reviewed submission doesn't want. The Lab's
  `/lab/scaling` tab makes this empirically defensible.
- **Streamlit `app.py` UI**. Replaced by the React SPA.
- **Local-only Plotly charts**. Replaced by Recharts in the SPA.

## 4. How to pick up where we left off

1. Read [`SCHEDULE_MODEL_REVAMP.md`](SCHEDULE_MODEL_REVAMP.md) §11
   ("Implementation context for the integrating agent") — that
   section is the live operational guide for the next phase of work.
2. Read [`CONSTRAINTS.md`](CONSTRAINTS.md) — the H/S rule spec.
   Note that Phase A will revise this doc significantly (subspec
   removal, per-station weekend); don't rely on the literal H8
   wording in the current `CONSTRAINTS.md` after Phase A lands.
3. Read [`CHANGELOG.md`](CHANGELOG.md) — running log of what
   shipped, in reverse chronological order.
4. Set up:
   ```bash
   pip install -r requirements.txt
   cd ui && pnpm install && cd ..
   ```
5. Run tests:
   ```bash
   python -m pytest tests/ -x -q --ignore=tests/test_stress.py
   ```
   Should finish in ~1–2 min and report ~80 tests passing
   (test_stress.py is the slow one; full suite is ~5 min).
6. Run the build script — solves all 17 scenarios end-to-end:
   ```bash
   python scripts/build_scenarios.py
   ```
7. Bring up the dev stack:
   ```bash
   # Backend (port 7860):
   uvicorn api.main:app --reload --port 7860
   # Frontend (proxies /api to 7860):
   cd ui && pnpm dev
   ```
   The SPA opens at `http://localhost:5173`.

## 5. Key files

| Path | Purpose |
|---|---|
| **Specs / docs** | |
| `docs/SCHEDULE_MODEL_REVAMP.md` | **Active forward plan** — read first. |
| `docs/CONSTRAINTS.md` | Hard + soft rule spec (will be updated as Phase A lands). |
| `docs/CHANGELOG.md` | Reverse-chronological log of every shipped change. |
| `docs/CONTEXT.md` | This file. |
| `docs/INDUSTRY_CONTEXT.md` | NRP literature + benchmarks + regulatory landscape. |
| `docs/VALIDATION_PLAN.md` | Research-readiness checklist. |
| `docs/RESEARCH_METRICS.md` | Formal metric definitions (S0…S7, etc.). |
| `docs/HOW_TO_REPRODUCE.md` | Replay-bundle walkthrough. |
| `docs/CITING.md` | BibTeX stubs. |
| `docs/LAB_TAB_SPEC.md` | Lab tab UI/API spec. |
| **Solver** | |
| `scheduler/model.py` | CP-SAT model, `solve()`, `SolveResult`. |
| `scheduler/instance.py` | `Doctor`, `Station`, `Instance` dataclasses + synthetic generator. |
| `scheduler/ui_state.py` | UI tables → `Instance` (validation gate). |
| `scheduler/persistence.py` | YAML round-trip (`load_state` / `dump_state`). |
| `scheduler/baselines.py` | Greedy + random-repair baselines for the Lab. |
| `scheduler/diagnostics.py` | L1 pre-solve feasibility checks + L3 infeasibility explainer. |
| `scheduler/metrics.py` | Per-solve and per-solution metric helpers. |
| **API** | |
| `api/main.py` | FastAPI app. Mounts SPA at `/`. |
| `api/sessions.py` | Per-browser session state, `session_to_instance`, role-string emission. |
| `api/validator.py` | Post-solve hard-constraint audit. **Must mirror solver.** |
| `api/models/session.py` | Pydantic shape of `SessionState`. |
| `api/models/events.py` | WS event shapes + `AssignmentRow`. |
| `api/models/lab.py` | Lab batch / capacity / scaling request-response shapes. |
| `api/routes/state.py` | `/api/state*`, scenario list + load. |
| `api/routes/solve.py` | WebSocket `/api/solve`, REST `/api/solve/run`, override fill-from-snapshot. |
| `api/routes/roster.py` | `/api/roster/validate` (hits validator). |
| `api/routes/lab.py` | Lab batch, scaling, capacity, bundle-zip. |
| `api/routes/metrics.py` | Fairness + coverage. |
| `api/routes/compliance.py` | UK NHS WTD audit. |
| `api/routes/diagnostics.py` | L1 pre-solve + L3 explain. |
| `api/lab/batch.py` | Cross-product (solver × seed) batch runner. |
| `api/lab/scaling.py` | Synthetic-instance grid + power-law fit. |
| `api/lab/capacity.py` | Hours-vs-target + team-reduction analyses. |
| `api/lab/bundle.py` | Reproducibility ZIP export. |
| `api/metrics/fairness.py` | Per-tier Gini/CV/range, FTE-normalised. |
| `api/metrics/coverage.py` | Shortfall + over-coverage per session. |
| `api/compliance/uk_wtd.py` | Six WTD rules (W1–W6) as a post-solve audit. |
| **Frontend (selected)** | |
| `ui/src/App.tsx` | React Router setup. |
| `ui/src/components/Layout.tsx` | Top + side nav. |
| `ui/src/api/hooks.ts` | TanStack Query hooks; one per endpoint. |
| `ui/src/api/openapi.json`, `types.ts` | Generated; regen via `pnpm run gen:types`. |
| `ui/src/routes/Setup/*` | All `/setup/*` pages (Templates · When · People · Leave · Preferences · Overrides · Shape · Teams · Constraints · Weights). |
| `ui/src/routes/Solve/*` | `/solve` and `/solve/lab/*`. |
| `ui/src/routes/Roster.tsx` | The post-solve workspace (heatmap, edit, validate, fairness, WTD, export). |
| `ui/src/store/solve.ts`, `draft.ts`, `labBatch.ts` | Zustand stores. |
| **Configs / scripts** | |
| `configs/default.yaml` | Default config emitted by `seed_defaults`. |
| `configs/scenarios/*.yaml` | The 17 bundled scenarios. |
| `configs/scenarios/manifest.json` | Generated alongside YAMLs. |
| `scripts/build_scenarios.py` | Builds + verifies + writes all 17 scenarios. |
| `scripts/dump_openapi.py` | Dumps OpenAPI spec to stdout. |
| `scripts/deploy_hf.sh` | Force-deploys to the HF Space. |
| `scripts/replay_bundle.py` | Replays a downloaded reproducibility bundle. |
| `scripts/benchmark_tuning.py` | A/B sweeps for the tuning toggles. |

## 6. Decisions that are still load-bearing

- **CP-SAT over MILP.** CP-SAT handles channelling (post-call off,
  1-in-N on-call) and symmetry breaking better than a typical MIP
  for this problem shape. Free + well-maintained. The MILP baseline
  for paper-comparison purposes is on the wishlist
  ([`docs/BRIEFING_2026-04-23.md`](BRIEFING_2026-04-23.md) §4.2)
  but not blocking.
- **Per-tier balance, not pooled.** Juniors and consultants do
  different work; balancing them in one pool would penalise
  consultants for legitimately doing fewer hours. Surfaced as a
  note on `/setup/weights` (was `/rules/weights` before the IA pass).
  **This stays after the revamp** — Phase C's variable-tier work
  preserves per-tier bucketing using a classification field.
- **No public-holiday calendar hardcoded.** Pass an explicit
  list. Treats public holidays as Sundays for weekend-rule
  purposes.
- **Reporting-only Hours config (current).** AM/PM/oncall hours
  exist in `Hours` but don't drive solver decisions — only the
  display column on `/roster`. Phase D will tie clock times into
  Hours automatically.
- **Validator parity.** Every hard rule enforced by the model is
  re-verified by `api/validator.py` post-solve. **Don't change a
  solver constraint without the matching validator change.**
- **HF deploys are docs-stripped.** `scripts/deploy_hf.sh`
  reconstitutes a `hf-deploy` branch from `react-ui` minus
  `docs/`, then force-pushes to HF main. Canonical history
  lives on GitHub.

## 7. Decisions that have CHANGED across the active revamp

State of play after Phase B1 (commit on `react-ui`, 2026-04-27):

- **3 hard-coded tiers (junior / senior / consultant).** **Still
  hard-coded.** Phase C makes this user-defined (next phase).
- **`station.eligible_tiers` is a hard rule.** **Removed in Phase
  A.** Now advisory metadata; only `doctor.eligible_stations` drives
  solver eligibility.
- **`Doctor.subspec` exists; H8 needs 1 consultant per subspec.**
  **Removed in Phase A.** Originally replaced by a configurable
  consultant count; now (Phase B1) lives as `daily_required` on the
  `weekend_consult` on-call type.
- **Single global `weekend_am_pm` toggle.** **Removed in Phase A.**
  Per-station `weekday_enabled` / `weekend_enabled` flags took over.
- **Hard-coded on-call / ext / wconsult variable families.**
  **Removed in Phase B1.** Generic `OnCallType` family driven by
  `Instance.on_call_types`. Legacy role strings preserved via
  `legacy_role_alias` field on each migrated type.
- **`ConstraintsConfig` H4/H6/H7/H8/weekday_oncall_coverage/
  weekend_consultants_required toggles.** **Removed in Phase B1.**
  All per-OnCallType now. Survivors on ConstraintsConfig: `h5_enabled`
  (master next-day-off override), `h9_enabled` (lieu day for
  weekend-role types), `h11_enabled` (idle-weekday penalty).

## 8. Known risks + watch-items

- **Solver blow-up at 200 doctors × 28 days.** Variable count is
  ~90k. CP-SAT usually handles it, but symmetry breaking + the
  redundant-aggregates toggle on `/lab/sweep` are the levers if
  it tightens up. Not blocking interactive use today.
- **HF cold-start.** First request after a redeploy can take 30–60s
  while the container warms. The deploy script polls the runtime
  API until `RUNNING` to confirm.
- **OpenAPI regen forgetting.** The single most common reason
  `pnpm build` fails after a backend edit. Pattern: `python
  scripts/dump_openapi.py > ui/src/api/openapi.json && (cd ui &&
  pnpm run gen:types)` after any change to `api/models/*.py`.
- **YAML schema drift across the revamp.** Phase A bumps
  `schema_version` from 1 to 2; Phase B → 3, etc. Loaders accept
  any older version and migrate forward; saves always write the
  current version. **Don't ship a phase boundary without testing
  that an older saved YAML still loads.**
- **Validator-model drift.** See §6. The FULL_DAY rollout was
  shipped without the validator change and produced a red
  self-check on every FULL_DAY scenario for two days before being
  caught. Don't repeat.

## 9. Running in a different environment

The backend is pure Python + OR-Tools. Dependencies pinned in
`requirements.txt`:

```
ortools>=9.10
pyyaml>=6
fastapi>=0.115
uvicorn[standard]>=0.30
orjson>=3.10
python-multipart>=0.0.9
websockets>=12
pytest>=8
httpx>=0.27
pandas>=2.0
plotly>=5.20  # legacy; only used by old scheduler/plots.py
```

Python 3.11+. No GPU needed. No network needed once deps are
installed.

The frontend ships as a Vite + React + TypeScript SPA bundled by
the multi-stage Dockerfile into `api/static/` at container build
time. For local dev, run Vite separately on port 5173 with the
`/api` proxy pointing at `localhost:7860`.

HF Space is a private Docker Space — `Dockerfile` at repo root
defines the multi-stage build. Container exposes port 7860.

## 10. Pointers to docs that supersede parts of this one

When in doubt, the more recent / specific doc wins:

- For the active model rework: `docs/SCHEDULE_MODEL_REVAMP.md`.
- For the current hard / soft rules: `docs/CONSTRAINTS.md`.
- For research-tooling and metric definitions: `docs/VALIDATION_PLAN.md`,
  `docs/RESEARCH_METRICS.md`, `docs/INDUSTRY_CONTEXT.md`.
- For the Lab tabs: `docs/LAB_TAB_SPEC.md`.
- For the running history: `docs/CHANGELOG.md`.
