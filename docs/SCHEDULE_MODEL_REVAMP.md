# Schedule-model revamp — integration plan

**Status:** Draft for review (2026-04-26). Updated as phases land.
**Owner:** Charles + Claude.
**Replaces / supersedes parts of:** `docs/CONSTRAINTS.md` (will need
revision after Phase A), `docs/LAB_TAB_SPEC.md` (no change, just
context), `docs/INDUSTRY_CONTEXT.md` §5 (the on-call section will
become more enforceable after Phase B).

---

## 1. Why this exists

Six gaps surfaced in real use that the current model can't accommodate
cleanly:

1. **Tiers are hard-coded.** Three slots — `junior`, `senior`,
   `consultant`. Renaming via `tier_labels` is cosmetic; departments
   that need 4 or 5 distinct grades have no way to express it.
2. **Tier locks station eligibility.** Every station has a
   `eligible_tiers` set that the solver enforces as a hard rule. In
   reality, eligibility is per-person — a senior may sometimes cover
   a junior's station out of necessity.
3. **Subspec is consultant-only and weekend-coupled.** It exists
   solely to satisfy the H8 "1 consultant per subspec on weekends"
   rule. It doesn't generalise (juniors / seniors can't have
   subspecs), and it forces every department to pretend they have
   subspecs even when they don't.
4. **No per-station weekend control.** A single global
   `weekend_am_pm` flag governs whether *all* stations run on
   weekends. There's no way to say "CT runs Mon–Fri only, weekend
   reporting runs every day, the OR list runs weekdays plus Saturday".
5. **On-call is a hard-baked solver concept.** The model has fixed
   `oncall` / `ext` / `wconsult` variable families with built-in
   rules (junior PM-on-on-call, senior whole-day-off, post-call
   rest, weekend H8). There's no way to express "this department
   uses 8am–10pm half-calls", "this one has 24h calls Mon–Fri only
   plus 12h weekend halves", or "two on-call grades, with different
   post-shift rules per grade".
6. **Hours are manually keyed.** AM/PM sessions have no clock-time
   field; users set the hours separately in the Hours config. They
   don't propagate.

Plus a small UX bug: backspacing the last digit of a number input
re-clamps the value and bumps the cursor to the end of the field.

## 2. Goals + non-goals

**Goals:**

- The user can describe a real department's roster shape — including
  4+ tier hierarchies, per-station weekend cover, and arbitrary
  on-call patterns — without the solver baking in assumptions.
- The solver still enforces statutory rest rules and balances workload
  per tier.
- Existing scenarios (17 today) continue to load and solve. YAML files
  saved before the revamp open without breaking.
- Tests stay green at every phase boundary.

**Non-goals:**

- Multiple shifts overlapping mid-day on the same station (e.g. a
  station that runs 07:00–15:00, 13:00–21:00, and 21:00–07:00 with
  three distinct shift handovers). Possible but out of scope here.
- Surgical-list-with-equipment / theatre-room coupling. Standard
  rostering only — not OR scheduling.
- Stochastic demand / absenteeism modelling.
- Multi-week rolling-horizon rescheduling.

## 3. Architecture today

```
┌─────────────────────────────────────────────────────────────┐
│ SessionState (api/models/session.py)                        │
│  ├── doctors: [{name, tier ∈ {jun,sen,con}, subspec, …}]    │
│  ├── stations: [{name, sessions ∈ {AM,PM,FULL_DAY},          │
│  │                eligible_tiers, …}]                        │
│  ├── horizon: {start, n_days, public_holidays}              │
│  ├── constraints: {h4_enabled, …, weekend_am_pm, …}         │
│  └── hours: {weekday_am=4, weekday_pm=4, weekday_oncall=12, │
│              weekend_*=…} (reporting only)                  │
└─────────────────────────────────────────────────────────────┘
            │
            ▼  session_to_instance (api/sessions.py)
┌─────────────────────────────────────────────────────────────┐
│ Instance (scheduler/instance.py)                            │
│  ├── doctors: [Doctor(tier, subspec, eligible_stations)]    │
│  ├── stations: [Station(sessions, eligible_tiers, …)]       │
│  ├── role_preferences (S7 — soft shortfall)                 │
│  └── …                                                       │
└─────────────────────────────────────────────────────────────┘
            │
            ▼  solve() (scheduler/model.py)
┌─────────────────────────────────────────────────────────────┐
│ CP-SAT model                                                │
│  Variables:                                                 │
│   ├── assign[d, day, station, sess]    AM | PM              │
│   ├── oncall[d, day]                   junior + senior only │
│   ├── ext[d, day]                      junior + senior, we  │
│   └── wconsult[d, day]                 consultant, weekends │
│  Hard rules: H1–H15 + weekday_oncall_coverage               │
│  Soft objective: S0 (workload balance) … S7 (role prefs)    │
└─────────────────────────────────────────────────────────────┘
```

The pain points map onto this diagram as:

- (1) Tier hard-coded in `Doctor.tier` Literal + `for tier in
  ("junior", "senior", "consultant")` loops in `model.py`.
- (2) `if d.tier not in st.eligible_tiers: continue` in the var-
  creation loop ([scheduler/model.py:256](scheduler/model.py)).
- (3) Subspec is referenced at `wconsult` weekend rule + Instance
  field + Doctor field.
- (4) Single global `weekend_am_pm_enabled` toggle gates *every*
  station's weekend behaviour.
- (5) `oncall` / `ext` / `wconsult` variable families + their rules
  are hard-coded; no way to add a third on-call type.
- (6) `Hours` is dataclass-style — no link to per-station times.

## 4. Architecture target (full revamp)

```
┌─────────────────────────────────────────────────────────────┐
│ SessionState                                                │
│  ├── tiers: [{key, label, classification ∈ {trainee,        │
│  │            specialist, lead}, …}]   <-- ★ N-flexible      │
│  ├── doctors: [{name, tier, eligible_stations, …}]          │
│  │                                     <-- ★ no subspec      │
│  ├── stations: [{name, sessions: [Session], …,              │
│  │               eligible_tiers (advisory),                  │
│  │               weekday_enabled, weekend_enabled,           │
│  │               weekday_am_start, weekday_am_end, …}]       │
│  │                                     <-- ★ time-defined    │
│  ├── on_call_types: [{key, label, start, end,                │
│  │                    days_active: [Mon..Sun],               │
│  │                    eligible_tiers (advisory),             │
│  │                    post_shift_rule: NextDayOff | None,    │
│  │                    frequency_cap_days: int | None,        │
│  │                    daily_required: int}]                  │
│  │                                     <-- ★ user-defined    │
│  ├── horizon, constraints, role_preferences, …              │
│  └── (dropped: subspecs, hours block — replaced)            │
└─────────────────────────────────────────────────────────────┘
```

