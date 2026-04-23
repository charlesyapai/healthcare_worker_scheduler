# Citing this work

If you use this solver in a publication, please cite both the solver
and the CP-SAT engine it is built on.

## Citing the solver

Until a peer-reviewed paper is accepted, cite the software itself:

```bibtex
@software{healthcare_roster_scheduler,
  title   = {Healthcare Roster Scheduler},
  author  = {Yap, Charles},
  year    = {2026},
  url     = {https://github.com/charlesyapai/healthcare_worker_scheduler},
  version = {<commit-sha>},
  note    = {Nurse Rostering Problem solver built on CP-SAT; includes
             /lab validation surface with FTE-aware fairness, coverage,
             and reproducibility-bundle export.}
}
```

The `version` field should be the git SHA visible on
`/api/health` → `git_sha`. This is the same SHA embedded in every
Lab bundle (`git_sha.txt` + `README.md`).

## Citing CP-SAT (OR-Tools)

```bibtex
@misc{ortools,
  title  = {OR-Tools},
  author = {Perron, Laurent and Furnon, Vincent},
  year   = {2024},
  url    = {https://developers.google.com/optimization/},
  note   = {Version 9.10 or later; SAT solver module ``cp\_model``.}
}
```

## Methodological citations

The formulations we lean on:

- **Nurse Rostering Problem (NRP) — surveys**:
  Burke, De Causmaecker, Vanden Berghe, Van Landeghem (2004);
  Ernst, Jiang, Krishnamoorthy, Sier (2004). See
  [`INDUSTRY_CONTEXT.md §1`](INDUSTRY_CONTEXT.md) for the full list.
- **Benchmark corpora**: INRC-II (2014–15) + Curtois collection (U.
  Nottingham) — adoption status tracked in
  [`VALIDATION_PLAN.md §1.2`](VALIDATION_PLAN.md).
- **Fairness measurement**: Gini + coefficient of variation (CV),
  with FTE normalisation applied before aggregation. Formulae in
  [`RESEARCH_METRICS.md §4`](RESEARCH_METRICS.md).

## Regulatory note

If the paper claims applicability to a specific jurisdiction (UK
NHS / US ACGME / California AB394), ensure the Lab run used the
appropriate regulatory-conformance module. A roster that is
mathematically feasible under H1–H15 is **not necessarily**
compliant with a jurisdiction's statutory limits — that is a
separate, pluggable layer per [`INDUSTRY_CONTEXT.md §5`](INDUSTRY_CONTEXT.md).
