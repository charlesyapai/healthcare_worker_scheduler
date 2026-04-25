# Scheduling Constraints — Single Source of Truth

Status: **v0.7** — Phase B1 landed (on-call shift types are now
user-defined; H4/H6/H7/H8/weekday_oncall_coverage replaced by per-type
fields). Phase B2 (UI editor for /setup/oncall) and Phase C (variable
tier count) still pending — see `docs/SCHEDULE_MODEL_REVAMP.md` §11.10
for the handoff brief.
Last updated: 2026-04-27.

This document is the authoritative specification for the CP-SAT model. If the
model and this doc disagree, this doc is wrong — file a changelog entry and
update it.

## 1. Entities

| Concept | Definition |
|---|---|
| Horizon | 28–31 consecutive days. Day 0 is a known weekday (Mon=0 … Sun=6). |
| Doctor tier | `junior`, `senior`, `consultant` — still hard-coded in Phase B; Phase C makes this user-defined. |
| Station | Named workstation. Each station has a session mask (AM, PM, or FULL_DAY), a required headcount per active session, advisory `eligible_tiers`, and per-station `weekday_enabled` / `weekend_enabled` flags. |
| Session | `AM`, `PM`, `FULL_DAY` (paired AM+PM encoding). |
| **OnCallType** | User-defined on-call shift. Fields: `key`, `label`, `start_hour` / `end_hour`, `days_active` (subset of Mon..Sun), `daily_required` (headcount per active day), `frequency_cap_days` (1-in-N cap, None = uncapped), `next_day_off` (post-shift rest), `works_full_day` (legacy H6 senior pattern), `works_pm_only` (legacy H7 junior pattern), `counts_as_weekend_role` (fairness bucketing), `legacy_role_alias` (`ONCALL` / `WEEKEND_EXT` / `WEEKEND_CONSULT` for back-compat role-string emission). |
| Migration default | `oncall_jr`, `oncall_sr` (all 7 days, daily_required=1, freq_cap=3, next_day_off=True, works_pm_only/works_full_day per tier), plus `weekend_ext_jr`, `weekend_ext_sr`, `weekend_consult` (Sat+Sun, daily_required=1, no cap, no post-call). All five carry the matching `legacy_role_alias` so existing scenarios produce identical role strings. |

## 2. Hard constraints (must hold in any feasible roster)

- **H1 — Station coverage.** For every (day, station, session) where the station
  is active in that session AND enabled on that day's kind (weekday or weekend
  per `weekday_enabled` / `weekend_enabled`), the number of assigned doctors
  equals the station's required headcount for that session.
- **H2 — One station per session + one on-call type per day.** A doctor fills
  at most one station in AM, one in PM, and at most one on-call type on any
  given day (mutual exclusion across user-defined types).
- **H3 — Eligibility.** A doctor can only be assigned to a station if the
  station is in that doctor's `eligible_stations`, and to an on-call type
  only if the type's key is in `eligible_oncall_types`. Advisory tier metadata
  on `Station` and `OnCallType` is **not** enforced.
- **H4 — Per-OnCallType frequency cap.** For each type with
  `frequency_cap_days = N >= 2`: in any window of N consecutive days, each
  doctor holds that type at most once. Per-type, not per-doctor-overall.
- **H5 — Post-shift rest.** For each type with `next_day_off = True`: a
  doctor on that type today does no station / on-call work the following
  day. Master override: `ConstraintsConfig.h5_enabled` (when False, every
  type's `next_day_off` is silently ignored).
- **H6 — Full-day-off on-call pattern.** For each type with
  `works_full_day = True`: doctors on this type that day take no AM or PM
  station. Generalises the legacy "senior on-call gets the day off".
- **H7 — PM-only on-call pattern.** For each type with `works_pm_only = True`:
  doctors on this type that day take AM=0 and PM=1 (weekdays only; on
  weekends, PM stations may not exist depending on station weekend_enabled
  flags). Generalises the legacy "junior on-call works PM".
- **H8 — Per-OnCallType daily required.** For each type with
  `daily_required = D > 0`, on each calendar day that's in the type's
  `days_active` (or a public holiday with Sat/Sun in days_active), exactly
  D doctors hold that type. Subsumes the legacy weekend H8 + weekday on-call
  coverage rules.
- **H9 — Day in lieu for weekend roles.** For every doctor assigned an
  on-call type with `counts_as_weekend_role=True` AND no `works_full_day`
  / `works_pm_only` flag set on a Sat or Sun, they receive a full day off
  (no AM, no PM, no on-call) on either the Friday before **or** the Monday
  after, whichever falls inside the horizon. If both fall inside, exactly
  one is chosen. Master toggle: `ConstraintsConfig.h9_enabled`.
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
  total on-call nights (across all types) a given doctor may receive
  in the horizon. `Doctor.max_oncalls: int | None` (None = no cap).
- **H15 — Manual overrides.** Per-assignment hard constraint that forces
  a specific (doctor, day, role) combination. Phase B accepts:
  - `STATION` (with station + session args),
  - `ONCALL_<type_key>` for any user-defined type,
  - legacy `ONCALL` / `EXT` / `WCONSULT` literals — resolved against any
    type whose `legacy_role_alias` matches and that the doctor is
    eligible for.

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

Doctor(id, tier, eligible_stations: frozenset[str],
       eligible_oncall_types: frozenset[str] = frozenset())
Station(name, sessions: tuple[str, ...], required_per_session: int,
        eligible_tiers: frozenset[str],    # advisory only — not enforced
        is_reporting: bool = False,
        weekday_enabled: bool = True,
        weekend_enabled: bool = False)
OnCallType(key, label, start_hour, end_hour,
           days_active: frozenset[int],     # 0=Mon..6=Sun
           eligible_tiers: frozenset[str],  # advisory only
           daily_required: int,
           post_shift_rest_hours: int,
           next_day_off: bool,
           frequency_cap_days: int | None,
           counts_as_weekend_role: bool,
           works_full_day: bool,
           works_pm_only: bool,
           legacy_role_alias: str | None)
```

Additional inputs on `Instance`:
- `on_call_types: list[OnCallType]` — drives every on-call var family + constraint.
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
