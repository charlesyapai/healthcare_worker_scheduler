## Solve-time Heatmap (Dashboard)

**What it shows.** Rows are doctor counts. Columns are horizon lengths in
days. Each cell is the **median wall-clock time** the solver took across
all seeds of that size. Cell labels show the number directly.

**How to read it.**
- Darker cells = slower. The plot is the headline chart for "how long does
  CP-SAT take on this problem class?"
- Scan across a row to see how the same doctor count scales with horizon.
- Scan down a column to see how a fixed horizon scales with doctor count.

**What to focus on.**
- **The 30 × 28 and 50 × 28 cells** — these are the user's primary target
  sizes. If they're fast (< 10 s), no ML layer is needed for the common case.
- **The 200 × 28 cell** — the expansion case. If it's red (> 60 s), that's
  where the ML predictor (or a progressive-relax schedule) starts to pay.
- **Row-to-row jumps**. Linear increase is expected; super-linear means
  the solver is struggling and may benefit from symmetry breaking.
