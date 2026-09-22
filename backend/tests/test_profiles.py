import csv
import io

import pytest

pytest.importorskip("faster_whisper", reason="whisper no instalado en este entorno")

import backend.db as db  # noqa: E402
from backend.db import DB_PATH, export_anki_csv, reset_for_tests, save_corrections, start_session, stats  # noqa: E402


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    reset_for_tests(tmp_path / "test-profiles.db")
    yield
    reset_for_tests(DB_PATH)


@pytest.fixture()
def ollama_ok(monkeypatch):
    async def fake_immersive_start(language, topic=None):
        return {"topic": topic or "travel", "reply": "Hello!", "corrections": []}

    async def fake_immersive_continue(language, history, user_text):
        return {"topic": "travel", "reply": "Hello!", "corrections": []}

    monkeypatch.setattr("backend.main.immersive_start", fake_immersive_start)
    monkeypatch.setattr("backend.main.immersive_continue", fake_immersive_continue)


class TestProfilesDb:
    def test_create_and_list(self, temp_db):
        pid = db.create_profile("  Ana  ")
        assert pid >= 1
        profiles = db.list_profiles()
        assert len(profiles) == 1
        assert profiles[0]["name"] == "Ana"
        assert profiles[0]["sessions"] == 0

    def test_empty_name_raises(self, temp_db):
        with pytest.raises(ValueError):
            db.create_profile("   ")

    def test_long_name_raises(self, temp_db):
        with pytest.raises(ValueError):
            db.create_profile("x" * 41)

    def test_legacy_sessions_have_null_profile(self, temp_db):
        sid = start_session("en", "travel", "voice")
        s = stats()
        assert s["total_sessions"] == 1
        assert s["total_corrections"] == 0
        assert s["by_language"] == {"en": 1}
        row = db._get_conn().execute("SELECT profile_id FROM sessions WHERE id = ?", (sid,)).fetchone()
        assert row["profile_id"] is None


class TestStatsByProfile:
    def test_stats_filtered_by_profile(self, temp_db):
        a = db.create_profile("Ana")
        b = db.create_profile("Luis")
        sid_a = start_session("en", "travel", "voice", profile_id=a)
        save_corrections(sid_a, "en", "travel", "i go", [
            {"error": "i go", "correction": "I went", "explanation": "pasado"}
        ])
        start_session("pt", "music", "text", profile_id=b)

        total = stats()
        assert total["total_sessions"] == 2
        assert total["total_corrections"] == 1

        only_a = stats(a)
        assert only_a["total_sessions"] == 1
        assert only_a["by_language"] == {"en": 1}
        assert only_a["top_topics_with_errors"] == {"travel": 1}

        only_b = stats(b)
        assert only_b["total_sessions"] == 1
        assert only_b["total_corrections"] == 0

    def test_anki_export_filtered_by_profile(self, temp_db):
        a = db.create_profile("Ana")
        sid_a = start_session("en", "travel", "voice", profile_id=a)
        save_corrections(sid_a, "en", "travel", "i go", [
            {"error": "i go", "correction": "I went", "explanation": "pasado"}
        ])
        start_session("pt", "music", "text")  # sin perfil: no debe contar para Ana

        rows_a = list(csv.reader(io.StringIO(export_anki_csv(a))))
        assert len(rows_a) == 2  # cabecera + 1
        assert rows_a[1][0] == "i go"

        rows_all = list(csv.reader(io.StringIO(export_anki_csv())))
        assert len(rows_all) == 2


class TestProfilesApi:
    def test_list_empty(self, client, temp_db):
        resp = client.get("/api/profiles")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_create_and_get(self, client, temp_db):
        resp = client.post("/api/profiles", json={"name": "Marta"})
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body["id"], int)
        assert body["name"] == "Marta"
        assert client.get("/api/profiles").json()[0]["name"] == "Marta"

    def test_create_empty_name_400(self, client, temp_db):
        resp = client.post("/api/profiles", json={"name": "   "})
        assert resp.status_code == 400

    def test_immersive_start_attaches_profile(self, client, ollama_ok, temp_db):
        pid = client.post("/api/profiles", json={"name": "Pepe"}).json()["id"]
        resp = client.post("/api/immersive", json={"mode": "start", "topic": "travel", "profile_id": pid})
        assert resp.status_code == 200
        assert stats(pid)["total_sessions"] == 1

    def test_stats_endpoint_by_profile(self, client, ollama_ok, temp_db):
        pid = client.post("/api/profiles", json={"name": "Luz"}).json()["id"]
        client.post("/api/immersive", json={"mode": "start", "topic": "music", "profile_id": pid})
        body = client.get("/api/stats", params={"profile_id": pid}).json()
        assert body["total_sessions"] == 1