The CP-SAT model becomes a function of these user-defined shapes
rather than baked-in tier names + on-call families.

## 5. Phasing

The full revamp is too big to land safely in one commit. Five phases,
each leaves the tree green and shippable.

### Phase A — Foundation (this session)

Decouples tier from station eligibility, removes subspec, gives
per-station weekend control, and squashes UX bugs. **Does not** touch
the on-call model, the tier count, or the hours/clock-time story —
those land later.

#### A.1 Decouple tier from station eligibility

- **Backend, scheduler/model.py:** Remove
  `if d.tier not in st.eligible_tiers: continue` from the var-creation
  loop. The only eligibility check left is `st_name in
  d.eligible_stations`. Effect: a doctor whose tier *isn't* in a
  station's `eligible_tiers` can still be assigned there if their
  individual `eligible_stations` includes it.
- **Backend, api/validator.py:** Mirror the relaxation. H3
  (eligibility) only checks per-doctor.
- **Backend, scheduler/ui_state.py:** `eligible_tiers` validation
  stays (kept as advisory metadata for the UX), but is no longer
  enforced when building doctor pools.
- **UI, Stations editor:** Rename the chip group from "Eligible tiers
  (locks)" to "Default tiers" with a hint: *"New doctors at these
  tiers will have this station pre-checked. Per-doctor edits override."*
- **UI, Doctors editor:** When adding a doctor at tier T, pre-fill
  their `eligible_stations` with all stations whose advisory
  `eligible_tiers` includes T (already the implicit behaviour; just
  make it explicit and discoverable).

**Migration:** None — existing rosters keep working because the
solver only loosens, never tightens.

**Tests:** new `tests/test_eligibility_decoupled.py` — a senior
explicitly listed on a junior-only station's eligibility list still
gets assigned there.

#### A.2 Remove subspec system

- **Backend, api/models/session.py:** Drop `DoctorEntry.subspec` and
  `SessionState.subspecs`.
- **Backend, scheduler/instance.py:** Drop `Doctor.subspec` and
  `Instance.subspecs`.
- **Backend, scheduler/model.py:** Replace H8's "1 consultant per
  subspec" rule with a configurable count
  `weekend_consultants_required: int = 1` on `ConstraintsConfig`.
  The rule becomes "at least N consultants do `wconsult` on each
  weekend day".
- **Backend, scheduler/ui_state.py:** Drop subspec parsing.
- **Backend, scheduler/persistence.py:** Drop subspec from load/save.
  YAML loading silently ignores any leftover `subspec:` field +
  `subspecs:` list (back-compat).
- **Migration:** All 17 scenarios re-saved without subspec via
  `python scripts/build_scenarios.py`. The cardiology / paeds /
  anaesthesia scenarios that *used* subspec for clinical realism
  fall back to flat consultant lists; the H8 weekend count works
  either way.
- **UI, Doctors editor:** Drop the subspec column.
- **UI, /rules/teams:** Drop the Sub-specs card entirely.
- **UI, Roster fairness panel:** The subspec parity card is removed.

**Tests:** existing scenarios solving + `test_h8_weekend_count.py` —
asserts a feasible solve covers H8 with the configurable count.

#### A.3 Per-station weekend toggle

- **Backend, api/models/session.py:** Add to `StationEntry`:
  - `weekday_enabled: bool = True`
  - `weekend_enabled: bool = False`
- **Backend, scheduler/instance.py:** Mirror on `Station` dataclass.
- **Backend, scheduler/model.py:** The weekend gate becomes
  per-station: `if inst.is_weekend(day) and not st.weekend_enabled:
  continue`. The old global `weekend_am_pm_enabled` flag becomes a
  default applied on first migration (any existing station gets
  `weekend_enabled = state.constraints.weekend_am_pm`); after that
  it's per-station.
- **Backend, api/validator.py:** Mirror in H1 weekend gate.
- **Migration:** Bulk-set `weekend_enabled = constraints.weekend_am_pm`
  for every station on first load. Once written, the flag becomes
  per-station truth.
- **UI, Stations editor:** Two checkboxes per station: "Weekday" /
  "Weekend". Default Weekday=on, Weekend=off.
- **UI, Shape page:** The "12h Day + Night" / "24/7 shifts" presets
  set `weekend_enabled` on all stations together. Other presets
  leave it weekday-only.
- **Tests:** `test_station_weekend_toggle.py` — a station with
  `weekend_enabled=True` produces weekend bookings even when the
  legacy global flag is off; conversely.

#### A.4 UX — backspace cursor jump

The pattern in [Lab/Scaling.tsx:189](ui/src/routes/Lab/Scaling.tsx),
[Solve.tsx](ui/src/routes/Solve), and [Rules/Shape.tsx](ui/src/routes/Rules/Shape.tsx)
applies `Math.max(min, Math.min(max, Number(e.target.value) || N))`
on every keystroke. Backspacing "10" → "1" → "" rewrites empty as
the floor (`1`), the input value gets re-set, and the cursor jumps
to the end.

- **Fix:** add a small `<NumberInput>` primitive in
  `ui/src/components/ui/numberInput.tsx`. It holds a draft string
  in component state, lets the user type freely, and only validates
  + commits on blur or Enter. Empty string is allowed mid-edit.
- Replace the offending raw `<Input type="number">` usages on the
  Lab tabs, Solve, Shape, Stations Required, etc.
- **Tests:** Vitest can't easily test cursor position; a simple unit
  test asserts that typing into the field, deleting all, then typing
  a new number ends up with the new number (no regression of the
  zero-clamp-on-empty behaviour).

#### A.5 Default-label cleanup

- Drop "OR list 08:00–17:00" / "Morning 08:00–13:00" cosmetic
  defaults from the Shape page presets. Defaults: just "AM", "PM",
  "Full day", "Night call". Users wanting clock-time labels type
  them in.
- The "Surgical lists" preset still exists and still flips relevant
  toggles, but doesn't pre-write a clock-time string.

#### A.6 Phase A acceptance criteria

- All 17 bundled scenarios load without errors after `python
  scripts/build_scenarios.py`.
- All existing tests pass.
- New tests for A.1, A.2, A.3 pass.
- A senior-tier doctor whose individual eligibility list includes
  a junior-only station is solvable onto that station.
- A station with `weekend_enabled=True` produces weekend rows.
- Backspacing the last digit of a number input on Lab/Scaling no
  longer jumps the cursor.
- Subspec column / card is gone from the UI; YAMLs without `subspec`
  load cleanly.

### Phase B — On-call revamp

