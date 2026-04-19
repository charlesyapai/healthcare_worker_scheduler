## Convergence

**What it shows.** Two step lines over wall-clock time. The upper line is the
**objective** of the best solution the solver has found so far (always
non-increasing — solutions only get better). The lower line is the solver's
**best bound** — a proven lower bound on the optimal objective (always
non-decreasing). The gap between them is the **optimality gap** at that
moment.

**How to read it.**
- When the two lines meet, the solver has proved the current solution is
  optimal. Status becomes `OPTIMAL`.
- A flat upper line with a rising bound means the solver is improving its
  lower bound via presolve/propagation without finding new solutions — fine.
- A flat bound with a falling upper line means the search phase is paying
  off but no proof yet.

**What to focus on.**
- **Time to first feasible** (first point on the upper line). Most users
  care about this more than proved optimality — it's when they have
  *something* to show.
- **Final gap**: `(final_obj - final_bound) / final_obj`. Under 5 % is
  usually fine; over 20 % means the solver needed more time or tighter
  constraints.
- **Slope of the upper line**: steep early improvements, then levelling
  off, is the normal pattern. A long flat upper line with time running out
  means the problem is hard for this solver configuration.
