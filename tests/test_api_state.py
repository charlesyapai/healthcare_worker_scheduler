"""REST-layer tests for /api/state, /api/state/yaml, /api/diagnose."""

from __future__ import annotations

from datetime import date


def test_health(client) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert isinstance(body["phase"], int)
    assert body["phase"] >= 1
    # Every bundle embeds the SHA so health must surface it too.
    assert "git_sha" in body


def test_seed_populates_defaults(client) -> None:
    r = client.post("/api/state/seed")
    assert r.status_code == 200
    state = r.json()
    assert len(state["doctors"]) == 20
    assert len(state["stations"]) == 8
    assert state["horizon"]["n_days"] == 21
    # Station "CT" should appear with senior + consultant eligibility.
    ct = next(s for s in state["stations"] if s["name"] == "CT")
    assert set(ct["eligible_tiers"]) == {"senior", "consultant"}


def test_put_replaces_state(client) -> None:
    body = {
        "horizon": {"start_date": "2026-05-01", "n_days": 14, "public_holidays": []},
        "doctors": [{
            "name": "Dr A",
            "tier": "junior",
            "eligible_stations": ["US", "GEN_AM"],
        }],
        "stations": [],
    }
    r = client.put("/api/state", json=body)
    assert r.status_code == 200, r.text
    state = r.json()
    assert state["horizon"]["n_days"] == 14
    assert len(state["doctors"]) == 1
    assert state["doctors"][0]["eligible_stations"] == ["US", "GEN_AM"]


def test_patch_merges_partial(client) -> None:
    client.post("/api/state/seed")
    r = client.patch("/api/state",
                     json={"horizon": {"n_days": 30},
                           "constraints": {"h4_gap": 4}})
    assert r.status_code == 200, r.text
    state = r.json()
    assert state["horizon"]["n_days"] == 30
    assert state["constraints"]["h4_gap"] == 4
    # Other fields preserved.
    assert len(state["doctors"]) == 20


def test_patch_rejects_invalid_field(client) -> None:
    client.post("/api/state/seed")
    r = client.patch("/api/state",
                     json={"horizon": {"n_days": "not-a-number"}})
    assert r.status_code == 400


def test_yaml_roundtrip(client) -> None:
    client.post("/api/state/seed")
    client.patch("/api/state",
                 json={"horizon": {"start_date": "2026-05-01", "n_days": 14}})
    exported = client.get("/api/state/yaml").json()["yaml"]
    assert "doctors:" in exported
    assert "horizon:" in exported
    # Round-trip: import the just-exported YAML into a second session.
    client2 = _new_client()
    client2.post("/api/state/yaml", json={"yaml": exported})
    state2 = client2.get("/api/state").json()
    assert state2["horizon"]["n_days"] == 14
    assert state2["horizon"]["start_date"] == "2026-05-01"
    assert len(state2["doctors"]) == 20


def test_yaml_import_rejects_garbage(client) -> None:
    r = client.post("/api/state/yaml", json={"yaml": ":\n-not yaml"})
    # Either parse fails (400) or validation picks up something wrong; either way
    # the state should not become garbage.
    assert r.status_code in (200, 400)
    if r.status_code == 200:
        state = client.get("/api/state").json()
        assert isinstance(state["doctors"], list)


def test_session_cookie_isolation() -> None:
    """Two TestClients → two independent sessions."""
    from fastapi.testclient import TestClient
    from api.main import app
    from api.sessions import reset_store
    reset_store()
    with TestClient(app) as a, TestClient(app) as b:
        a.post("/api/state/seed")
        assert len(a.get("/api/state").json()["doctors"]) == 20
        assert len(b.get("/api/state").json()["doctors"]) == 0
    reset_store()


def test_prev_workload_from_roster_json(client) -> None:
    client.post("/api/state/seed")
    doctors_before = client.get("/api/state").json()["doctors"]
    name = doctors_before[0]["name"]
    roster = {
        "meta": {"start_date": "2026-03-01"},
        "assignments": [
            {"doctor": name, "date": "2026-03-01", "role": "STATION_CT_AM"},
            {"doctor": name, "date": "2026-03-02", "role": "ONCALL"},
        ],
    }
    r = client.post("/api/state/prev_workload",
                    json={"prev_roster_json": roster})
    assert r.status_code == 200, r.text
    doctors_after = r.json()
    assert doctors_after[0]["prev_workload"] > 0


def test_diagnose_seeded_state_is_feasible_or_warns(client) -> None:
    client.post("/api/state/seed")
    r = client.post("/api/diagnose")
    assert r.status_code == 200
    issues = r.json()
    # Default 20-doctor/21-day instance should have no hard errors.
    assert all(i["severity"] != "error" for i in issues), issues


def _new_client():
    from fastapi.testclient import TestClient
    from api.main import app
    return TestClient(app)
