"""/api/state/yaml — import / export the session state as YAML.

Reuses `scheduler.persistence.dump_state` / `load_state` verbatim so v1 YAML
files remain round-trippable.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from api.models.events import YamlExportResponse, YamlImportRequest
from api.models.session import SessionState
from api.sessions import (
    ServerSession,
    get_session,
    session_to_v1_dict,
    v1_dict_to_session,
)
from scheduler.persistence import dump_state, load_state

router = APIRouter(prefix="/api/state/yaml", tags=["state"])


@router.get("", response_model=YamlExportResponse)
def export_yaml(session: ServerSession = Depends(get_session)) -> YamlExportResponse:
    v1 = session_to_v1_dict(session.state)
    return YamlExportResponse(yaml=dump_state(v1))


@router.post("", response_model=SessionState)
def import_yaml(
    req: YamlImportRequest,
    session: ServerSession = Depends(get_session),
) -> SessionState:
    try:
        updates = load_state(req.yaml)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not parse YAML: {e}")
    try:
        session.state = v1_dict_to_session(updates, base=SessionState())
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid state in YAML: {e}")
    return session.state
