"""Reproducibility-bundle export.

A bundle is a ZIP that lets a reviewer replay a batch bit-for-bit on a
fresh checkout:
  - state.yaml         session state at run time
  - run_config.json    exact CP-SAT parameters used
  - results.json       BatchSummary + per-run details
  - git_sha.txt        code revision
  - requirements.txt   pinned runtime deps
  - README.md          step-by-step replay instructions

Per `docs/LAB_TAB_SPEC.md §2.3` and `docs/VALIDATION_PLAN.md §1.3`.
"""

from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime
from pathlib import Path

from api.lab.batch import _StoredBatch


_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_REQUIREMENTS = _REPO_ROOT / "requirements.txt"


def _read_requirements() -> str:
    try:
        return _REQUIREMENTS.read_text()
    except Exception:
        return "# requirements.txt not found in this environment\n"


_README_TEMPLATE = """# Reproducibility bundle — batch {batch_id}

Exported {exported_at}

This bundle contains everything needed to replay the benchmark run on a
fresh checkout of the solver at commit `{git_sha}`.

## Contents

| File | What it holds |
|---|---|
| `state.yaml` | Session state used as input (doctors, stations, weights, constraints). |
| `run_config.json` | Exact CP-SAT parameters (`random_seed`, `search_branching`, …). |
| `results.json` | The `BatchSummary` and per-run details we claim. |
| `git_sha.txt` | Code revision this was run against. |
| `requirements.txt` | Pinned runtime deps. |

## How to replay

```bash
git clone https://github.com/charlesyapai/healthcare_worker_scheduler.git
cd healthcare_worker_scheduler
git checkout {git_sha}
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/replay_bundle.py path/to/this/bundle.zip
```

The replay script unpacks the ZIP, re-runs every (solver × seed) cell,
and reports any objective / self-check / coverage divergence against
`results.json`. Zero divergences = bit-for-bit reproduction (with
`num_workers=1`).

## Industry-reliability metrics in this bundle

See `docs/RESEARCH_METRICS.md` for the formulae. Each run records:

- `self_check_ok` — post-solve hard-constraint validator agrees (§1.1).
- `coverage_shortfall` / `coverage_over` (§5.1b).
- `objective`, `best_bound`, `headroom` (§1.1–1.3).
- Fairness payload under `details.<run_id>.fairness` — per-tier FTE-
  normalised Gini, CV, range, std, mean (§4).

## Limitations

- CP-SAT multi-worker runs (`num_workers > 1`) are non-deterministic.
  For strict replay use `num_workers = 1`.
- Bundles exported from HF Space deployments may have `git_sha =
  unknown` if the image was built without the commit SHA baked in;
  the session YAML + results are still valid, only the code-revision
  pointer is lossy.
"""


def build_bundle(stored: _StoredBatch, git_sha: str) -> bytes:
    """Return the ZIP contents as bytes. Caller is responsible for
    streaming to the client under the right Content-Disposition."""
    buf = io.BytesIO()
    exported_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
    summary = stored.summary
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("state.yaml", stored.state_yaml)
        zf.writestr(
            "run_config.json",
            json.dumps(summary.run_config.model_dump(mode="json"), indent=2),
        )
        zf.writestr(
            "results.json",
            json.dumps({
                "summary": summary.model_dump(mode="json"),
                "details": {
                    k: v.model_dump(mode="json")
                    for k, v in stored.details.items()
                },
            }, indent=2, default=str),
        )
        zf.writestr("git_sha.txt", (git_sha or "unknown") + "\n")
        zf.writestr("requirements.txt", _read_requirements())
        zf.writestr(
            "README.md",
            _README_TEMPLATE.format(
                batch_id=summary.batch_id,
                exported_at=exported_at,
                git_sha=git_sha or "unknown",
            ),
        )
    return buf.getvalue()
