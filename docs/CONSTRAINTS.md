# Scheduling Constraints — Single Source of Truth

Status: **v0.6** — Phase A revamp landed (subspec system removed, tier
no longer locks station eligibility, per-station weekday/weekend toggles,
configurable weekend-consultant count).
Last updated: 2026-04-26.

This document is the authoritative specification for the CP-SAT model. If the
model and this doc disagree, this doc is wrong — file a changelog entry and
update it.

## 1. Entities

| Concept | Definition |
|---|---|
| Horizon | 28–31 consecutive days. Day 0 is a known weekday (Mon=0 … Sun=6). |
| Doctor tier | `junior`, `senior`, `consultant`. Each doctor has exactly one tier. |
| Station | Named workstation (e.g. `CT`, `MR`, `US`, `XR_REPORT`, `IR`, `FLUORO`, `GEN_AM`, `GEN_PM`). Each station has a session mask (AM, PM, or FULL_DAY), a required headcount per active session, and per-station `weekday_enabled` / `weekend_enabled` flags. |
| Session | `AM`, `PM`, `NIGHT`, `FULL_DAY` (paired AM+PM encoding). |
| On-call roles | `JUNIOR_ONCALL`, `SENIOR_ONCALL` (both attend at night; see H6/H7 for their day-side patterns). |
| Weekend-only roles | `JUNIOR_EXTENDED`, `SENIOR_EXTENDED`, `CONSULT_WEEKEND` (configurable headcount via `weekend_consultants_required`, default 1). |

## 2. Hard constraints (must hold in any feasible roster)

- **H1 — Station coverage.** For every (day, station, session) where the station
  is active in that session AND enabled on that day's kind (weekday or weekend
  per `weekday_enabled` / `weekend_enabled`), the number of assigned doctors
  equals the station's required headcount for that session.
- **H2 — One station per session.** A doctor fills at most one station in AM,
  and at most one in PM, on any given day.
- **H3 — Station eligibility.** A doctor can only be assigned to a station if
  the station is in that doctor's `eligible_stations` set. `station.eligible_tiers`
  is **advisory metadata only** — it pre-fills new doctors' eligibility lists
  in the UI but is not enforced by the solver.
- **H4 — On-call cap (1-in-3).** For every doctor and every 3 consecutive days,
  at most one of those days has that doctor on on-call (junior or senior).
- **H5 — Post-call off.** The day after any on-call: no AM, no PM, no on-call.
- **H6 — Senior on-call pattern.** On the senior's on-call day: no AM, no PM
  (full day off); the night shift is worked implicitly by the on-call role.
- **H7 — Junior on-call pattern.** On the junior's on-call day: PM session is
  worked, AM is off; the night shift is worked implicitly by the on-call role.
- **H8 — Weekend coverage (Sat & Sun, and public holidays that are not
  adjacent-weekday-treated).** Each weekend day requires:
  - 1 `JUNIOR_EXTENDED`
  - 1 `SENIOR_EXTENDED`
  - 1 `JUNIOR_ONCALL`
  - 1 `SENIOR_ONCALL`
  - `weekend_consultants_required` consultants on `CONSULT_WEEKEND`
    (default 1; configurable via `ConstraintsConfig.weekend_consultants_required`).
  A single doctor fills at most one of these weekend roles on a given day.
  Whether a station's AM/PM slots also run on the weekend is per-station
  (see `Station.weekend_enabled`).
- **H9 — Day in lieu for weekend extended.** For every doctor assigned
  `*_EXTENDED` on a Sat or Sun, they receive a full day off (no AM, no PM, no
  on-call) on either the Friday before **or** the Monday after, whichever
  falls inside the horizon. If both fall inside, exactly one is chosen.
- **H10 — Leave.** Leave days (input) force: no AM, no PM, no on-call, no
  weekend role on that day.
- **H11 — Mandatory weekday assignment (soft).** On every weekday, every
  doctor must be either (a) assigned to an AM or PM station, (b) on-call, or
  (c) excused. Valid excuses: leave (H10), post-call (day after on-call;
  enforced by H5), senior-on-call-day (full day off per H6), lieu day (H9).
  Enforced as a soft constraint S5 with a large default weight so that idle
  doctor-weekdays are minimised when capacity allows, and surfaced as a
  penalty when capacity is insufficient.
- **H12 — Call block.** Per-doctor, per-day hard block on being assigned
  on-call. Unlike leave, the doctor may still be assigned AM/PM stations
  that day. Input via `Instance.no_oncall[doctor_id] → set[day_idx]`.
