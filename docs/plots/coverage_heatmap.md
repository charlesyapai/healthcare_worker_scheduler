## Coverage Heatmap

**What it shows.** Rows are days, columns are `station/session` slots (e.g.
`CT/AM`, `CT/PM`, `US/AM`, …). Each cell's value is the number of doctors
assigned to that slot. Darker blue = more doctors.

**How to read it.**
- Every cell should equal the station's `required_per_session`. Any mismatch
  is an H1 violation (shouldn't happen if the solver succeeded).
- Weekend rows will be empty if `weekend_am_pm_enabled=False` (default) —
  weekend work shows up only in the Roster Heatmap.

**What to focus on.**
- **Any cell that doesn't match the required headcount** for that station.
  The diagnostics' coverage-violation count should already be 0; this chart
  is a visual double-check.
- **Column variance**: if you raise `required_per_session` for a station,
  this column darkens uniformly — a quick sanity check on the config.
