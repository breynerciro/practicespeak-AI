import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture()
def client() -> TestClient:
    """Cliente HTTP contra la app real, sin tocar Ollama (los tests de API
    parchean `ask_ollama`, así que nunca sale al modelo local)."""
    return TestClient(app)
