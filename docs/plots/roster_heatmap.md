## Roster Heatmap

**What it shows.** A calendar grid. Rows are doctors (`D0, D1, …`). Columns
are days (`d00, d01, …`). Each cell's color encodes what that doctor is doing
that day:

| Color       | Meaning          |
|-------------|------------------|
| light grey  | off              |
| light blue  | AM station only  |
| medium blue | PM station only  |
| dark blue   | AM + PM          |
| yellow      | on-call          |
| orange      | weekend extended |
| purple      | weekend consult  |
| near-white  | leave (input)    |

**How to read it.**
- Scan each row (one doctor's month). Look for unexpected clusters — e.g.
  three consecutive yellows would violate H4 and is a bug canary.
- Scan each column (one day). Weekend columns should have 1 yellow + 1
  orange per tier and 3 purples (one per subspec).
- Post-call rule (H5): the day after any yellow cell should be grey for
  that doctor.

**What to focus on.**
- **Yellow-followed-by-non-grey**: H5 violation.
- **Rows with sparse color**: a doctor who got very little work — the
  balance constraint should prevent this; if you see it, check leave days.
- **Rows with saturated color**: a doctor whose workload is unusually
  dense — again, balance constraint should prevent it.
