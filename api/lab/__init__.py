"""Batch-runner infrastructure for the Lab tab.

Thin layer on top of `scheduler.solve` + `scheduler.baselines.*`. A
batch enumerates (solver × seed) tuples, executes them serially
(Phase 2 — no async), and aggregates comparative metrics so the UI
can show CPSAT vs greedy vs random_repair side by side.

Deliberately no disk persistence: batches live in a per-process LRU
cache. HF Spaces restart wipes lab history; users who care about
reproducibility should download the bundle (Phase 3).
"""
