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

The v1 Streamlit app remains on [`main`](../../tree/main) and is deployed as
a separate Space at
<https://huggingface.co/spaces/charlesyapai/doctor_roster_solver>.
Both deployments share the solver core in [`scheduler/`](scheduler/)
verbatim — v2 is a UI rewrite, not a product pivot.

## What's new in v2

- **SPA shell, no page reloads.** Every interaction stays on the client;
  state syncs to FastAPI via `fetch` / WebSocket.
- **Live solve streaming via WebSocket.** CP-SAT's improving solutions
  arrive as `{type:event,...}` messages; a stop signal reaches the solver
  at its next callback boundary.
- **Proper roster heatmap** with a sticky doctor column and colour-coded
  cells (station AM/PM, on-call, weekend, leave, idle weekday).
- **Snapshot slider** across intermediate solutions with client-side
  workload recomputation as you scrub.
- **Diff view** between any two snapshots — changed cells highlighted.
- **Dark mode**, **keyboard shortcuts** (`g s`, `Ctrl+Enter`, `Ctrl+S`),
  responsive mobile layout.
- **Export**: JSON / CSV / ICS / print-preview / copy-YAML / share-link /
  per-doctor mailto previews.

See [`docs/NEW_UI_PLAN.md`](docs/NEW_UI_PLAN.md) for the full plan and
[`docs/CHANGELOG.md`](docs/CHANGELOG.md) for the v2 entry with the
complete feature list and deviations.

## Run locally

```bash
# Backend — FastAPI on :7860
pip install -r requirements.txt
uvicorn api.main:app --host 0.0.0.0 --port 7860 --reload

# Frontend — Vite on :5173, proxies /api to :7860
cd ui
pnpm install
pnpm dev
```

Open <http://localhost:5173> for the SPA (dev) or
<http://localhost:7860> for the built-bundle mode.

For a single-process production-like run, build the SPA and serve from
uvicorn:

```bash
cd ui && pnpm build && cd ..
uvicorn api.main:app --host 0.0.0.0 --port 7860
```

## Run tests

```bash
python -m pytest tests/ -x -q    # 21 tests, ~105s
cd ui && pnpm typecheck          # strict TypeScript over the whole SPA
```

## Architecture

```
┌───────────────────────────────────────────────────┐
│ Browser (SPA)                                      │
│   React + TS + Tailwind v4                         │
│   • Pages: /setup /rules /solve /roster /export    │
│   • State: TanStack Query (server) + Zustand       │
└─────────────┬──────────────────────┬───────────────┘
              │ REST JSON              │ WebSocket
┌─────────────▼──────────────────────▼───────────────┐
│ FastAPI (uvicorn)                                   │
│   /api/state   GET/PUT/PATCH  session state         │
│   /api/state/yaml              import/export YAML   │
│   /api/diagnose /api/explain   L1 + L3              │
│   /api/solve                   WS streaming solve   │
│   /api/overrides/…             lock-and-re-solve    │
│   /                            static SPA bundle    │
└─────────────┬──────────────────────────────────────┘
              │ Python function calls
┌─────────────▼──────────────────────────────────────┐
│ scheduler/ (unchanged v1)                           │
│   instance · model · diagnostics · metrics ·        │
│   persistence · plots · ui_state                    │
└─────────────────────────────────────────────────────┘
```

## Repo layout

```
api/                     FastAPI app
  main.py                route wiring + static SPA mount
  routes/{state,yaml_io,diagnostics,solve}.py
  models/{session,events}.py
  sessions.py            cookie-keyed store + adapters to v1 data model
  static/                SPA bundle (built into image by Dockerfile)
ui/                      React SPA source
  src/{App,main}.tsx
  src/routes/…
  src/components/…
  src/api/{client,hooks,solveWs,types,openapi}.ts
  src/store/{solve,ui}.ts
  src/lib/{roster,keys,utils}.ts
scheduler/               UNCHANGED from main (v1 solver)
tests/                   solver tests + new API tests
docs/
  NEW_UI_PLAN.md         v2 plan
  CONSTRAINTS.md         constraint spec
  FEATURES.md            v0.7.1 feature reference
  CHANGELOG.md           history
Dockerfile               multi-stage (Node build + Python runtime)
scripts/dump_openapi.py  regenerate openapi.json
```

## Regenerate API types after a backend change

```bash
python scripts/dump_openapi.py > ui/src/api/openapi.json
cd ui && pnpm gen:types
```

Both `openapi.json` and `types.ts` are committed so the Docker build
doesn't need a running API to typecheck.

## Deployment

HF Spaces Docker SDK on port 7860. The `react-ui` branch is pushed to
GitHub `origin` **and** to the `hf_v2` remote (v2 Space). See
[`docs/CHANGELOG.md`](docs/CHANGELOG.md) for the full v2 release notes.

## License

MIT.
