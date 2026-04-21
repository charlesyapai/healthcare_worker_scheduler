"""Test-wide fixtures for the FastAPI layer."""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.sessions import reset_store


@pytest.fixture
def client():
    """TestClient with a sticky X-Session-Id header — matches the SPA's
    header-based session keying, so tests hit the same code path as the
    browser. WebSocket tests should tack the same id onto /api/solve as
    `?session_id=<id>`."""
    reset_store()
    sid = uuid.uuid4().hex
    with TestClient(app) as c:
        c.headers.update({"X-Session-Id": sid})
        c.session_id = sid  # type: ignore[attr-defined]
        yield c
    reset_store()
