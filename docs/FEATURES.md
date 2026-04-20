# Features — Healthcare Roster Scheduler (v0.6)

A comprehensive reference for every feature currently in the app. Written for
clinicians, roster coordinators, and anyone else who wants to know what each
control does without reading the source.

See `CONSTRAINTS.md` for the formal constraint spec and `CHANGELOG.md` for
the release history.

---

## 1. What the app does

Given a list of doctors, a list of stations, a roster horizon, leave/block
inputs, and a set of rules, the app produces a monthly (or any-length)
roster that:

- Covers every clinical slot that must be covered (stations, on-call,
  weekend duty).
- Respects every doctor's unavailability (leave, call blocks, session blocks).
- Follows the rules you chose to enable (on-call caps, post-call days off,
  weekend rotation, mandatory weekday utilisation, etc.).
- Spreads workload fairly across doctors within each tier, using a weighted
  score that can count weekend work as "heavier" than weekday work.
- Can factor in **prior-period carry-in** — doctors who worked more last
  month get less this month.

The solver streams improving solutions while it searches, so you can watch
the roster get better in real time and stop early once it looks good.

---

## 2. The flow

Three tabs, one sidebar:

1. **Configure** — set up everything.
2. **Solve & Roster** — run the solver, watch it stream, review the final
   roster and workload.
3. **Export** — download JSON or CSV.

The sidebar has solver settings (time limit, CPU workers, feasibility-only
mode) and two diagnostic tools.

---

## 3. Configure tab — section by section

### 3.1 When

- **Roster start date** — the first day of the schedule.
- **Number of days to roster** — horizon length, 1–90.
- **Public holidays in this period** — multi-select from the dates in the
  horizon. Treated like Sundays (weekend coverage rules apply).

### 3.2 Doctors

One row per doctor. Columns:

| Column | What it is |
|---|---|
| **Name** | Display name. Must be unique. |
| **Tier** | `junior`, `senior`, or `consultant`. Drives station eligibility and which on-call roles apply. |
| **Sub-spec** | Required for consultants (`A`, `B`, `C`); leave blank for juniors/seniors. Used by the weekend consultant-rotation rule. |
| **Eligible stations** | Comma-separated list of station names the doctor can work. Example: `CT,MR,US`. |
| **Previous workload** | Integer carry-in from the prior period. Higher = did more last period → solver gives them less this period. Default 0. |

Click the **+** at the bottom of the table to add doctors. Rows can also
be deleted via the table controls.

### 3.3 Stations (in an expander)

Rarely changed — defaults cover a typical radiology department. One row per
station:

| Column | What it is |
|---|---|
| **Name** | Station identifier. Must match the names in the Doctors table. |
| **Sessions** | `AM`, `PM`, or `AM,PM`. |
| **Required** | How many doctors must cover this station each session. |
| **Eligible tiers** | Comma-separated. Example: `consultant` means consultant-only. |
| **Reporting?** | If true, the solver tries to avoid assigning the same doctor to this station on back-to-back days. |

### 3.4 Leave, blocks, and preferences

One row per "block". Columns:

| Column | What it is |
|---|---|
| **Doctor** | Type the doctor's name exactly as in the Doctors table. The app shows a "Known doctors: …" caption above the table for reference. |
| **Date** | The date of the block. Dates outside the horizon are silently ignored. |
| **Type** | Dropdown: `Leave`, `No on-call`, `No AM`, `No PM`. |

**Block type meanings:**

- **Leave** — doctor does not work at all that day (no AM, no PM, no on-call,
  no weekend role).
- **No on-call** — "call block". Doctor will not be given on-call that day,
  but can still be assigned to AM/PM stations.
- **No AM** — doctor will not be assigned to any AM station that day. They
  can still do PM and on-call.
- **No PM** — mirror of No AM.

Use Leave for annual leave / sick days. Use No on-call for protected call
blocks. Use No AM / No PM for specific session preferences.

### 3.5 Rules for the roster

Each rule is toggleable. Defaults match the formal spec in `CONSTRAINTS.md`.

| Toggle | What it does |
|---|---|
| **Cap on-call frequency** (1-in-N) | No doctor has more than one on-call in any N-day window. N is editable (default 3). |
| **Day off after a night on-call** | Post-call: the day after on-call, the doctor has no AM, PM, or further on-call. |
| **Seniors on-call get the whole day off** | On their on-call day, seniors do no AM or PM station work. |
| **Juniors on-call work the PM session** | Juniors cover a PM station on their on-call day. |
| **Weekend coverage** | Sat/Sun must have 1 junior EXT, 1 senior EXT, 1 junior on-call, 1 senior on-call, and 1 consultant per sub-spec. |
| **Day off in lieu after weekend EXT** | A doctor on weekend EXT gets either the Friday-before or Monday-after as a lieu day (no work). |
| **Every doctor has a duty every weekday** | Soft constraint with a penalty per idle day. Excuses: leave, post-call, lieu. High penalty = solver forces full utilisation. |
| **Also roster AM/PM stations on weekends** | Off by default. Only enable if your hospital staffs weekday-style stations on weekends. |

