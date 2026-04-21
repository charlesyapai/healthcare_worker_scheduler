"""Test-wide fixtures for the FastAPI layer."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.sessions import reset_store


@pytest.fixture
def client():
    reset_store()
    with TestClient(app) as c:
        yield c
    reset_store()
