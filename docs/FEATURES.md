# Features — Healthcare Roster Scheduler (v0.7)

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

### 3.2 Tier labels & sub-specialties

Small section to rename the three internal tiers (`junior`, `senior`,
`consultant`) to your hospital's terminology (e.g. "Registrar", "Fellow",
"Consultant"). The labels flow through the workload table, metric strip,
and verdict banner; internal constraint logic still targets the three
semantic tiers.

Sub-specialties are a comma-separated list that defaults to
`Neuro, Body, MSK`. Weekend coverage rule (H8) requires one consultant
per sub-spec on weekends, so edit this to match your actual sub-spec mix.

### 3.3 Doctors

One row per doctor. Columns:

| Column | What it is |
|---|---|
| **Name** | Display name. Must be unique. |
| **Tier** | `junior`, `senior`, or `consultant`. Drives station eligibility and which on-call roles apply. |
| **Sub-spec** | Required for consultants; dropdown sourced from the sub-specialty list. Leave blank for juniors/seniors. |
| **Eligible stations** | Comma-separated list of station names. Example: `CT,MR,US`. |
| **Previous workload** | Integer carry-in from the prior period. Higher = did more last period → less this period. Auto-fillable from the "Import prior-period workload" sidebar uploader. |
| **FTE** | Full-time equivalent, 0.1–1.0, default 1.0. A 0.5-FTE doctor carries ≈ half a full-timer's workload score and is allowed to be idle more. |
| **Max on-calls** | Optional hard cap on this doctor's night-call count for the horizon. Leave blank for no cap. |

Click the **+** at the bottom of the table to add doctors.

### 3.3 Stations (in an expander)

Defaults cover a typical radiology department and are chosen so juniors,
seniors, and consultants all have roughly comparable weekday workload.
Defaults as of v0.6.1:

| Station | Sessions | Required | Eligible tiers | Reporting? |
|---|---|---:|---|:---:|
| CT | AM, PM | 1 | senior, consultant | no |
| MR | AM, PM | 1 | senior, consultant | no |
| US | AM, PM | 2 | all | no |
| XR_REPORT | AM, PM | 2 | all | yes |
| IR | AM, PM | 1 | consultant | no |
| FLUORO | AM, PM | 1 | consultant | no |
| GEN_AM | AM only | 1 | all | no |
| GEN_PM | PM only | 1 | all | no |

That's 18 slot-assignments per weekday in total. If you have ~20 doctors,
each averages ~1 session per weekday (plus on-call rotations and weekend
duty) — realistic clinical time for a typical department. Edit freely to
match your hospital; the **Avg hours / week (by tier)** metric after solve
tells you if your config produces balanced workload.

One row per station:

| Column | What it is |
|---|---|
| **Name** | Station identifier. Must match the names in the Doctors table. |
| **Sessions** | `AM`, `PM`, or `AM,PM`. |
| **Required** | How many doctors must cover this station each session. |
| **Eligible tiers** | Comma-separated. Example: `consultant` means consultant-only. |
| **Reporting?** | If true, the solver tries to avoid assigning the same doctor to this station on back-to-back days. |

### 3.5 Leave, blocks, and preferences

One row per "block". Columns:

| Column | What it is |
|---|---|
| **Doctor** | Type the doctor's name exactly as in the Doctors table. The app shows a "Known doctors: …" caption above the table for reference. |
| **Date (first day)** | Start of the block. Dates outside the horizon are silently ignored. |
| **End date (optional)** | Last day of the block. Blank = single day. Range is inclusive. |
| **Type** | Dropdown: `Leave`, `No on-call`, `No AM`, `No PM`, `Prefer AM`, `Prefer PM`. |

**Block type meanings:**

- **Leave** (hard) — doctor does not work at all that day (no AM, no PM, no on-call, no weekend role).
- **No on-call** (hard) — "call block". Doctor will not be given on-call, but can still do AM/PM stations.
- **No AM** / **No PM** (hard) — session opt-out for that day.
- **Prefer AM** / **Prefer PM** (soft) — positive preference. The solver honours it if doing so doesn't break a heavier goal; each unmet preference adds a small penalty (default weight 5).

**Bulk CSV paste:** expand the "Bulk-add blocks from CSV" section and paste
lines of the form `doctor,start_date,end_date,type` (end_date optional).
Lets you dump a list of leave requests from email in one go.

### 3.6 Manual overrides (lock specific assignments)

Separate table for **hard overrides** that force a specific role on a
specific day. Columns: Doctor, Date, Role (e.g. `STATION_CT_AM`,
`STATION_XR_REPORT_PM`, `ONCALL`, `EXT`, `WCONSULT` — case-insensitive).

**Workflow**: solve once, then on the Solve & Roster tab click **📌 Copy
this roster to overrides** — this fills this table with every current
assignment. Go back to section 6 in Configure, delete the specific rows
you want the solver to re-compute (e.g. the day Dr A called in sick),
and re-solve. The rest of the roster stays identical.

### 3.7 Rules for the roster

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

### 3.8 Hours per shift

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

### 3.9 How "fairness" is measured (workload weights)

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

### 3.10 Solver priorities (advanced)

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
| Honour positive session preferences | 5 | Cost per unmet "Prefer AM/PM" wish. |

---

## 4. Sidebar

### 4.1 Save / Load configuration

Hugging Face Spaces storage is ephemeral — a restart wipes session state.