### 3.6 Hours per shift

Used for the **Hours / week** column in the results. Adjust to match your
hospital's shift lengths. **Does not affect solver decisions.** Defaults:

| Shift | Default hours |
|---|---:|
| Weekday AM | 4.0 |
| Weekday PM | 4.0 |
| Weekend AM | 4.0 |
| Weekend PM | 4.0 |
| Weekday on-call | 12.0 |
| Weekend on-call | 16.0 |
| Weekend extended-duty | 12.0 |
| Weekend consultant | 8.0 |

### 3.7 How "fairness" is measured (workload weights)

These turn each assignment into a number. The sum becomes the doctor's
workload score. The solver balances this score across doctors in the same
tier. Weekend roles default to higher weights so weekend call counts as more
work than weekday call. Defaults:

| Role | Default weight |
|---|---:|
| Weekday session | 10 |
| Weekend session | 15 |
| Weekday on-call | 20 |
| Weekend on-call | 35 |
| Weekend extended-duty | 20 |
| Weekend consultant | 25 |

Set any weight to 0 to ignore that role in fairness.

### 3.8 Solver priorities (advanced)

How hard the solver tries to achieve each goal. Higher = more important.
Set to 0 to turn off. Defaults:

| Priority | Default | What it does |
|---|---:|---|
| Fairness: balance weighted workload | 40 | Primary — spreads workload score evenly per tier. |
| Penalty per day a doctor has no duty | 100 | Heavy — forces full utilisation. |
| Balance raw session counts | 5 | Secondary — counts AM+PM sessions. |
| Balance on-call counts | 10 | Secondary — absolute on-call spread per tier. |
| Balance weekend-duty counts | 10 | Secondary — absolute weekend spread per tier. |
| Spread out reporting-desk duty | 5 | Avoids back-to-back reporting days. |

---

## 4. Sidebar

### 4.1 Solver settings

- **Time limit (s)** — how long to run. 5–600. Default 60.
- **CP-SAT workers** — parallel search threads. 1–16. Default 8.
- **Feasibility only** — skip the fairness objective, just find any valid
  roster. Fastest mode.

### 4.2 Diagnostics

- **Diagnose (L1 pre-solve)** — millisecond necessary-condition checks:
  tier headcount, per-station eligibility, weekend sub-spec coverage,
  on-call capacity under the 1-in-N rule, coverage slack per day. Runs
  before any solve and tells you if the problem is provably infeasible
  without burning solver time.
- **Explain infeasibility (L3)** — if the solver returns INFEASIBLE,
  rebuilds the model with slack variables on station coverage and weekend
  coverage, minimises total slack, and reports exactly which constraints
  had to be broken and by how much. Takes ~30 s.

---

## 5. Solve & Roster tab

### 5.1 Running a solve

Click **▶ Solve**. The solver runs in a background thread. The UI updates
every ~0.2 s with:

- A **status line** showing elapsed time, number of improving solutions
  found, current objective value, best-known bound, and the optimality
  gap (as a percentage).
- A **convergence chart** (objective vs. time).
- A **live roster** — the doctor × date grid of the latest improving
  solution. Updates every time the solver finds a better one.
- A **workload peek** expander with the headline table for the current
  best roster.
- An **intermediate solutions log** expander — full table of every
  improving solution with their penalty-component breakdown.

### 5.2 Stop button

Click **⏹ Stop solve (accept current best)** at any time. The solver
exits on its next callback boundary and returns with `FEASIBLE` status
(if any solution was found) or the time-limit behavior otherwise.

### 5.3 Verdict banner

Once the solver stops (naturally or via Stop), you get a one-sentence
verdict at the top of the results:

- **OPTIMAL** — green. Best possible roster under your constraints.
- **FEASIBLE, gap X%** — green if gap < 5%, yellow otherwise. Valid roster
  but not proved optimal.
- Extra line if any **idle doctor-weekdays** — yellow. Tells you the
  solver couldn't give every doctor a duty every weekday; raise the
  "Penalty per day a doctor has no duty" weight or expand capacity.
- **INFEASIBLE** — red. No roster satisfies your constraints. Use
  *Explain infeasibility (L3)* in the sidebar to see why.

### 5.4 Metric strip

Five numbers at a glance:

