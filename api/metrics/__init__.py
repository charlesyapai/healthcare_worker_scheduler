"""Per-solve analysis metrics — fairness, coverage, etc.

Pure functions over a SessionState + assignment list. No solver state,
no side effects. Everything here is callable both from the live solve
path (to attach a bias snapshot to SolveResultPayload) and from the
batch-runner in the Lab tab."""
