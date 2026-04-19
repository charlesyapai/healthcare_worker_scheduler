## On-call Spacing

**What it shows.** Histogram of the number of days between successive
on-calls for the same doctor, across all doctors. A red dashed line marks
the 1-in-3 floor (H4: no two on-calls within 3 days).

**How to read it.**
- Every bar must be at x ≥ 3. A bar at x < 3 is a bug — H4 was violated.
- A tall bar at exactly x = 3 means the solver pushed on-calls as tight as
  the rule allows — usually because available doctors are near capacity.
- A spread to the right (gaps of 4, 5, 6+) means there's slack; on-calls
  could even be redistributed for better balance.

**What to focus on.**
- **Minimum gap** (leftmost nonzero bar). If it's 3, the solver is
  fully saturating the 1-in-3 cap — reducing leave or adding a junior/senior
  would relax this.
- **Mean gap**. Compared to `n_days / oncalls_per_doc`, this tells you
  whether the distribution is fair (mean ≈ expected) or lumpy.