User-defined on-call shift types replace the hard-baked `oncall` /
`ext` / `wconsult` variable families.

#### B.1 Data model

```python
class OnCallType(StrictModel):
    key: str                  # internal id, e.g. "night_full"
    label: str                # display, e.g. "Full call 20:00–08:00"
    start_hour: int           # 0..23
    end_hour: int             # 0..23, may be < start_hour (overnight)
    days_active: list[Weekday]  # MON..SUN, any subset
    eligible_tiers: list[str] # advisory
    daily_required: int = 1   # how many people per active day
    post_shift_rest_hours: int = 11  # statutory rest
    next_day_off: bool = True  # full post-call day off?
    frequency_cap_days: int | None = 3  # 1-in-N (None = uncapped)
    counts_as_weekend_role: bool = False  # for fairness bucketing
```

`SessionState.on_call_types: list[OnCallType]`. Existing rosters
get migrated on load: the legacy `oncall` becomes a
`night_full` type; the legacy weekend `ext` becomes a
`weekend_ext` type; legacy `wconsult` becomes a `weekend_consult`
type.

#### B.2 Solver model

For each on-call type, create a variable family `oc_<key>[d, day]`
where day ∈ days_active days. Constraints:

- **Daily required:** `sum_d oc_<key>[d, day] == daily_required`
  for each active day.
- **Eligibility:** built from per-doctor `eligible_oncall_types: list[str]`
  field (default = advisory tiers); same decoupling story as Phase A.
- **Post-shift rest:** if `next_day_off`, all activities on day+1
  are zeroed when `oc_<key>[d, day] == 1`. Generalises H5.
- **Frequency cap:** if `frequency_cap_days = N`, sliding window
  sum ≤ 1.
- **Mutual exclusion:** a doctor can hold at most one on-call type
  per day (sum of `oc_<key>[d, day]` across keys ≤ 1).

The hard-coded H4 / H5 / H6 / H7 / H8 / weekday_oncall_coverage
constraints are removed; their behaviour becomes user-configurable
via on-call type fields.

#### B.3 H6 / H7 generalisation