- **💾 Save YAML** — downloads `{doctors, stations, blocks, overrides, weights,
  hours, constraints, tier_labels, subspecs, horizon}` as a single YAML
  file. Filename includes today's date.
- **Load YAML** — file-uploader. Replaces your current state entirely.
  Missing sections in older files fall back to defaults.
- **Import prior-period workload** (expander) — upload last month's
  JSON export (from the Export tab). The app parses assignments, re-runs
  the weighted-workload formula, and fills each doctor's `prev_workload`
  column. Gives you a turnkey carry-in setup month-over-month.

### 4.2 Solver settings

- **Time limit (s)** — how long to run. 5–3600. Default 60.
- **CP-SAT workers** — parallel search threads. 1–16. Default 8.
- **Feasibility only** — skip the fairness objective, just find any valid
  roster. Fastest mode.

### 4.3 Diagnostics

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
- Extra line if there's a **cross-tier hours gap** — yellow. Fires when
  the lowest-hours tier averages under 60% of the highest. Almost always
  means station eligibility or `required_per_session` needs tuning — one
  tier has far fewer eligible slots than the others.
- **INFEASIBLE** — red. No roster satisfies your constraints. Use
  *Explain infeasibility (L3)* in the sidebar to see why.

### 5.4 Metric strip

Five numbers at a glance:

| Metric | What it is |
|---|---|
| **Status** | OPTIMAL / FEASIBLE / INFEASIBLE / UNKNOWN. |
| **Solve time** | Wall-clock seconds the solver ran. |
| **Days without duty** | Total doctor-weekdays where a doctor was idle with no excuse. |
| **Avg hours / week (by tier)** | `J 45h · S 48h · C 43h`-style summary. Spot imbalances across tiers at a glance. |
| **Penalty score (lower = better)** | The sum of all weighted penalties. 0 = every soft goal satisfied. |

### 5.5 Snapshot picker

Any improving solution the solver found during search is available via
"Which roster to view". Pick `Final (best)` for the final result, or an
intermediate if you preferred an earlier one.

### 5.6 Roster grid

Doctor × date table. Cells are **colour-coded** for quick scanning:

| Colour | Meaning |
|---|---|
| 🟢 green (darker if AM+PM both) | Station work |
| 🟣 purple | On-call (night) |
| 🔵 teal | Weekend EXT or WC |
| ⚪ grey | Leave |
| 🟡 amber | No duty on a weekday — **something to investigate** (tighten capacity or relax constraints) |

Role codes shown in each cell:

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

### 5.9 Alternative views

Three toggles inside the "Alternative views" expander:

- **Station × date** — transposes the grid. Rows are role / station·session;
  cells list the doctors covering that slot. Good for verifying coverage.
- **Per-doctor calendar** — pick a doctor → see their horizon as week rows ×
  Mon–Sun columns. What you'd hand an individual doctor.
- **Today's roster** — pick any date in the horizon → table of who's doing
  what on that day.

### 5.10 Diff against another snapshot

Expander below the roster grid. Pick an intermediate solution (or the
Final one) to compare against. The diff grid shows only cells that
differ, with the text `old → new` and a yellow highlight. A line at the
top reports how many cells changed.

### 5.11 Lock and re-solve

Click **📌 Copy this roster to overrides** above the grid to push every
current assignment into the Manual-overrides table on the Configure tab.
From there you can delete just the rows you want to re-compute (e.g. the
day Dr A called in sick) and hit **▶ Solve** again. Everything you didn't
delete stays exactly as it was. Use this for sick-day coverage, last-minute
changes, or stress-testing the roster.

### 5.12 Advanced analytics (expander)

For power users:

- Convergence chart (objective vs. time).
- Penalty breakdown over time (which soft constraints contributed what).
- Workload histogram per tier.
- On-call spacing distribution.
- Coverage heatmap (station × day).

---

## 6. Export tab

Three download buttons:

- **Download roster (JSON)** — one file with `meta` (status, objective,
  wall_time, start_date, n_days, penalty_components) and `assignments`
  (list of `{doctor, date, role}` rows, dates as ISO strings). Feed this
  to next month's "Import prior-period workload" sidebar to carry the
  score forward.
- **Download roster (CSV)** — the same assignments flattened into a CSV
  (columns: `doctor`, `date`, `role`). Paste into Excel or Google Sheets.
- **📄 Download print-friendly HTML** — single-file HTML with embedded CSS,
  colour-coded cells, and print-media rules. Open in your browser and
  use **File → Print → Save as PDF** for a paper-ready monthly roster.

Role strings in exports:
- `STATION_<name>_<session>` — e.g. `STATION_CT_AM`.
- `ONCALL`, `WEEKEND_EXT`, `WEEKEND_CONSULT`.

---

## 7. What's NOT in the app (yet)

- **Drag-and-drop cell editing** on the roster grid. For now, use "Copy
  this roster to overrides" + delete rows + re-solve.
- **Multi-user collaboration** (two rosterers editing simultaneously).
- **Real PDF output** — today we emit print-ready HTML; you click "Save
  as PDF" in the browser.
- **Direct email / calendar invite publishing** to doctors.
- **Top-3 alternative solutions** side by side. (Was on the roadmap but
  deprioritised — the snapshot picker lets you scrub through the solver's
  intermediate solutions, which covers 80% of that use case.)
- **End-user definable new hard constraints** (DSL). New rules require
  a code change; existing rules are all toggleable.
- **Mobile-optimised layout**. Streamlit's data editors are wide-only.

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
