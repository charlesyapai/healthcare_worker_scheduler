from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import scheduler
from api.routes import diagnostics, roster, solve, state, yaml_io

app = FastAPI(
    title="Healthcare Roster Scheduler v2",
    version="2.0.0-phase1",
)

# In dev, the Vite server runs on another port; production serves the built
# SPA from `api/static/` under the same origin so CORS is a no-op there.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["x-session-id"],
)

app.include_router(yaml_io.router)          # /api/state/yaml — register first
app.include_router(state.router)            # /api/state
app.include_router(diagnostics.router)      # /api/diagnose, /api/explain
app.include_router(solve.router)            # WebSocket /api/solve
app.include_router(solve.overrides_router)  # /api/overrides/fill-from-snapshot
app.include_router(roster.router)           # /api/roster/validate


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "phase": 1,
        "scheduler_version": getattr(scheduler, "__version__", "unknown"),
    }


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="spa")