| Metric | What it is |
|---|---|
| **Status** | OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN. |
| **Solve time** | Wall-clock seconds the solver ran. |
| **First valid roster found at** | Seconds until the first feasible solution. |
| **Penalty score (lower = better)** | The sum of all weighted penalties. 0 = every soft goal satisfied. |
| **Days without duty** | Total doctor-weekdays where a doctor was idle with no excuse. |

### 5.5 Snapshot picker

Any improving solution the solver found during search is available via
"Which roster to view". Pick `Final (best)` for the final result, or an
intermediate if you preferred an earlier one.

### 5.6 Roster grid

Doctor × date table. Cells show the role codes:

| Code | Meaning |
|---|---|
| `AM:CT` | AM at the CT station. Other stations use their own names. |
| `PM:GEN_PM` | PM at the GEN_PM station. |
| `AM:CT / PM:MR` | Both AM and PM assignments on that day. |
| `OC` | On-call (night shift). May combine with PM station for juniors. |
| `EXT` | Weekend extended-duty. |
| `WC` | Weekend consultant. |
| `LV` | Leave. |
| *(blank)* | No duty — a "day without duty" unless excused. |

### 5.7 Per-doctor workload — headline

The headline table is your at-a-glance fairness view:

| Column | What it is |
|---|---|
| **Doctor** | Name. |
| **Tier** | junior / senior / consultant. |
| **Sub-spec** | For consultants. |
| **Workload score** | Weighted sum of assignments + prev-period carry-in. The number the solver balances. |
| **Δ vs. tier median** | How far this doctor is from their tier's median score. Red = over-worked, blue = under-worked, intensity scaled by the largest deviation in that tier. |
| **Hours / week** | Total hours ÷ (n_days / 7). Uses the shift lengths from section 5 of Configure. |
| **Leave days** | Count of leave days in this period. |
| **Days without duty** | Weekday count where the doctor had no role AND wasn't on leave. |

### 5.8 Per-doctor workload — full breakdown (expander)

The detailed view, for anyone who wants to see the underlying counts:

| Column | What it is |
|---|---|
| **Weekday sessions** | AM + PM station assignments on weekdays. |
| **Weekend sessions** | AM + PM station assignments on weekends (if enabled). |
| **Weekday on-call** | Night on-call on weekdays. |
| **Weekend on-call** | Night on-call on Sat/Sun. |
| **Weekend extended** | Weekend EXT role. |
| **Weekend consultant** | Consultant weekend cover. |
| **Leave days** | Same as headline. |
| **Prev-period score** | Carry-in. |
| **This-period score** | Weighted sum of this period's assignments only. |
| **Total (with carry-in)** | = **Workload score** in the headline. |

### 5.9 Advanced analytics (expander)

For power users:

- Convergence chart (objective vs. time).
- Penalty breakdown over time (which soft constraints contributed what).
- Workload histogram per tier.
- On-call spacing distribution.
- Coverage heatmap (station × day).

---

## 6. Export tab

Two download buttons:

- **Download roster (JSON)** — one file with `meta` (status, objective,
  wall_time, start_date, n_days, penalty_components) and `assignments`
  (list of `{doctor, date, role}` rows, dates as ISO strings).
- **Download roster (CSV)** — the same assignments flattened into a CSV
  (columns: `doctor`, `date`, `role`).

Role strings in exports:
- `STATION_<name>_<session>` — e.g. `STATION_CT_AM`.
- `ONCALL`, `WEEKEND_EXT`, `WEEKEND_CONSULT`.

---

## 7. What's NOT in the app (yet)

- **Positive preferences** (e.g. "Dr X prefers AM on Tuesday"). Only the
  negative form (No AM / No PM / No on-call) is currently supported.
- **Save/load of the whole instance to disk**. HF Spaces storage is
  ephemeral, so state is lost across Space restarts. Work-in-progress.
- **Per-doctor calendar grid** for entering leave/blocks. Today it's one
  row per (doctor, date, type).
- **Mid-month re-solve** with locked past assignments.
- **End-user definable new hard constraints**. New rules require a code
  change; existing rules are all toggleable.

---

## 8. Architecture (one-paragraph version)

Python + OR-Tools CP-SAT for the solver, Streamlit for the UI, deployed as
a Docker Space on Hugging Face. `scheduler.model.solve(inst, constraints,
workload_weights, stop_event, ...)` builds a CP-SAT model, returns a
`SolveResult` with full assignments + penalty components. Streaming via a
CP-SAT solution callback that posts events into a `queue.Queue` consumed
by the Streamlit main thread across `st.rerun()` boundaries (this is what
enables the live roster + Stop button). No ML model — CP-SAT is fast
enough for the 30–100 doctor range we care about.