- **H13 — Session block.** Per-doctor, per-day, per-session hard block.
  Prevents assigning the doctor to any station in that session (AM or PM).
  Unlike leave, other sessions and on-call remain available. Input via
  `Instance.no_session[doctor_id][day_idx] → {"AM" | "PM"}`.
- **H14 — Per-doctor on-call cap.** Optional hard upper bound on the
  number of on-call nights a given doctor may receive in the horizon.
  `Doctor.max_oncalls: int | None` (None = no cap). Policy-driven —
  e.g., part-timers or doctors with medical restrictions.
- **H15 — Manual overrides.** Per-assignment hard constraint that forces
  a specific (doctor, day, role) combination. Used by the "lock this and
  re-solve" workflow. Input via
  `Instance.overrides: list[(doctor_id, day, station_or_None, session_or_None, role)]`
  where role ∈ {"STATION", "ONCALL", "EXT", "WCONSULT"}.

## 3. Soft constraints (objective terms, weights configurable)

All penalties are summed, multiplied by their weight, and minimized.

- **S1 — Workload balance (weekday sessions).** Minimize
  `max(total_AM_PM) − min(total_AM_PM)` across rostered doctors, restricted to
  the tier in question (computed separately per tier so juniors are balanced
  against juniors, etc.).
- **S2 — On-call balance.** Minimize `max − min` of on-call count per
  doctor-within-tier.
- **S3 — Weekend-duty balance.** Minimize `max − min` of weekend-duty count
  (extended + oncall + consult-weekend combined) per doctor-within-tier.
- **S4 — Reporting-station spread.** Penalize every consecutive-day pair where
  the same doctor is on a station flagged `is_reporting=True` (default: only
  `XR_REPORT`).
- **S0 — Weighted workload balance (per tier).** Primary fairness term.
  Each assignment is weighted: weekday session (default 10), weekend session
  (15), weekday on-call (20), weekend on-call (35), weekend EXT (20),
  weekend consultant (25). Per-doctor `weighted_workload[d] + prev_workload[d]`
  is computed; S0 minimises `max − min` of that quantity across doctors in
  a tier. Prior-period carry-in `prev_workload[d]` is an integer input per
  doctor; a doctor who did a lot last period gets a higher baseline and is
  naturally given less work this period.
- **S5 — Idle-weekday penalty (H11).** Per idle doctor-weekday (no station,
  no on-call, no excuse). Default weight 100 — heavy, so the solver will
  eliminate idles wherever capacity allows. **FTE-scaled**: a 0.5-FTE
  doctor's idle day costs half as much, so the solver tolerates more idle
  for part-timers.
- **S6 — Unmet positive preferences.** Per (doctor, day, session) in
  `Instance.prefer_session` that the solver chose not to honour. Default
  weight 5 — soft; the solver honours preferences when doing so doesn't
  conflict with heavier goals.

S0 also FTE-scales: the per-doctor balance target is
`weighted_workload[d] × (100 / fte_pct[d]) + prev_workload[d]`, so a 0.5-
FTE doctor's score is doubled for balance purposes (solver gives them less).

Default weights: `balance_workload=40`, `balance_sessions=5`, `balance_oncall=10`,
`balance_weekend=10`, `reporting_spread=5`, `idle_weekday=100`, `preference=5`.

## 4. Inputs expected by the model

```python
Instance(
    n_days: int,                     # horizon length
    start_weekday: int,              # 0=Mon..6=Sun for day 0
    doctors: list[Doctor],           # see below
    stations: list[Station],         # see below
    leave: dict[doctor_id, set[int]],# forced-off days
    public_holidays: set[int] = (),  # treated as Sundays
    prev_oncall: set[doctor_id] = (),# for H5 continuity at day 0
)

Doctor(id, tier, eligible_stations: set[str])
Station(name, sessions: tuple[str, ...], required_per_session: int,
        eligible_tiers: set[str],          # advisory only — not enforced
        is_reporting: bool = False,
        weekday_enabled: bool = True,
        weekend_enabled: bool = False)
```

Additional inputs on `Instance`:
- `weekend_consultants_required: int = 1` — H8 weekend consultant headcount.
- `prev_workload: dict[doctor_id, int]` — carry-in from prior period for S0.
- `no_oncall: dict[doctor_id, set[day_idx]]` — H12 call blocks.
- `no_session: dict[doctor_id, dict[day_idx, set[session]]]` — H13 session blocks.
- `prefer_session: dict[doctor_id, dict[day_idx, set[session]]]` — S6 positive
  preferences (soft).
