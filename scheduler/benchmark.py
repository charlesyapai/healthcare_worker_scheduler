"""Benchmark harness: sweep problem sizes, record CP-SAT solve time.

Run:
  python -m scheduler.benchmark            # full sweep
  python -m scheduler.benchmark --smoke    # quick sanity check
  python -m scheduler.benchmark --help

Output: results/benchmark_<timestamp>.csv
Columns: n_doctors, n_days, seed, status, wall_time_s, objective,
         best_bound, n_vars, n_constraints, time_limit_s, feasibility_only
"""

from __future__ import annotations

import argparse
import csv
import sys
import time
from pathlib import Path

from scheduler.instance import make_synthetic
from scheduler.model import solve

DEFAULT_DOCTORS = (30, 50, 100, 200)
DEFAULT_DAYS = (7, 14, 28)
DEFAULT_SEEDS = (0,)
DEFAULT_TIME_LIMIT_S = 300.0

SMOKE_DOCTORS = (15,)
SMOKE_DAYS = (7,)


def run_sweep(
    doctor_counts: tuple[int, ...],
    day_counts: tuple[int, ...],
    seeds: tuple[int, ...],
    *,
    time_limit_s: float,
    feasibility_only: bool,
    num_workers: int,
    out_path: Path,
    verbose: bool = True,
) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "n_doctors", "n_days", "seed", "status",
        "wall_time_s", "objective", "best_bound",
        "n_vars", "n_constraints",
        "time_limit_s", "feasibility_only",
    ]
    with out_path.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for n_d in doctor_counts:
            for n_days in day_counts:
                for seed in seeds:
                    if verbose:
                        print(f"[run] doctors={n_d} days={n_days} seed={seed} "
                              f"limit={time_limit_s}s feas_only={feasibility_only}",
                              flush=True)
                    inst = make_synthetic(n_d, n_days, seed=seed)
                    res = solve(
                        inst,
                        time_limit_s=time_limit_s,
                        feasibility_only=feasibility_only,
                        num_workers=num_workers,
                    )
                    row = {
                        "n_doctors": n_d,
                        "n_days": n_days,
                        "seed": seed,
                        "status": res.status,
                        "wall_time_s": round(res.wall_time_s, 3),
                        "objective": res.objective,
                        "best_bound": res.best_bound,
                        "n_vars": res.n_vars,
                        "n_constraints": res.n_constraints,
                        "time_limit_s": time_limit_s,
                        "feasibility_only": feasibility_only,
                    }
                    writer.writerow(row)
                    fh.flush()
                    if verbose:
                        print(f"       → {res.status} in {res.wall_time_s:.2f}s "
                              f"(obj={res.objective}, vars={res.n_vars}, "
                              f"cons={res.n_constraints})", flush=True)
    return out_path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="CP-SAT rostering benchmark")
    p.add_argument("--smoke", action="store_true",
                   help="Tiny sweep (10 doctors × 7 days) for a sanity check.")
    p.add_argument("--doctors", type=int, nargs="+", default=None,
                   help="Doctor counts to sweep.")
    p.add_argument("--days", type=int, nargs="+", default=None,
                   help="Day counts to sweep.")
    p.add_argument("--seeds", type=int, nargs="+", default=list(DEFAULT_SEEDS))
    p.add_argument("--time-limit", type=float, default=DEFAULT_TIME_LIMIT_S,
                   help="Per-run wall-time limit in seconds.")
    p.add_argument("--feasibility-only", action="store_true",
                   help="Skip objective. Useful when optimization blows up.")
    p.add_argument("--workers", type=int, default=8,
                   help="CP-SAT num_search_workers.")
    p.add_argument("--out", type=str, default=None,
                   help="Output CSV path. Default: results/benchmark_<ts>.csv")
    args = p.parse_args(argv)

    if args.smoke:
        doctors = SMOKE_DOCTORS
        days = SMOKE_DAYS
        time_limit = min(args.time_limit, 30.0)
    else:
        doctors = tuple(args.doctors) if args.doctors else DEFAULT_DOCTORS
        days = tuple(args.days) if args.days else DEFAULT_DAYS
        time_limit = args.time_limit

    ts = time.strftime("%Y%m%d_%H%M%S")
    out_path = Path(args.out) if args.out else Path("results") / f"benchmark_{ts}.csv"

    path = run_sweep(
        doctor_counts=tuple(doctors),
        day_counts=tuple(days),
        seeds=tuple(args.seeds),
        time_limit_s=time_limit,
        feasibility_only=args.feasibility_only,
        num_workers=args.workers,
        out_path=out_path,
    )
    print(f"\nBenchmark written to: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
