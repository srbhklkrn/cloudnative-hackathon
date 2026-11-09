import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.store import MemoryStore


@pytest.fixture
def store():
    return MemoryStore()


@pytest.fixture
def client(store):
    with TestClient(create_app(store)) as client:
        yield client
