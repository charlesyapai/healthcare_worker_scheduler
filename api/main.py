from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import ORJSONResponse
from fastapi.staticfiles import StaticFiles

import scheduler

app = FastAPI(
    title="Healthcare Roster Scheduler v2",
    version="2.0.0-phase0",
    default_response_class=ORJSONResponse,
)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "phase": 0,
        "scheduler_version": getattr(scheduler, "__version__", "unknown"),
    }


app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="spa")
