## First-feasible vs Total Wall Time (Dashboard)

**What it shows.** Grouped bars per problem size. For each (doctors × days)
pair, one bar is the **time to the first feasible solution** and the other
is the **total wall time** the solver ran (either to proved optimality or
to the time limit).

**How to read it.**
- If the two bars are nearly equal, the solver finds a feasible solution
  just before concluding — polishing time was minimal.
- If the "first feasible" bar is much shorter than the total, the solver
  spent most of its time improving / proving optimality. For an interactive
  UI, users can see a result almost immediately and the rest is
  optimization in the background.

**What to focus on.**
- **First-feasible bar**: this is the time the user actually waits before
  seeing a roster. Keep it under 10 s for the 30–100 doctor target sizes.
- **The ratio total / first_feasible**. A high ratio (e.g. 10×) argues for
  a "show first feasible now, keep refining" UI pattern.
- **Missing "first feasible" bars** mean the solver hit the time limit
  without finding any feasible solution. Treat as `UNKNOWN` and investigate
  with the L1 pre-solve sniff + L3 soft-relax explainer.
