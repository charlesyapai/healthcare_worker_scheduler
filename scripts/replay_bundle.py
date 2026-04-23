"""Replay a Lab-exported bundle and diff against its recorded results.

Usage:
    python scripts/replay_bundle.py path/to/bundle.zip

Unpacks `state.yaml` + `run_config.json` + `results.json`, re-runs every
(solver × seed) cell the batch originally contained, and reports any
divergence. A clean replay (zero divergences) is bit-for-bit
reproducibility — the publication-grade claim VALIDATION_PLAN §1.3
promises.

Limitations:
  - CP-SAT multi-worker runs are non-deterministic even with fixed
    seeds. For strict replay the bundle must have been exported with
    num_workers=1.
  - The script compares objective, status, self-check, and coverage
    shortfall. Exact assignment-dict equality is not enforced because
    multiple optima with identical objective/fairness are valid.
"""

from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path


def _bail(msg: str) -> None:
    print(f"FATAL: {msg}")
    sys.exit(1)


def main() -> None:
    if len(sys.argv) != 2:
        _bail("usage: python scripts/replay_bundle.py path/to/bundle.zip")

    bundle_path = Path(sys.argv[1]).expanduser().resolve()
    if not bundle_path.exists():
        _bail(f"{bundle_path} does not exist")

    # Defer imports until after argparse so `--help`-style failures are
    # cheap even before ortools is importable.
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from api.models.lab import BatchRunRequest, RunConfig  # noqa: E402
    from api.models.session import SessionState  # noqa: E402
    from api.sessions import v1_dict_to_session  # noqa: E402
    from api.lab.batch import reset_store, run_batch  # noqa: E402
    from scheduler.persistence import load_state  # noqa: E402

    with zipfile.ZipFile(bundle_path) as zf:
        names = set(zf.namelist())
        for required in ("state.yaml", "run_config.json", "results.json"):
            if required not in names:
                _bail(f"{bundle_path} is missing {required}")
        state_yaml = zf.read("state.yaml").decode()
        run_cfg_raw = json.loads(zf.read("run_config.json").decode())
        expected = json.loads(zf.read("results.json").decode())

    print(f"[replay] bundle: {bundle_path.name}")
    print(f"[replay] {len(expected['summary']['runs'])} expected run(s)")
    print(f"[replay] git_sha (recorded): {zf.read('git_sha.txt').decode().strip() if 'git_sha.txt' in names else 'unknown'}")

    run_config = RunConfig.model_validate(run_cfg_raw)
    # Solver portfolio to re-run: whatever is in the recorded summary.
    solvers = sorted({r["solver"] for r in expected["summary"]["runs"]})
    seeds = sorted({r["seed"] for r in expected["summary"]["runs"]})
    req = BatchRunRequest(solvers=solvers, seeds=seeds, run_config=run_config)

    updates = load_state(state_yaml)
    state = v1_dict_to_session(updates, base=SessionState())
    reset_store()
    summary = run_batch(state, req, instance_label=expected["summary"]["instance_label"])

    # Index the expected runs for comparison.
    expected_by_cell: dict[tuple[str, int], dict] = {
        (r["solver"], r["seed"]): r for r in expected["summary"]["runs"]
    }
    divergences: list[str] = []
    for actual in summary.runs:
        key = (actual.solver, actual.seed)
        exp = expected_by_cell.get(key)
        if exp is None:
            divergences.append(f"{key}: not present in recorded results")
            continue
        for field in ("status", "objective", "self_check_ok", "coverage_shortfall", "coverage_over"):
            a_val = getattr(actual, field)
            e_val = exp.get(field)
            if a_val != e_val:
                divergences.append(
                    f"{key}.{field}: expected {e_val!r}, got {a_val!r}"
                )

    if divergences:
        print(f"\n[replay] FAIL — {len(divergences)} divergence(s):")
        for d in divergences:
            print(f"  - {d}")
        sys.exit(1)
    else:
        print(f"\n[replay] OK — all {len(summary.runs)} runs reproduce.")


if __name__ == "__main__":
    main()
