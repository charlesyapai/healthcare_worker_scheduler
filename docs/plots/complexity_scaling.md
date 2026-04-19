## Complexity Scaling (Dashboard)

**What it shows.** Log-log scatter. X axis: `N_doctors × N_days` (proxy for
problem scale). Y axis: number of CP-SAT variables in the final model.
Bubble size = wall time. Color = solve status.

**How to read it.**
- Variable count should grow roughly linearly with `N × D` (straight line
  on log-log). A sudden jump in variable count without a size jump
  indicates a model-structure cliff — worth investigating.
- Bubble-size tells you which scales are cheap vs expensive.
- Colour clumping: if all `FEASIBLE`-status bubbles are on the right, the
  solver is hitting the time limit specifically on large problems.

**What to focus on.**
- **The largest bubble with status `OPTIMAL`** — the biggest problem the
  solver can prove optimal within the time budget. This defines the
  "comfortable" operating range.
- **Red / feasible-only bubbles**. These are the problems where you'd
  want the streaming UI pattern, or a second pass.
