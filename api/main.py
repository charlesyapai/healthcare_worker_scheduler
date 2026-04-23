import os
import subprocess
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

import scheduler
from api.routes import diagnostics, lab, metrics, roster, solve, state, yaml_io

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
app.include_router(metrics.router)          # /api/metrics/{fairness,coverage}
app.include_router(lab.router)              # /api/lab/*


def _resolve_git_sha() -> str:
    """Best-effort code-revision identifier. Reviewers need it in every
    exported bundle so they can replay against the exact solver.

    Priority: GIT_SHA env var (set at container build time on HF Spaces) →
    `git rev-parse HEAD` on a dev machine → "unknown".
    """
    env = os.environ.get("GIT_SHA") or os.environ.get("SPACE_COMMIT")
    if env:
        return env.strip()
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(Path(__file__).resolve().parent.parent),
            stderr=subprocess.DEVNULL,
            timeout=2,
        )
        return out.decode().strip()
    except Exception:
        return "unknown"


# Resolved once at import time. HF Spaces are stateless containers —
# the SHA doesn't change across requests on a live deployment.
GIT_SHA = _resolve_git_sha()


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "phase": 3,
        "scheduler_version": getattr(scheduler, "__version__", "unknown"),
        "git_sha": GIT_SHA,
    }


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="spa")
