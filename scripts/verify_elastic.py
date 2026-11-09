"""Run with uv run --env-file /secure/path/credentials.env python -m scripts.verify_elastic."""
import json

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.store import ElasticStore


def main():
    store = ElasticStore()
    try:
        store.initialize()
        query = "sniffing interpod conversations"
        keyword = store.search(query, "keyword")
        semantic = store.search(query, "semantic")
        assert store.ready()
        assert len(store.all_sessions()) == 30
        assert semantic and any("networking" in s.topics or "ebpf" in s.topics for s, _ in semantic[:5])
        assert [s.id for s, _ in keyword[:5]] != [s.id for s, _ in semantic[:5]]
        with TestClient(create_app(store)) as client:
            result = client.post("/api/agenda", json={"action": "save", "session_id": "session-01"})
            assert result.status_code == 200, result.status_code
            assert client.get("/api/agenda").json()["agenda"]["session_ids"] == ["session-01"]
            # A second SDK instance establishes that this is persisted data, not process memory.
            second = ElasticStore()
            try:
                agenda, _ = second.get_agenda(client.cookies.get("detour_attendee"))
                assert agenda.session_ids == ["session-01"]
            finally:
                second.close()
        print(json.dumps({"status": "verified", "store": "elasticsearch", "sessions": 30,
            "inference_id": store.inference_id, "query": query,
            "keyword_top5": [s.title for s, _ in keyword[:5]], "semantic_top5": [s.title for s, _ in semantic[:5]],
            "agenda_persistence": "verified with a separate client"}, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
