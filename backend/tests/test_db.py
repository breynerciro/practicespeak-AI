import csv
import io

import pytest

pytest.importorskip("faster_whisper", reason="whisper no instalado en este entorno")

import backend.db as db  # noqa: E402
from backend.db import (
    DB_PATH,
    export_anki_csv,
    finish_session,
    reset_for_tests,
    save_corrections,
    start_session,
    stats,
)  # noqa: E402


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """Redirige la base de datos a un archivo temporal por test."""
    reset_for_tests(tmp_path / "test-nova.db")
    yield
    reset_for_tests(DB_PATH)


@pytest.fixture()
def ollama_ok(monkeypatch):
    async def fake_tutor_chat(language, history, message):
        return {"reply": "Hello!", "corrections": []}

    async def fake_immersive_start(language, topic=None):
        return {"topic": topic or "travel", "reply": "Hello!", "corrections": []}

    async def fake_immersive_continue(language, history, user_text):
        return {
            "topic": "travel",
            "reply": "Great!",
            "corrections": [{"error": "i go", "correction": "I went", "explanation": "pasado"}],
        }

    async def fake_correct_grammar(language, text):
        return {"corrected": text, "errors": [], "summary": ""}

    monkeypatch.setattr("backend.main.tutor_chat", fake_tutor_chat)
    monkeypatch.setattr("backend.main.immersive_start", fake_immersive_start)
    monkeypatch.setattr("backend.main.immersive_continue", fake_immersive_continue)
    monkeypatch.setattr("backend.main.correct_grammar", fake_correct_grammar)


class TestDb:
    def test_start_and_stats(self, temp_db):
        sid = start_session("en", "travel", "voice")
        assert sid >= 1
        s = stats()
        assert s["total_sessions"] == 1
        assert s["by_language"]["en"] == 1

    def test_save_corrections_persists_and_dedupes_nothing(self, temp_db):
        sid = start_session("en", "travel", "text")
        n = save_corrections(sid, "en", "travel", "i go to school", [
            {"error": "i go", "correction": "I went", "explanation": "pasado"}
        ])
        assert n == 1
        s = stats()
        assert s["total_corrections"] == 1
        assert s["top_topics_with_errors"]["travel"] == 1

    def test_save_empty_corrections_is_noop(self, temp_db):
        sid = start_session("en", None, "voice")
        assert save_corrections(sid, "en", None, "hola", []) == 0

    def test_export_anki_csv_format(self, temp_db):
        sid = start_session("en", "music", "text")
        save_corrections(sid, "en", "music", "i like musics", [
            {"error": "musics", "correction": "music", "explanation": "incontable"}
        ])
        csv_data = export_anki_csv()
        rows = list(csv.reader(io.StringIO(csv_data)))
        assert rows[0] == ["Front", "Back"]
        assert rows[1][0] == "musics"
        assert "music" in rows[1][1]
        assert "incontable" in rows[1][1]

    def test_finish_session_updates_row(self, temp_db):
        sid = start_session("en", None, "voice")
        finish_session(sid)
        with db._lock:
            row = db._get_conn().execute("SELECT finished_at FROM sessions WHERE id = ?", (sid,)).fetchone()
        assert row["finished_at"] is not None


class TestStatsEndpoints:
    def test_stats_endpoint(self, client, temp_db):
        start_session("pt", "music", "text")
        resp = client.get("/api/stats")
        assert resp.status_code == 200
        assert resp.json()["total_sessions"] == 1

    def test_export_anki_headers(self, client, temp_db):
        resp = client.get("/api/export/anki")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/csv")
        assert "attachment" in resp.headers["content-disposition"]
        assert resp.text.startswith("Front,Back") or resp.text.startswith('"Front","Back"')

    def test_session_finish_ok(self, client, temp_db):
        sid = start_session("en", None, "voice")
        resp = client.post("/api/session/finish", json={"session_id": sid})
        assert resp.status_code == 200

    def test_immersive_start_returns_session_id(self, client, ollama_ok, temp_db):
        resp = client.post("/api/immersive", json={"mode": "start", "topic": "travel"})
        assert resp.status_code == 200
        assert isinstance(resp.json()["session_id"], int)

    def test_immersive_continue_saves_corrections(self, client, ollama_ok, temp_db):
        sid = start_session("en", "travel", "text")
        resp = client.post(
            "/api/immersive",
            json={
                "mode": "continue",
                "message": "i go",
                "session_id": sid,
                "history": [{"role": "assistant", "content": "hi"}],
            },
        )
        assert resp.status_code == 200
        s = stats()
        assert s["total_corrections"] == 1
