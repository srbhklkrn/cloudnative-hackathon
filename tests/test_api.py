from fastapi.testclient import TestClient

from backend.main import create_app


def save(client, sid):
    return client.post("/api/agenda", json={"action": "save", "session_id": sid})


def disrupt(client, sid, event_type="room_full", **fields):
    return client.post("/api/demo/disruptions", json={"session_id": sid, "event_type": event_type, **fields})


def test_health_and_metadata(client):
    assert client.get("/healthz").status_code == 200
    assert client.get("/readyz").json()["store"] == "memory"
    assert client.get("/api/meta").json()["semantic_search"] is False


def test_unconfigured_elastic_is_unready_but_alive(monkeypatch):
    monkeypatch.delenv("ELASTICSEARCH_URL", raising=False)
    monkeypatch.delenv("ELASTICSEARCH_API_KEY", raising=False)
    monkeypatch.setenv("DETOUR_STORE", "elasticsearch")
    with TestClient(create_app()) as client:
        assert client.get("/healthz").status_code == 200
        assert client.get("/readyz").status_code == 503
        assert client.get("/api/search").status_code == 503


def test_conflict_and_anonymous_isolation(client, store):
    assert save(client, "session-01").status_code == 200
    assert save(client, "session-02").status_code == 409
    assert save(client, "session-06").status_code == 200
    with TestClient(create_app(store)) as other:
        assert other.get("/api/agenda").json()["sessions"] == []
    assert "HttpOnly" in client.get("/api/agenda").request.headers.get("cookie", "") or client.cookies.get("detour_attendee")


def test_full_disruption_replan_accept_then_consecutive_cancel(client):
    save(client, "session-01")
    save(client, "session-11")
    assert disrupt(client, "session-01").status_code == 200
    search_ids = [x["session"]["id"] for x in client.get("/api/search", params={"q": ""}).json()["results"]]
    assert "session-01" not in search_ids
    plan = client.post("/api/replan", json={}).json()
    assert plan["disruption"]["session_id"] == "session-01"
    assert plan["recommendations"]
    replacement = plan["recommendations"][0]["session"]["id"]
    response = client.post("/api/agenda", json={"action": "accept", "session_id": "session-01", "replacement_id": replacement})
    assert response.status_code == 200
    assert "session-01" not in response.json()["agenda"]["session_ids"]
    assert replacement in response.json()["agenda"]["session_ids"]
    disrupt(client, replacement, "cancel")
    plan = client.post("/api/replan", json={}).json()
    assert plan["disruption"]["session_id"] == replacement


def test_stale_replacement_is_revalidated(client):
    save(client, "session-01")
    disrupt(client, "session-01")
    plan = client.post("/api/replan", json={}).json()
    replacement = plan["recommendations"][0]["session"]["id"]
    disrupt(client, replacement, "cancel")
    response = client.post("/api/agenda", json={"action": "accept", "session_id": "session-01", "replacement_id": replacement})
    assert response.status_code == 409
    assert client.get("/api/agenda").json()["agenda"]["session_ids"] == ["session-01"]


def test_no_alternative_and_reject(client, store):
    save(client, "session-01")
    disrupt(client, "session-01")
    first = client.post("/api/replan", json={}).json()["recommendations"][0]["session"]["id"]
    client.post("/api/agenda", json={"action": "reject", "session_id": "session-01", "replacement_id": first})
    assert first not in [x["session"]["id"] for x in client.post("/api/replan", json={}).json()["recommendations"]]
    for sid in list(store.sessions):
        store.sessions[sid].status = "canceled"
    result = client.post("/api/replan", json={}).json()
    assert result["recommendations"] == [] and result["message"]


def test_accessibility_filters_and_room_move_revokes_verification(client):
    results = client.get("/api/search", params={"accessibility": "step_free"}).json()["results"]
    assert all(x["session"]["accessibility"]["step_free"] for x in results)
    assert client.get("/api/search", params={"accessibility": "teleport"}).status_code == 422
    save(client, "session-01")
    response = disrupt(client, "session-01", "update", room="New room")
    assert response.status_code == 200 and not response.json()["session"]["accessibility_verified_demo"]
    assert client.get("/api/agenda").json()["affected"]
    results = client.get("/api/search", params={"accessibility": "step_free"}).json()["results"]
    assert "session-01" not in [x["session"]["id"] for x in results]


def test_time_filters_require_offsets_and_compare_utc(client):
    assert client.get("/api/search", params={"after": "2026-11-09T13:00:00"}).status_code == 422
    results = client.get("/api/search", params={"after": "2026-11-09T13:00:00-07:00"}).json()["results"]
    assert len(results) == 15
    assert disrupt(client, "session-01", "update", end="2026-11-09T08:00:00-07:00").status_code == 422


def test_reset_replaces_demo_state_and_clears_agenda(client):
    save(client, "session-01")
    disrupt(client, "session-01")
    assert client.post("/api/demo/reset", json={}).status_code == 200
    assert client.get("/api/agenda").json()["sessions"] == []
    assert len(client.get("/api/search").json()["results"]) == 30
    assert client.get("/api/sessions").json()["disruptions"] == []


def test_write_boundaries_and_no_fake_semantic_search(client):
    assert client.post("/api/demo/reset").status_code == 415
    assert client.post("/api/demo/reset", json={}, headers={"Origin": "https://other.example"}).status_code == 403
    assert client.get("/api/search", params={"mode": "semantic", "q": "kernel"}).status_code == 422
    assert client.get("/api/search").headers["cache-control"] == "no-store"