- `overrides: list[(did, day, station|None, session|None, role)]` — H15
  manual assignment locks.

Additional inputs on `Doctor`:
- `fte: float` — full-time equivalent in [0.01, 1.0], default 1.0.
- `max_oncalls: int | None` — H14 hard cap on on-call count, default None.

Additional inputs on `solve(...)`:
- `constraints: ConstraintConfig` — toggle each hard constraint on/off and
  parameterise H4's `oncall_gap_days` (default 3).
- `workload_weights: WorkloadWeights` — per-role weights for the S0 balance
  term (and mirrored in the UI's workload score).
- `stop_event: threading.Event | None` — caller-set flag; when set, solver
  stops at the next callback opportunity and returns with FEASIBLE status.

The UI also accepts `HoursConfig` (weekday AM/PM, weekend AM/PM, weekday/
weekend on-call, weekend EXT, weekend consultant) for the **hours / week**
report column. HoursConfig does not affect solver decisions — it's a
display convenience only.

## 5. Defaults used when inputs are not specified (gaps #1–9)

These are the working assumptions until the user confirms. All are toggleable
in `configs/default.yaml` and the benchmark's `--gaps` flag.

| # | Gap | Default |
|---|---|---|
| 1 | Station list | 8 stations: `CT`, `MR`, `US`, `XR_REPORT`, `IR`, `FLUORO`, `GEN_AM` (AM only), `GEN_PM` (PM only). 1 doctor per (station, session). |
| 2 | Eligibility | Per-doctor `eligible_stations` only. `station.eligible_tiers` is advisory (UI hint), not enforced. |
| 3 | Weekday rostering | All three tiers roster weekdays. Default doctor templates pre-fill plausible per-tier eligibility lists; users override individually. |
| 4 | Weekday on-call | 1 junior + 1 senior every night (weekday and weekend). |
| 5 | Weekend AM/PM | Per-station via `weekend_enabled` flag (default false). |
| 6 | Extended duty | Modeled as a boolean role that counts as 1 work-day. No station assignment, no extra hours tracked. |
| 7 | Month boundary seed | Clean start: no `prev_oncall`. |
| 8 | Public holidays | Treated as Sundays. Accepts a list of day indices. |
| 9 | Balance metric | Balance on-call, weekend, and AM+PM separately, per tier (S1–S3). |
| 10 | Weekend consultants | `ConstraintsConfig.weekend_consultants_required` controls H8 consultant headcount (default 1). |

## 6. Decision variables (CP-SAT encoding)

- `assign[d, day, station, session] ∈ {0,1}` — doctor `d` on `station` in that
  session. Created only if `station ∈ d.eligible_stations`, the station is
  active in that session, and the station is enabled on that day's kind
  (weekday vs weekend per the per-station flags). Tier eligibility is
  advisory and not used to gate var creation.
- `oncall_j[d, day] ∈ {0,1}` — junior on-call indicator (only for junior
  doctors).
- `oncall_s[d, day] ∈ {0,1}` — senior on-call indicator (only for senior
  doctors).
- `ext_j[d, day] ∈ {0,1}` — junior extended (weekend days only).
- `ext_s[d, day] ∈ {0,1}` — senior extended (weekend days only).
- `weekend_consult[d, day] ∈ {0,1}` — consultant weekend duty. Sum over
  consultants per weekend day equals `weekend_consultants_required`.
- `lieu[d, day] ∈ {0,1}` — lieu day taken (only defined for Fri/Mon adjacent to
  a weekend-extended assignment).

Auxiliary (for objective):
- `work_sessions[d]` = Σ AM+PM station assignments.
- `oncall_count[d]`, `weekend_count[d]`.
- `tier_max_*`, `tier_min_*` for each tier's balance terms.

## 7. Out of scope

- Mid-month re-solve with locked past assignments. (User confirmed not needed.)
- Pairwise conflicts ("person X cannot work with Y"). (User: no such constraint.)
- Max-hours-per-doctor caps. (User: no such constraint for now.)
- Preference constraints (doctor wants specific days).
- End-user defined new hard constraints (DSL / form-builder). Adding a new
  hard rule requires a code change + a ConstraintConfig toggle. Existing
  rules are toggleable; parameters are editable in the UI.

Fairness-across-months carry-in is **in scope** as of v0.5 via `prev_workload`.