H6 ("seniors on-call get the whole day off") and H7 ("juniors on-call
work the PM session") are *patterns* tied to specific tier classes.
Phase B makes them per-on-call-type fields:

```python
class OnCallType(...):
    works_full_day: bool = False    # like H6 — no station work
    works_pm_only: bool = False     # like H7 — PM station required
```

#### B.4 UI

- New `/setup/oncall` sub-tab: list + edit on-call types.
- Each type card has: name, time range slider (0–24h, can wrap),
  day-of-week chips (M T W T F S S), required count, post-shift
  rules (next-day-off toggle, rest-hours number, frequency cap).
- The Rules → Constraints page loses H4–H7 + weekday_oncall +
  weekend_am_pm + h8 specific toggles. They're replaced by the
  on-call type configuration.

#### B.5 Migration

Auto-migrate any pre-Phase-B SessionState on load:

- Adds three default on-call types: `night_full` (Mon–Sun, 20:00–
  08:00), `weekend_ext` (Sat+Sun, 08:00–20:00), `weekend_consult`
  (Sat+Sun, 08:00–17:00).
- Sets `eligible_tiers` from `Doctor.tier` for each existing
  doctor (juniors+seniors get night_full + weekend_ext, consultants
  get weekend_consult).
- Sets `frequency_cap_days = 3` (matches old H4 default), `next_day_off
  = True` (matches old H5).

This means every existing scenario keeps producing the same roster
the first time it's loaded post-Phase-B. Once loaded and re-saved,
the on-call types are explicit in YAML.

#### B.6 Tests

`tests/test_oncall_types.py` — define a new on-call type, verify
the solver:
- creates the right variable family,
- enforces daily_required,
- enforces frequency_cap,
- skips inactive days,
- enforces post-shift rest.

### Phase C — Variable tier count

Tiers become user-defined entries with classification mapping.

```python
class Tier(StrictModel):
    key: str                 # "registrar", "consultant_a", etc.
    label: str               # "Specialty Registrar"
    classification: Literal["trainee", "specialist", "lead"]
    # Used to wire H6/H7-style on-call patterns + the per-tier
    # balance bucketing. Multiple user tiers can share a class.
```

The solver replaces `for tier in ("junior", "senior", "consultant")`
with `for tier in inst.tiers:`. H6/H7 patterns key off
classification, not on the literal "junior"/"senior" tier names.

UI: `/setup/teams` adds a Tiers card with "Add tier" button. Each
tier picks a classification from the dropdown.

Migration: existing rosters get auto-mapped:
- `junior` → tier(key=junior, classification=trainee)
- `senior` → tier(key=senior, classification=specialist)
- `consultant` → tier(key=consultant, classification=lead)

### Phase D — Clock-time AM/PM with auto-hours

Each station session gets `start_hour: int` + `end_hour: int`. The
`Hours` block goes away; per-doctor weekly hours are computed from
station times + on-call type times.

The solver doesn't need per-shift wall-clock times to function — they
matter only for the workload weight and the printable summary. So
this phase is mostly UI + reporting.

## 6. Cross-cutting concerns

### 6.1 YAML schema versioning

Every saved YAML has `schema_version: 1` today. Phase A bumps to
`schema_version: 2` (drops subspec, adds per-station weekend).
Phase B bumps to 3 (on-call types). Phase C bumps to 4 (tiers list).
Phase D bumps to 5 (station times).

Loaders accept any older version and migrate forward. Saved files
are always written at the current version.

### 6.2 OpenAPI / typed UI

Each phase regenerates `ui/src/api/openapi.json` and
`ui/src/api/types.ts` so the TypeScript layer follows the Pydantic
shape changes. No manual hook edits needed beyond import-renames.

### 6.3 HF Space deployment

Each phase ends with `python scripts/build_scenarios.py` to verify
all scenarios still solve, plus a deploy via
`bash scripts/deploy_hf.sh`. Phases A and B will likely produce
visibly different solve outputs for some scenarios — that's expected
(per-station weekend, different on-call structure).

### 6.4 Documentation updates

- `docs/CONSTRAINTS.md` — must be revised after Phase A (removes
  subspec) and Phase B (rewrites the on-call section).
- `docs/CHANGELOG.md` — entry per phase.
- `docs/INDUSTRY_CONTEXT.md` §5 — Phase B makes statutory on-call
  rules user-defined, which strengthens the regulatory-conformance
  story. Update note.
- `docs/RESEARCH_METRICS.md` — Phase C revisits the per-tier
  fairness formulae; the math doesn't change but the index variable
  needs renaming.

## 7. Rollout sequence

1. **Phase A** — this session.
   - One commit, one deploy.
   - Tests + 17 scenarios green.
   - CHANGELOG entry.

2. **Phase B** — next session. Larger commit because the solver
   changes more. May land in two sub-commits:
   - B1: data model + migration + tests (no UI yet, on-call types
     editable only via YAML).
   - B2: UI for on-call types + remove the legacy rule toggles.

3. **Phase C** — after Phase B settles. Tier expansion is largely
   independent of B; the order doesn't matter much.

4. **Phase D** — last. Cosmetic + reporting only.

## 8. Open questions

- **C1.** Should on-call types support partial-tier eligibility
  inside one tier (e.g. "only registrars in their final year do
  night call")? Probably yes — it falls out of the per-doctor
  `eligible_oncall_types` list.
- **C2.** Should H11 ("every doctor has a duty every weekday")
  count an on-call shift on a Sat/Sun as an excuse for the next
  weekday's idle penalty? Currently yes via post-call. Phase B
  needs to keep that behaviour.
- **C3.** Phase D: do hours come from session times *plus* a manual
  override field per role? (For shifts where actual hours worked
  diverge from scheduled — e.g. paid vs unpaid breaks.) Probably
  add the override.
- **C4.** Should the existing `role_preferences` (S7) accept
  on-call-type keys after Phase B? Yes — the role string already
  accepts `ONCALL` / `WEEKEND_EXT`; we'll generalise to "any on-call
  type key".

## 9. Risks

- **Phase B is big.** The solver loses three variable families and
  gains a generic one. If we get the migration wrong, every scenario
  produces a subtly different roster on first load. Mitigation:
  golden-file tests on each scenario before/after the migration.
- **YAML schema drift.** If a user has an unsaved YAML from before
  the revamp and pastes it into a post-revamp build, the loader has
  to handle it. Mitigation: explicit schema_version handling +
  back-compat tests.
- **UX regression.** Removing `eligible_tiers` as a hard rule could
  surprise users who relied on it as a guard. Mitigation: keep the
  advisory metadata visible, tooltip explains the new semantics.
- **Phase A is large enough to be its own multi-hour pass.** Better
  to ship A first and reassess B's scope after seeing what changes.

---

## Phase A — concrete file-level checklist

This is the list I'll work from when integrating Phase A. Items are
ordered so the tree stays compilable + green at each step.

| # | File | Change |
|---|---|---|
| 1 | `api/models/session.py` | Drop `DoctorEntry.subspec`, drop `SessionState.subspecs`. Add `StationEntry.weekday_enabled` + `.weekend_enabled`. Add `ConstraintsConfig.weekend_consultants_required`. |
| 2 | `scheduler/instance.py` | Drop `Doctor.subspec`, drop `Instance.subspecs`. Add `Station.weekday_enabled` + `.weekend_enabled`. |
| 3 | `scheduler/ui_state.py` | Drop subspec parsing. Read per-station weekend flags. Keep `eligible_tiers` parsing (now advisory). |
| 4 | `scheduler/model.py` | (a) Remove `if d.tier not in st.eligible_tiers` gate. (b) Replace global weekend gate with per-station `weekend_enabled`. (c) Replace H8 per-subspec rule with `weekend_consultants_required` count. |
| 5 | `scheduler/persistence.py` | Drop subspec serialisation; back-compat ignore on load. Add per-station weekend flags to YAML. Bump `schema_version` to 2. |
| 6 | `api/sessions.py` | Drop subspec wiring. Add weekend-flag wiring. |
| 7 | `api/validator.py` | Per-station weekend gate. H3 eligibility uses per-doctor only. |
| 8 | `scripts/build_scenarios.py` | Remove subspec from every scenario. Set per-station weekend flags. Verify all 17 still solve. |
| 9 | `tests/` | Drop subspec assertions. Add `test_eligibility_decoupled.py`, `test_station_weekend_toggle.py`, `test_h8_weekend_count.py`. |
| 10 | `ui/src/api/openapi.json`, `types.ts` | Regenerate. |
| 11 | `ui/src/api/hooks.ts` | Remove subspec from typed exports if directly referenced. |
| 12 | `ui/src/routes/Setup/Doctors.tsx` | Drop subspec column. |
| 13 | `ui/src/routes/Rules/Teams.tsx` | Drop Sub-specs card. Add per-station weekday/weekend toggles. Rename `eligible_tiers` chip group to "Default tiers" with hint. |
| 14 | `ui/src/routes/Rules/Shape.tsx` | Drop "OR list 08:00–17:00" default labels. Wire weekend-toggle preset behaviour to per-station flags. |
| 15 | `ui/src/components/ui/numberInput.tsx` | New file — controlled-with-draft-string number input. |
| 16 | `ui/src/routes/Lab/Scaling.tsx`, `Solve/*`, `Rules/Shape.tsx`, `Rules/Teams.tsx` (Required field) | Replace bare `<Input type="number">` with `<NumberInput>` where clamp-on-empty bug appears. |
| 17 | `ui/src/components/FairnessPanel.tsx` | Drop subspec parity card. |
| 18 | `docs/CONSTRAINTS.md` | Delete subspec section, rewrite H8 to reference the configurable consultant count, mention per-station weekend. |
| 19 | `docs/CHANGELOG.md` | Append Phase A entry. |

## 10. Phase A — sequence of commits

To keep the tree green at every step, I'll land Phase A as **one
atomic commit** rather than splitting — the changes are interlocked
(removing subspec affects every scenario YAML, which affects every
test). Splitting would force temporary back-compat shims that get
deleted in the next commit.

Commit message draft:

```
Schedule-model revamp Phase A: tier/eligibility decoupling, drop
subspec, per-station weekend, UX fixes

* Solver no longer enforces station.eligible_tiers as a hard rule —
  per-doctor eligible_stations is the truth. Tier still drives
  fairness bucketing.
* Doctor.subspec + SessionState.subspecs removed. H8 weekend
  consultant count moved to a configurable ConstraintsConfig field.
* StationEntry gains weekday_enabled + weekend_enabled. Replaces
  the global weekend_am_pm flag with per-station truth.
* Migration: existing YAMLs load with `subspec:` silently dropped;
  per-station weekend flags inherit from the global toggle once.
  schema_version bumped to 2.
* UX: new <NumberInput> primitive avoids the backspace-jumps-to-end
  bug. Default Shape labels reset to neutral ("AM", "PM", …).
* All 17 scenarios re-built + verified.

Phase B (on-call revamp), C (variable tiers), D (clock-time AM/PM)
land in subsequent passes — see docs/SCHEDULE_MODEL_REVAMP.md.
```

---

## Appendix A — what stays unchanged

- The Lab tabs (Benchmark, Capacity, Sweep, Fairness, Scaling).
  All still work end-to-end after Phase A.
- The Roster page heatmap, edit mode, validation panel, fairness
  panel (minus the subspec card), WTD compliance audit.
- Solve UX: WS streaming, intermediate snapshots, lock-to-overrides.
- Export: grid + list previews, file downloads, mailto, print preview.
- The role-preferences (S7) feature.
- The reproducibility bundle export from `/lab/benchmark`.

These are all stable surfaces and aren't touched by this revamp.

---

## 11. Implementation context for the integrating agent

> **You are picking up this revamp.** This section is the
> "what you'll wish someone told you on day 1" briefing. Read it
> end-to-end before opening any code.

### 11.1 Repo conventions

- **Backend:** Python 3.11, FastAPI, OR-Tools CP-SAT, Pydantic v2,
  pytest. Tests live under `tests/`, named `test_<feature>.py`.
- **Frontend:** Vite + React + TypeScript strict + Tailwind v4 +
  TanStack Query + Zustand + React Router. Lives entirely in
  `ui/src/`.
- **Code style:** see top-level `CLAUDE.md` for the canonical rules.
  Headlines:
  - Default to no comments. Only add a comment when the *why* is
    non-obvious. Don't restate what well-named code does.
  - Don't add multi-paragraph docstrings. One short line max for
    new functions.
  - Don't add backwards-compatibility shims when you can change
    the code. Schema bumps + back-compat loaders for YAML are an
    explicit exception (Phase boundaries demand them).
  - Don't add error handling / fallbacks for situations that can't
    happen. Trust internal callers; only validate at system edges.
- **Branch:** `react-ui`. Don't merge to `main`; the project ships
  from `react-ui` directly.

### 11.2 Build / test / deploy commands

```bash
# Backend tests (full suite, ~5 min — slow because of test_stress.py)
python -m pytest tests/ -x -q

# Skip the slow stress tests during iteration
python -m pytest tests/ -x -q --ignore=tests/test_stress.py

# Single test file (fastest feedback loop)
python -m pytest tests/test_<thing>.py -x -q

# Re-build all 17 scenarios (also verifies they still solve)
python scripts/build_scenarios.py

# Regenerate the OpenAPI spec → TypeScript types after a Pydantic change
python scripts/dump_openapi.py > ui/src/api/openapi.json
(cd ui && pnpm run gen:types)

# UI build (also runs tsc --noEmit; this is the type-check)
cd ui && pnpm build

# Deploy to HF Space (force-pushes a docs-stripped branch onto HF main)
bash scripts/deploy_hf.sh
```

The **OpenAPI regen step is critical** after every change to
`api/models/*.py`. The UI's typed shapes come from the regenerated
`ui/src/api/types.ts`. Forgetting this step is the single most
common reason `pnpm build` fails after a backend edit.

### 11.3 The validator-parity rule (learned the hard way)

`scheduler/model.py` and `api/validator.py` enforce the **same**
hard constraints — the model at solve time, the validator post-solve
(both as a self-check audit and on manual roster edits via
`/api/roster/validate`).

**Every change to a hard constraint in the solver must be mirrored
in the validator.** When this rule was violated during the FULL_DAY
rollout, the result was a green solver + red self-check badge for
every FULL_DAY scenario, with the validator reporting "0/1 people
assigned" because it didn't recognise the paired-AM/PM encoding.

For Phase A specifically:
- Removing `eligible_tiers` as a hard rule → update both
  `scheduler/model.py:256` (var-creation gate) **and** the
  eligibility check in `api/validator.py` H3.
- Per-station `weekend_enabled` → update both the var-creation
  loop's weekend gate **and** `api/validator.py` H1's weekend gate.
- Replacing H8's per-subspec rule → update both files in lockstep.

The regression test pattern that catches this: build a fixture,
solve it via the model, hand the solved assignments to the
validator, assert zero violations. See
[`tests/test_full_day_validator.py`](../tests/test_full_day_validator.py)
for the canonical shape.

### 11.4 Hidden coupling — files that don't *look* relevant

The audit lists below are wider than you'd guess from the plan's §10
checklist. These files reference the affected concepts but aren't on
the obvious "models + UI" axis.

#### subspec — 60 files (Phase A.2 must touch many, can ignore docs)

| Group | Files | What to do in Phase A |
|---|---|---|
| **Pydantic + dataclass** | `api/models/session.py`, `scheduler/instance.py` | Drop the field. |
| **Plumbing** | `api/sessions.py`, `scheduler/ui_state.py`, `scheduler/persistence.py` | Drop subspec parsing in both directions. Silently ignore on load (back-compat). |
| **Solver** | `scheduler/model.py` | H8 weekend rule rewrite. |
| **Validator** | `api/validator.py` | H8 weekend rule mirror. |
| **Pre-solve diagnostics** | `scheduler/diagnostics.py` | Has its own weekend-coverage prereq check that references subspec. |
| **Metrics / fairness** | `api/metrics/fairness.py`, `scheduler/metrics.py` | Drop the subspec parity computation. |
| **Plots / heatmaps** | `scheduler/plots.py` | Drop subspec colouring if any. |
| **Baselines** | `scheduler/baselines.py` | Greedy + random_repair use subspec for weekend coverage. |
| **Default state** | `configs/default.yaml`, `api/routes/state.py` (the seed defaults function) | Both currently produce subspecs. Drop. |
| **Scenario builders** | `scripts/build_scenarios.py` | Every builder function references subspec; rewrite. |
| **Scenario YAMLs** | `configs/scenarios/*.yaml` (all 17) | Auto-regenerated by build_scenarios.py. |
| **Fixtures** | `tests/test_fairness.py`, `tests/test_baselines.py`, `tests/test_role_preferences.py`, `tests/test_full_day*.py`, `tests/test_stress.py`, `tests/test_coverage.py` | Update fixtures to drop subspec. |
| **UI types** | `ui/src/api/openapi.json`, `ui/src/api/types.ts` | Regenerated. |
| **UI editor** | `ui/src/routes/Setup/Doctors.tsx` (subspec column), `ui/src/routes/Rules/Teams.tsx` (Sub-specs card), `ui/src/components/CellEditor.tsx`, `ui/src/components/FairnessPanel.tsx` (subspec parity card), `ui/src/components/WorkloadTable.tsx` (subspec column), `ui/src/lib/roster.ts` (workload helpers) | Drop the field everywhere it surfaces. |
| **Lab manifest** | `configs/scenarios/manifest.json` | Regenerated; will lose subspec mentions in tags. |
| **ScenarioPicker** | `ui/src/components/ScenarioPicker.tsx` | Possibly references subspec in display logic. |
| **Docs (informational only — leave for Phase A doc pass)** | `docs/CONSTRAINTS.md` (must update — solver spec), `docs/RESEARCH_METRICS.md`, `docs/CHANGELOG.md` (add entry), others (cosmetic) | Update only `CONSTRAINTS.md` and `CHANGELOG.md` in Phase A; the rest can drift. |

#### eligible_tiers — 43 files (Phase A.1)

The big surprise: `eligible_tiers` is referenced in test fixtures all
over the place. Decoupling means those fixtures are still valid (they
just become advisory), but tests that *rely* on tier-locked
eligibility for a negative assertion need rewriting.

| Concern | Files |
|---|---|
| **Hard-rule enforcement (must remove)** | `scheduler/model.py:256` (var-creation gate). |
| **Validator mirror (must remove)** | `api/validator.py` H3 eligibility check. |
| **Pre-solve diagnostics** | `scheduler/diagnostics.py` — checks if every required station has at least one tier-eligible doctor. After Phase A, this should check per-doctor instead. |
| **Plumbing (advisory metadata, keep parsing)** | `scheduler/ui_state.py`, `scheduler/persistence.py`, `api/sessions.py`, `api/models/session.py` — keep the field flowing through; just don't enforce it. |
| **UI** | `ui/src/routes/Rules/Teams.tsx` — the chip group. Rename to "Default tiers" with a tooltip. |
| **Tests** | `tests/test_baselines.py`, `tests/test_fairness.py`, `tests/test_role_preferences.py`, `tests/test_full_day*.py`, `tests/test_stress.py`, `tests/test_api_state.py`, `tests/test_coverage.py` — all use `eligible_tiers` in fixtures. Update only those that *assert* it as a hard rule (most don't). |

#### weekend_am_pm — 39 files (Phase A.3)

| Concern | Files |
|---|---|
| **Solver gate (replace with per-station)** | `scheduler/model.py` (var-creation gate, H1, H8, weekday on-call), `api/validator.py` (H1 gate). |
| **Pre-solve / metrics / plots** | `scheduler/diagnostics.py`, `scheduler/metrics.py`, `scheduler/plots.py`, `api/metrics/coverage.py` |
| **Plumbing** | `api/models/session.py` (`ConstraintsConfig.weekend_am_pm`), `scheduler/ui_state.py`, `scheduler/persistence.py`, `api/sessions.py`, `scheduler/instance.py` (`Instance.weekend_am_pm_enabled`) |
| **UI** | `ui/src/routes/Rules/Constraints.tsx` (toggle), `ui/src/routes/Rules/Shape.tsx` (rota presets that set this flag) |
| **Scenarios** | All YAMLs have a `constraints.weekend_am_pm: false/true` line. Migration: bulk-set every station's `weekend_enabled` from this field, then drop the global. |
| **Tests** | `tests/test_coverage.py`, `tests/test_stress.py` |

#### wconsult / WCONSULT / WEEKEND_CONSULT — 32 files

These are the same concept across three identifiers:
- `wconsult` — the CP-SAT variable family in `scheduler/model.py`,
  the assignment-bucket key in result dicts.
- `WCONSULT` — the override role string accepted in the validator
  / overrides parsing.
- `WEEKEND_CONSULT` — the role string in `AssignmentRow.role`
  emitted by `solve_result_to_payload`.

Phase A keeps all three (subspec removal doesn't kill the wconsult
role itself — consultants still cover weekends, just without
sub-spec parity). Phase B is when these go away in favour of a
generic on-call type.

### 11.5 Patterns that have bitten us before

1. **Model + validator drift.** Fixed in 0c7edb8 — see §11.3.
2. **Forgetting OpenAPI regen.** UI build fails with cryptic type
   errors. Fix: `python scripts/dump_openapi.py > ui/src/api/openapi.json`
   then `pnpm run gen:types`.
3. **Default-data drift.** `configs/default.yaml` and the
   `api/routes/state.py:seed_defaults` endpoint produce two
   independent default rosters. They must stay in sync — both
   need the subspec drop in Phase A.
4. **Scenario rebuild forgotten.** When you change the YAML schema,
   the existing `configs/scenarios/*.yaml` files are still on the
   old shape. Run `python scripts/build_scenarios.py` after every
   schema-touching change to rewrite them.
5. **Backspace-clamp regression.** Number inputs that clamp on
   empty string (`Number("") || 1`) cause the cursor jump bug
   (Phase A.4). The fix is the `<NumberInput>` primitive; don't
   write new bare `<Input type="number">` with clamp logic.
6. **Test fixtures with hard-coded subspec / tier strings.** Many
   tests construct `Doctor(tier="consultant", subspec="Neuro", …)`
   inline. Phase A removes the second arg. Run pytest with `-x`
   so you don't get a wall of failures all at once.
7. **`solve_result_to_payload` role-string format.** The serialiser
   in `api/sessions.py` (or wherever `assignments_to_rows` lives)
   emits `STATION_<name>_<AM|PM>`, `ONCALL`, `WEEKEND_EXT`,
   `WEEKEND_CONSULT`. The validator parses these. **Don't change
   the format in Phase A** — wait for Phase B to redesign role
   strings around generic on-call type keys.

### 11.6 Recently-landed features the user owns — DO NOT TOUCH

These were added in parallel to Claude's work and represent
explicit user intent. Don't refactor them as part of this revamp:

- `ui/src/components/CharlesAvatar.tsx` and its use in
  `Layout.tsx` ("Charles' Healthcare Roster Scheduler" header).
- The `/solve/lab/*` route restructure (Lab nests under Solve).
  See [`ui/src/App.tsx`](../ui/src/App.tsx). Also the Setup
  layout that absorbed Rules — `ui/src/routes/Setup/index.tsx`.
- The Lab Capacity tab — `api/routes/lab.py` `/capacity/run`,
  `api/lab/capacity.py`, `ui/src/routes/Lab/Capacity.tsx`,
  `tests/test_lab_capacity.py`. Phase A's model changes might
  ripple into this (capacity uses `session_to_instance`); verify
  it still solves but don't refactor it.
- The Roster page's `RosterExport` inline component
  (Roster absorbed Export — `ui/src/components/RosterExport.tsx`).

Treat these as if they were written by another engineer who
deserves not to be refactored without consultation.

### 11.7 Surfaces to smoke-test after Phase A

After the commit, before deploy, eyeball these manually:

- [ ] All 17 scenarios load (`POST /api/state/scenarios/<id>`) and
      solve. Easiest: run `python scripts/build_scenarios.py` and
      check it prints status for every one.
- [ ] Open `/setup/doctors` → no subspec column.
- [ ] Open `/setup/teams` → no Sub-specs card. The Stations card
      shows weekday/weekend toggles per station.
- [ ] Open `/rules/shape` → preset row applies correctly. Default
      labels are clean ("AM", "PM", "Full day"), not the long-form
      clock-time strings.
- [ ] Open `/lab/scaling` → backspace into the "Doctor counts"
      and "Time (s)" inputs without the cursor jumping.
- [ ] Open `/solve` → solve a scenario; the Solver self-check
      badge is green. (Confirms the validator parity.)
- [ ] Open `/roster` → fairness panel renders without subspec.
      WTD compliance card still works.
- [ ] Open `/lab/capacity` → run a hours-vs-target analysis on
      a loaded scenario; should not crash. (Confirms the recent
      Capacity feature still works post-revamp.)
- [ ] Open `/setup/preferences` → add a role preference for
      ONCALL; solve; the S7 component appears in the score
      breakdown. (Confirms role-preferences still work.)

### 11.8 Critical sequencing notes

1. **Order matters within Phase A.** Don't start UI edits before
   regenerating openapi.json + types.ts. The TypeScript layer
   will refuse to compile if it's out of sync.
2. **Keep the test suite green between sub-steps.** Run
   `pytest tests/ -x -q --ignore=tests/test_stress.py` after each
   logical chunk. If a test fails for a reason unrelated to your
   change, it's probably a broken fixture (subspec arg) — fix it
   in place.
3. **Scenario rebuild last.** Don't regenerate scenarios until
   the model, validator, and persistence layers all agree.
   `build_scenarios.py` solves each scenario as part of the
   build — broken model = build script silently produces broken
   YAMLs.
4. **Bump `schema_version` to 2 on output, accept 1 on input.**
   Add an explicit migration on load: if the YAML has
   `schema_version: 1` (or omits it), apply Phase A's defaults
   (drop subspec, set per-station `weekend_enabled` from the
   global flag).
5. **Don't ship a half-state to HF.** If something breaks
   mid-Phase, don't deploy. The HF Space is the user-facing
   demo; a broken solve there is more visible than a broken test.

### 11.9 Phase B watchpoints (preview)

Phase A's footprint affects Phase B's design. Notes for whoever
picks up B:

- After Phase A, `wconsult` is still a separate variable family.
  Phase B replaces it (and `oncall`, `ext`) with a generic
  `OnCallType` family.
- The S7 role-preferences accept the strings `ONCALL`,
  `WEEKEND_EXT`, `WEEKEND_CONSULT`. Phase B should generalise
  the accepted set to "any user-defined on-call type key" plus
  the legacy three (back-compat). Migration logic: pre-Phase-B
  preferences keying off `ONCALL` automatically map to whatever
  on-call type is created by the legacy migration of `oncall`.
- The validator's H4–H7 + weekday on-call rules become per
  on-call-type. Three of them disappear from
  `ConstraintsConfig` (replaced by per-OnCallType fields); one
  (`h11_enabled`) stays.
- The H6 / H7 patterns (senior on-call gets the day off, junior
  on-call works PM) become `OnCallType.works_full_day`,
  `OnCallType.works_pm_only` flags. Currently they're wired to
  literal `tier == "senior"` / `tier == "junior"` checks.

### 11.10 Phase B1 landed — handoff for B2 + C

**As of commit `<TBD>` on `react-ui`, Phase B1 is shipped.** Backend
on-call rewrite is complete: solver, validator, persistence,
diagnostics, baselines, metrics, scenarios, tests, schema migration
(2 → 3) all use `OnCallType`s. The 5 default migrated types
(`oncall_jr`, `oncall_sr`, `weekend_ext_jr`, `weekend_ext_sr`,
`weekend_consult`) reproduce the legacy ConstraintConfig behaviour
exactly when `legacy_role_alias` is set, so existing scenarios keep
emitting `ONCALL` / `WEEKEND_EXT` / `WEEKEND_CONSULT` role strings
unchanged.

#### What still needs doing

##### B2 — `/setup/oncall` UI editor

The `/setup/constraints` page currently shows a placeholder card
explaining that on-call rules moved to per-type config. We need a
real editor at `/setup/oncall`:

- **Route:** add to [ui/src/App.tsx](../ui/src/App.tsx) under the
  Setup section. Sub-tab navigation in
  [ui/src/routes/Setup/index.tsx](../ui/src/routes/Setup/index.tsx).
- **Component:** new `ui/src/routes/Setup/OnCall.tsx`. Table editor
  with one row per `OnCallType`. Columns + controls per type:
  - **Key** (read-only after creation; snake_case constraint).
  - **Label** (free text).
  - **Days active** — Mon/Tue/.../Sun chip group (toggleable).
  - **Daily required** — `<NumberInput>` (0..N, 0 disables the type).
  - **Frequency cap (1-in-N)** — `<NumberInput>` with empty = no cap.
  - **Next-day-off** toggle (per-type post-shift rest).
  - **Works full day** / **Works PM only** — mutually exclusive
    toggles (legacy H6/H7 patterns).
  - **Counts as weekend role** toggle (drives S3 weekend bucketing
    + H9 lieu day eligibility).
  - **Legacy alias** dropdown — `ONCALL` / `WEEKEND_EXT` /
    `WEEKEND_CONSULT` / `(none)`. Drives role-string emission.
  - **Eligible tiers** — Jr/Sr/Cn chip group (advisory; see Phase A
    decoupling).
- **Hooks:** the typed `useSessionState` already exposes
  `state.on_call_types` after the openapi/types regen. The
  `useAutoSavePatch` PATCH endpoint takes `on_call_types: [...]`
  in its merge dict (lists replace wholesale — see `deep_merge` in
  [api/sessions.py](../api/sessions.py)).
- **Per-doctor `eligible_oncall_types`:** the Doctors editor
  ([ui/src/routes/Setup/Doctors.tsx](../ui/src/routes/Setup/Doctors.tsx))
  currently doesn't expose this field. Add a chip group
  ("Eligible on-call types") next to the existing eligible-stations
  column, populated from the current `state.on_call_types` keys.
- **CSV import:** `DoctorsCsvDrawer` accepts a CSV row with
  `eligible_oncall_types` as a `|`-separated list of type keys.
  Already wired on the backend (parser in
  [scheduler/ui_state.py](../scheduler/ui_state.py); CSV editor needs
  to surface the column).
- **Acceptance:** every existing scenario loads correctly,
  `/setup/oncall` shows the 5 migrated types, editing them
  hot-reloads the solver. Removing the placeholder card from
  [ui/src/routes/Rules/Constraints.tsx](../ui/src/routes/Rules/Constraints.tsx)
  is also part of B2.

##### Phase C — variable tier count

`Doctor.tier` is still a `Literal["junior", "senior", "consultant"]`.
Phase C makes this user-defined.

- **Pydantic model.** New `Tier` model with `key`, `label`,
  `classification: Literal["trainee", "specialist", "lead"]`. Add
  `SessionState.tiers: list[Tier]`. `Doctor.tier` becomes a `str`
  (key reference; validated against the tier list).
- **Dataclass.** Mirror in
  [scheduler/instance.py](../scheduler/instance.py).
  `Instance.tiers: list[Tier]`.
- **Solver.** Replace the literal `for tier in ("junior", "senior",
  "consultant")` triple in
  [scheduler/model.py](../scheduler/model.py) with `for tier in
  inst.tiers`. Per-tier balance (S0–S3) iterates user tiers. The
  `_doctor_signature` and `_apply_redundant_aggregates` helpers also
  need an audit — they string-compare tier names today.
- **Migration.** v3 → v4 in
  [scheduler/persistence.py](../scheduler/persistence.py): synthesise
  `[Tier(key="junior", classification="trainee"),
   Tier(key="senior", classification="specialist"),
   Tier(key="consultant", classification="lead")]` from any v3
  session that lacks a `tiers` list. Schema bump 3 → 4. Existing
  `Doctor.tier` strings remain valid (they're now keys into the
  default tiers list).
- **OnCallType.eligible_tiers / Station.eligible_tiers:** these
  already accept arbitrary strings (just lower-cased + filtered to
  the literal three). Drop the literal filter so user-defined tier
  keys flow through.
- **UI.** `/setup/teams` adds a Tiers card with "Add tier" button.
  Each tier picks a classification from a dropdown. All chip groups
  (eligible_tiers on stations, eligible_tiers on on-call types,
  per-doctor tier dropdown) need to read the user-defined list.
- **Tests.** Add `tests/test_variable_tiers.py` proving:
  (a) a 4-tier department (e.g. junior / registrar / consultant /
  lead) solves end-to-end; (b) classifications propagate correctly to
  H6/H7-style patterns (multiple tiers can share a classification,
  e.g. two "specialist" tiers both treated as senior-equivalent if
  some on-call type's eligible_tiers includes both).

##### Phase D — clock-time AM/PM with auto-hours

Untouched after B1. Plan §6 sketches the data shape; nothing has
shifted in B1 that affects D's design.

#### Build / deploy / smoke checklist for B2 + C

```
[ ] python -m pytest tests/ -x -q --ignore=tests/test_stress.py
[ ] python scripts/build_scenarios.py   ← all 17 solve
[ ] python -m pytest tests/test_self_check.py -q   ← solver/validator parity
[ ] python scripts/dump_openapi.py > ui/src/api/openapi.json
[ ] (cd ui && pnpm run gen:types && pnpm build)
[ ] grep -r "weekday_oncall_coverage\|weekend_consultants_required\|h4_gap" \
        api/ scheduler/ ui/src/   ← empty after B2
[ ] (Phase C) grep -r 'tier == "junior"\|tier == "senior"\|tier == "consultant"' \
        scheduler/   ← empty after C
[ ] CHANGELOG.md entry per commit
[ ] bash scripts/deploy_hf.sh
[ ] curl https://charlesyapai-healthcare-workforce-scheduler-v2.hf.space/api/health
```

#### Pitfalls B1 hit (so B2 / C can avoid them)

1. **`pd.isna` on list values.** When `eligible_oncall_types` is a
   list, `pd.isna(val)` raises "truth value ambiguous". Phase B1's
   `_df_rows` in [api/sessions.py](../api/sessions.py) special-cases
   lists — keep that pattern when adding more list-valued doctor /
   station columns.
2. **H9 lieu day + tight senior bench.** With weekday on-call ON
   (default for v2 SessionState) and 3 seniors over a long horizon,
   the per-type H4 1-in-3 cap + H5 next_day_off + H9 lieu day combo
   becomes infeasible. Phase B1 bumped the seed default senior
   fraction (0.15 → 0.20) and the ICU scenario's senior bench
   (4 → 5). Watch for the same trap in any new test fixture or
   scenario.
3. **Solver var maps used as locals.** Phase A's solver had `oncall`,
   `ext`, `wconsult` as named local dicts; the snapshot logic, warm
   start, and SolveResult construction all referenced them by name.
   Phase B's `oc_vars: dict[str, dict[...]]` is keyed by type key.
   Phase B1's `_IntermediateLogger` snapshot uses
   `f"oncall_by_type::{type_key}"` keys; the WS handler in
   [api/routes/solve.py](../api/routes/solve.py) re-nests them. If
   you add new top-level snapshot keys, follow the same pattern.
4. **Validator reports `H6` / `H7` / `H9` now.** The validator-
   tracked rules list in
   [api/sessions.py](../api/sessions.py) `_VALIDATOR_RULES` lost
   `weekday_oc` and gained `H6, H7, H9`. UI assertions / tests that
   pattern-match `rules_failed` keys may need updating.
5. **`assignments_to_rows` reads `oncall_by_type` first.** Pre-B
   callers passed `oncall` / `ext` / `wconsult` directly. Post-B,
   the canonical key is `oncall_by_type`. Legacy keys are a fallback.
   Don't duplicate by passing both — the function picks one path.

---

## Appendix B — exact grep audit (for rapid file location)

Generated 2026-04-26 via `Grep`. If the integrating agent runs the
same grep and the file count differs by more than ±2, something has
moved in the tree since this plan was written.

- **`subspec`**: 60 files (matches across `api/`, `scheduler/`,
  `ui/`, `tests/`, `configs/`, `docs/`, `scripts/`).
- **`eligible_tiers`**: 43 files.
- **`weekend_am_pm`**: 39 files.
- **`wconsult|WCONSULT|WEEKEND_CONSULT`**: 32 files.

Run `Grep` with `output_mode=files_with_matches` for the full list
on each.

---

## Appendix C — Phase A's "definition of done"

Use this as the final gate before deploying:

```
[ ] python -m pytest tests/ -x -q   ← all pass (allow ~5 min)
[ ] cd ui && pnpm build             ← clean (no TS errors)
[ ] python scripts/build_scenarios.py   ← all 17 solve
[ ] git diff --stat HEAD~1          ← inspect; no surprises
[ ] grep -r "subspec" api/ scheduler/ tests/ ui/src/   ← empty
[ ] grep -r "eligible_tiers" scheduler/model.py | grep -v "advisory"  ← empty
[ ] curl https://charlesyapai-healthcare-workforce-scheduler-v2.hf.space/api/health  ← {"status":"ok",…} after deploy
[ ] Smoke-test surfaces from §11.7
[ ] CHANGELOG.md entry committed
```
