## Penalty Breakdown

**What it shows.** A stacked-area chart of every soft-objective component
(S1–S4) at each intermediate solution. The total height at any time equals
the current objective value.

**Components.**
- `S1_sessions_gap_<tier>` — `(max − min)` of AM+PM session count among
  doctors of that tier, times `balance_sessions` weight.
- `S2_oncall_gap_<tier>` — same for on-call counts (juniors and seniors).
- `S3_weekend_gap_<tier>` — same for total weekend duties.
- `S4_reporting_count` — number of consecutive-day pairs on a
  `is_reporting=True` station, times `reporting_spread` weight.

**How to read it.**
- Components with nonzero final height are the **binding** soft constraints
  — they're what stopped the solver from reaching objective 0.
- Component values that collapse early in the timeline mean the solver
  fixed them cheaply; ones that persist to the end are the hard ones.

**What to focus on.**
- Which component dominates the final objective. Raising its weight will
  make the solver work harder on it (at the cost of the others). Lowering
  the weight tells the solver it's OK to tolerate that imbalance.
- If `S4_reporting_count` is the top contributor, consider whether your
  `is_reporting` flag is on the right stations.
- Large `S3_weekend_gap` usually means some tier has too few people to
  distribute weekends evenly under the 1-in-3 cap.
