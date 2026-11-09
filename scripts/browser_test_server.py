"""Isolated real-Elasticsearch browser target on port 8081; deletes its own indices on exit.

uv run --env-file /secure/path/credentials.env python -m scripts.browser_test_server
"""
import os
from uuid import uuid4

import uvicorn

from backend.main import create_app
from backend.store import INDICES, ElasticStore


def main():
    original = INDICES.copy()
    prefix = f"detour-demo-browser-{uuid4().hex}"
    isolated = {kind: f"{prefix}-{kind}-v1" for kind in original}
    store = ElasticStore()
    # Refuse to adopt existing data, even if the generated namespace collides.
    assert not any(store.client.indices.exists(index=name) for name in isolated.values())
    INDICES.update(isolated)
    os.environ["APP_VERSION"] = "browser-test"
    os.environ.pop("DETOUR_PUBLIC_ORIGIN", None)
    try:
        store.initialize()
        app = create_app(store)

        @app.get("/__test_scope")
        def test_scope():
            return {"isolated": True, "index_prefix": prefix}

        # Put the test-only route ahead of the production SPA catch-all mount.
        app.router.routes.insert(0, app.router.routes.pop())
        print(f"Isolated browser dataset: {prefix}", flush=True)
        uvicorn.run(app, host="127.0.0.1", port=8081, access_log=False)
    finally:
        # App shutdown closes its client; cleanup uses a fresh client and exact owned names.
        cleanup = ElasticStore()
        try:
            for name in isolated.values():
                assert name.startswith(prefix + "-")
                cleanup.client.options(ignore_status=404).indices.delete(index=name)
            print(f"Deleted isolated browser dataset: {prefix}", flush=True)
        finally:
            cleanup.close()
            store.close()
            INDICES.update(original)


if __name__ == "__main__":
    main()
