# Scheduling Constraints — Single Source of Truth

Status: **v0.5** — H11 soft constraint added; all H-rules toggleable; weighted
workload model with prior-period carry-in.
Last updated: 2026-04-20.

This document is the authoritative specification for the CP-SAT model. If the
model and this doc disagree, this doc is wrong — file a changelog entry and
update it.

## 1. Entities

| Concept | Definition |
|---|---|
| Horizon | 28–31 consecutive days. Day 0 is a known weekday (Mon=0 … Sun=6). |
| Doctor tier | `junior`, `senior`, `consultant`. Each doctor has exactly one tier. |
| Subspec | Each **consultant** has exactly one of 3 subspecs: `A`, `B`, `C`. Juniors and seniors have `None`. |
| Station | Named workstation (e.g. `CT`, `MR`, `US`, `XR_REPORT`, `IR`, `FLUORO`, `GEN_AM`, `GEN_PM`). Each station has a session mask (AM, PM, or both) and a required headcount per active session. |
| Session | `AM`, `PM`, `NIGHT`. |
| On-call roles | `JUNIOR_ONCALL`, `SENIOR_ONCALL` (both attend at night; see H6/H7 for their day-side patterns). |
| Weekend-only roles | `JUNIOR_EXTENDED`, `SENIOR_EXTENDED`, `CONSULT_WEEKEND` (one per subspec). |

## 2. Hard constraints (must hold in any feasible roster)

- **H1 — Station coverage.** For every (day, station, session) where the station
  is active in that session, the number of assigned doctors equals the station's
  required headcount for that session.
- **H2 — One station per session.** A doctor fills at most one station in AM,
  and at most one in PM, on any given day.
- **H3 — Station eligibility.** A doctor can only be assigned to a station if
  the station is in that doctor's `eligible_stations` set.
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
  - 1 consultant per subspec (`CONSULT_WEEKEND`), i.e. 3 consultants total.
  A single doctor fills at most one of these weekend roles on a given day, and
  they do not also take an AM/PM station that day (weekend AM/PM stations are
  disabled by default; see Gap #5).
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
  eliminate idles wherever capacity allows.

Default weights: `balance_workload=40`, `balance_sessions=5`, `balance_oncall=10`,
`balance_weekend=10`, `reporting_spread=5`, `idle_weekday=100`.

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

Doctor(id, tier, subspec|None, eligible_stations: set[str])
Station(name, sessions: {"AM"|"PM"}, required_per_session: int,
        eligible_tiers: set[str], is_reporting: bool = False)
```

Additional input on `Instance`:
- `prev_workload: dict[doctor_id, int]` — carry-in from prior period for S0.

Additional inputs on `solve(...)`:
- `constraints: ConstraintConfig` — toggle each hard constraint on/off and
  parameterise H4's `oncall_gap_days` (default 3).
- `workload_weights: WorkloadWeights` — per-role weights for the S0 balance
  term (and mirrored in the UI's workload score).

## 5. Defaults used when inputs are not specified (gaps #1–9)

These are the working assumptions until the user confirms. All are toggleable
in `configs/default.yaml` and the benchmark's `--gaps` flag.

| # | Gap | Default |
|---|---|---|
| 1 | Station list | 8 stations: `CT`, `MR`, `US`, `XR_REPORT`, `IR`, `FLUORO`, `GEN_AM` (AM only), `GEN_PM` (PM only). 1 doctor per (station, session). |
| 2 | Station↔subspec | Per-doctor eligibility flag only. No station demands a specific subspec. |
| 3 | Weekday rostering | All three tiers roster weekdays. Juniors/seniors eligible for `GEN_AM`, `GEN_PM`, `US`, `XR_REPORT` only. |
| 4 | Weekday on-call | 1 junior + 1 senior every night (weekday and weekend). |
| 5 | Weekend AM/PM | Disabled. Weekend work is only the 5 roles in H8. |
| 6 | Extended duty | Modeled as a boolean role that counts as 1 work-day. No station assignment, no extra hours tracked. |
| 7 | Month boundary seed | Clean start: no `prev_oncall`. |
| 8 | Public holidays | Treated as Sundays. Accepts a list of day indices. |
| 9 | Balance metric | Balance on-call, weekend, and AM+PM separately, per tier (S1–S3). |

## 6. Decision variables (CP-SAT encoding)

- `assign[d, day, station, session] ∈ {0,1}` — doctor `d` on `station` in that
  session. Created only if `d` is tier-eligible and station-eligible and the
  station is active in that session.
- `oncall_j[d, day] ∈ {0,1}` — junior on-call indicator (only for junior
  doctors).
- `oncall_s[d, day] ∈ {0,1}` — senior on-call indicator (only for senior
  doctors).
- `ext_j[d, day] ∈ {0,1}` — junior extended (weekend days only).
- `ext_s[d, day] ∈ {0,1}` — senior extended (weekend days only).
- `weekend_consult[d, day, subspec] ∈ {0,1}` — consultant weekend duty.
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
