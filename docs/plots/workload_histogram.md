## Workload Histogram

**What it shows.** Four side-by-side histograms (AM+PM sessions, on-calls,
weekend extended, weekend consult), colored by tier. Each bar is a count of
doctors whose workload of that type fell into that bucket.

**How to read it.**
- A sharp, single-bar histogram per tier means the solver distributed that
  workload evenly within the tier — good balance.
- A spread-out histogram per tier means some doctors got more work than
  others — the tier's `balance_*` soft penalty is binding (look at the
  Penalty Breakdown).

**What to focus on.**
- **Within-tier range**: the rightmost nonzero bar minus the leftmost
  nonzero bar. This is the "fairness gap" being minimized by S1/S2/S3.
- **Between-tier difference** is expected — consultants and juniors do
  different stations and accumulate different counts. Don't try to make
  these match.
- **A bar at zero for a tier that should be working**: usually a bug. For
  example, any consultant with zero on-calls is expected (consultants
  don't on-call); any junior with zero AM+PM on a workable day is not.
