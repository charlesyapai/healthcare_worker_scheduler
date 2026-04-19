## Coverage Slack (Pre-solve)

**What it shows.** One bar per weekday, whose height is
`available_doctor_sessions / required_sessions` for that day. A red dashed
line at `y = 1.0` marks the break-even point.

**How to read it.**
- Bars below 1.0 are **infeasible by necessary condition** — there aren't
  enough doctor-sessions to cover the required slots even before any other
  constraints apply.
- Bars just above 1.0 (e.g. 1.05–1.2) are **tight** — the solver has
  almost no slack to distribute on-calls, lieu days, and balance
  constraints.
- Bars well above 1.5 mean the solver has lots of freedom; balance and
  reporting-spread become the binding constraints instead of coverage.

**What to focus on.**
- **Minimum bar (`coverage_slack_min`)**. This is the single tightest day.
  It sets an upper bound on how much leave or eligibility restriction the
  schedule can absorb.
- **Bars at ~1.0 clustered around the same day of week**. If every
  Monday is tight, you're short-staffed Mondays specifically — often the
  day the real hospital also feels it.
- Because this is pre-solve, it is the fastest way to diagnose
  "my instance is obviously infeasible" without running CP-SAT.
