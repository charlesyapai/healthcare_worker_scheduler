---
title: Healthcare Roster Scheduler v2
emoji: 🩺
colorFrom: indigo
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
license: mit
short_description: React SPA + FastAPI rewrite of the v1 roster generator
---

# Healthcare Roster Scheduler v2

A React SPA + FastAPI rewrite of the v1 Streamlit roster generator.
**Branch:** `react-ui`. **HF Space:**
<https://huggingface.co/spaces/charlesyapai/healthcare_workforce_scheduler_v2>.

The v1 Streamlit app remains on the [`main`](../../tree/main) branch and is
deployed as a separate Space
(<https://huggingface.co/spaces/charlesyapai/doctor_roster_solver>). The
solver core in [`scheduler/`](scheduler/) is shared verbatim between the
two — v2 is a UI rewrite, not a product pivot.

## Status

**Phase 0 — Scaffolding.** FastAPI backend serving a static placeholder
landing page. The React SPA scaffold lands in Phase 2.

See [`docs/NEW_UI_PLAN.md`](docs/NEW_UI_PLAN.md) §10 for the full phase
sequencing and [`docs/AGENT_PROMPT.md`](docs/AGENT_PROMPT.md) for the
forking-agent brief.

## Why v2

v1 hit UX ceilings imposed by Streamlit:

- Clumsy data-table editing (cell-commit races, no keyboard nav).
- No drag-and-drop on the roster grid.
- `st.rerun()` for streaming is brittle.
- Single-column, desktop-only layout; mobile unusable.
- Forms rebuild on every interaction, dropping in-flight state.

v2 addresses these by moving to a proper SPA while keeping the proven
CP-SAT solver, constraint model, and persistence layer untouched.

See [`docs/NEW_UI_PLAN.md`](docs/NEW_UI_PLAN.md) §1 for the full goals
list and §7 for the new features enabled by the rewrite.

## Run locally (Phase 0)

```bash
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 7860 --reload
```

Then open <http://localhost:7860/>. `/api/health` should return
`{"status":"ok","phase":0,...}`.

## Run tests

```bash
python -m pytest tests/ -x -q
```

The v1 solver tests (`test_smoke.py`, `test_h11.py`, `test_stress.py`)
must stay green through every phase. API-layer tests are added in
Phase 1.

## Repo layout (Phase 0)

```
api/                  FastAPI app + static placeholder (Phase 0)
  main.py             app entry: mounts /api/* + serves static SPA
  static/index.html   placeholder landing page
ui/                   React SPA source — populated in Phase 2
scheduler/            UNCHANGED from main; reused verbatim
tests/                UNCHANGED from main; API tests added in Phase 1
docs/
  NEW_UI_PLAN.md      authoritative v2 plan (~850 lines)
  AGENT_PROMPT.md     forking-agent brief
  FEATURES.md         v0.7.1 feature reference (parity target)
  CONSTRAINTS.md      formal constraint spec (unchanged)
  CHANGELOG.md        release history (v2 entries land in Phase 9)
Dockerfile            single-stage Python runtime (multi-stage in Phase 2)
```

## Deployment

HF Spaces Docker SDK on port 7860, same as v1. The branch is pushed to
GitHub `origin` **and** to the `hf_v2` remote pointing at the v2 Space.

## License

MIT.
