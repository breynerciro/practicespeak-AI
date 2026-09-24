import pytest
from fastapi.testclient import TestClient

from backend.main import app


@pytest.fixture(autouse=True)
def reset_ai_state():
    """Limpia el estado global de ai.py entre tests."""
    from backend.ai import reset_model_cache, reset_topic_history
    reset_model_cache()
    reset_topic_history()
    yield
    reset_model_cache()
    reset_topic_history()


@pytest.fixture()
def client() -> TestClient:
    """Cliente HTTP contra la app real, sin tocar Ollama (los tests de API
    parchean `ask_ollama`, así que nunca sale al modelo local)."""
    return TestClient(app)
