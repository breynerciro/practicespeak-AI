import os

import pytest

pytest.importorskip("faster_whisper", reason="whisper no instalado en este entorno")



@pytest.fixture()
def ollama_ok(monkeypatch):
    """Parchea las funciones de ai.py para devolver un JSON válido sin salir a Ollama."""
    async def fake_tutor_chat(language, history, message):
        return {"reply": "Hello!", "corrections": []}

    async def fake_immersive_start(language, topic=None):
        return {"topic": topic or "travel", "reply": "Hello!", "corrections": []}

    async def fake_immersive_continue(language, history, user_text):
        return {"topic": "travel", "reply": "Hello!", "corrections": []}

    async def fake_correct_grammar(language, text):
        return {"corrected": text, "errors": [], "summary": ""}

    monkeypatch.setattr("backend.main.tutor_chat", fake_tutor_chat)
    monkeypatch.setattr("backend.main.immersive_start", fake_immersive_start)
    monkeypatch.setattr("backend.main.immersive_continue", fake_immersive_continue)
    monkeypatch.setattr("backend.main.correct_grammar", fake_correct_grammar)


@pytest.fixture()
def model_garbage(monkeypatch):
    """Simula un modelo que responde 200 pero con texto no-JSON -> ValueError -> 502."""
    async def garbage(*args):
        raise ValueError("Could not parse JSON from model: lorem ipsum")

    monkeypatch.setattr("backend.main.tutor_chat", garbage)
    monkeypatch.setattr("backend.main.immersive_start", garbage)
    monkeypatch.setattr("backend.main.immersive_continue", garbage)
    monkeypatch.setattr("backend.main.correct_grammar", garbage)


@pytest.fixture()
def ollama_down(monkeypatch):
    """Parchea las funciones de ai.py para simular Ollama caído (NovaError)."""
    from backend.ai import NovaError

    async def fail(*args):
        raise NovaError("No se pudo contactar con Ollama: refused")

    monkeypatch.setattr("backend.main.tutor_chat", fail)
    monkeypatch.setattr("backend.main.immersive_start", fail)
    monkeypatch.setattr("backend.main.immersive_continue", fail)
    monkeypatch.setattr("backend.main.correct_grammar", fail)


class TestHealth:
    def test_ok_false_when_ollama_down(self, client, monkeypatch):
        async def down():
            return False

        monkeypatch.setattr("backend.main.check_ollama", down)
        resp = client.get("/api/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is False
        assert body["ollama"] is False

    def test_ok_true_when_ollama_up(self, client, monkeypatch):
        async def up():
            return True

        monkeypatch.setattr("backend.main.check_ollama", up)
        body = client.get("/api/health").json()
        assert body["ok"] is True
        assert body["model"] == "qwen3:4b"


class TestChat:
    def test_ok(self, client, ollama_ok):
        resp = client.post("/api/chat", json={"language": "en", "message": "hi"})
        assert resp.status_code == 200
        assert resp.json() == {"reply": "Hello!", "corrections": []}

    def test_ollama_down_returns_503(self, client, ollama_down):
        resp = client.post("/api/chat", json={"message": "hi"})
        assert resp.status_code == 503
        assert "Modelo local no disponible" in resp.json()["detail"]

    def test_invalid_language_returns_400_with_detail(self, client, ollama_ok):
        resp = client.post("/api/chat", json={"language": "xx", "message": "hi"})
        assert resp.status_code == 400
        assert "en" in resp.json()["detail"] and "pt" in resp.json()["detail"]

    def test_empty_message_returns_400(self, client, ollama_ok):
        resp = client.post("/api/chat", json={"message": "   "})
        assert resp.status_code == 400

    def test_null_message_returns_400(self, client, ollama_ok):
        resp = client.post("/api/chat", json={"message": None})
        assert resp.status_code == 400

    def test_history_with_bad_role_returns_400(self, client, ollama_ok):
        resp = client.post("/api/chat", json={"message": "hi", "history": [{"role": "bot", "content": "x"}]})
        assert resp.status_code == 400
        assert "history.0.role" in resp.json()["detail"]


    def test_model_garbage_returns_502(self, client, model_garbage):
        resp = client.post("/api/chat", json={"message": "hi"})
        assert resp.status_code == 502
        assert "respuesta inválida" in resp.json()["detail"]


class TestImmersive:
    def test_start_ok(self, client, ollama_ok):
        resp = client.post("/api/immersive", json={"mode": "start", "topic": "travel"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["reply"] == "Hello!"
        assert body["topic"] == "travel"

    def test_continue_without_message_returns_400(self, client, ollama_ok):
        resp = client.post("/api/immersive", json={"mode": "continue"})
        assert resp.status_code == 400
        assert "Empty message" in resp.json()["detail"]

    def test_continue_ok(self, client, ollama_ok):
        resp = client.post(
            "/api/immersive",
            json={"mode": "continue", "message": "I like pizza", "history": [{"role": "assistant", "content": "Hi!"}]},
        )
        assert resp.status_code == 200
        assert resp.json()["reply"] == "Hello!"

    def test_ollama_down_returns_503(self, client, ollama_down):
        resp = client.post("/api/immersive", json={"mode": "start"})
        assert resp.status_code == 503


    def test_model_garbage_returns_502(self, client, model_garbage):
        resp = client.post("/api/immersive", json={"mode": "start"})
        assert resp.status_code == 502
        assert "respuesta inválida" in resp.json()["detail"]


class TestGrammar:
    def test_ok(self, client, ollama_ok):
        resp = client.post("/api/grammar", json={"text": "i has a cat"})
        assert resp.status_code == 200
        assert resp.json() == {"corrected": "i has a cat", "errors": [], "summary": ""}

    def test_empty_text_returns_400(self, client, ollama_ok):
        resp = client.post("/api/grammar", json={"text": ""})
        assert resp.status_code == 400

    def test_ollama_down_returns_503(self, client, ollama_down):
        resp = client.post("/api/grammar", json={"text": "hello"})
        assert resp.status_code == 503


    def test_model_garbage_returns_502(self, client, model_garbage):
        resp = client.post("/api/grammar", json={"text": "hello"})
        assert resp.status_code == 502
        assert "respuesta inválida" in resp.json()["detail"]


class TestLogsAndClientLog:
    def test_client_log_ok(self, client):
        resp = client.post("/api/log", json={"msg": "TEST_MESSAGE"})
        assert resp.status_code == 200
        assert resp.json() == {"ok": True}

    def test_logs_endpoint_returns_log_lines(self, client):
        client.post("/api/log", json={"msg": "LOG_MARKER_XYZ"})
        resp = client.get("/api/logs?limit=50")
        assert resp.status_code == 200
        assert any("LOG_MARKER_XYZ" in line for line in resp.json()["logs"])


@pytest.fixture()
def fake_transcribe(monkeypatch):
    """Reemplaza transcribe (sync, como el real: main la pasa por threadpool)."""
    def fake(audio_bytes, language):
        assert audio_bytes == b"AUDIOBYTES"
        return "hello world"

    monkeypatch.setattr("backend.main.transcribe", fake)


@pytest.fixture()
def fake_sintetizar(monkeypatch):
    """Reemplaza sintetizar para no salir a edge_tts."""
    async def fake(text, language, gender="female", voice="", speed=1.0):
        return b"FAKEMP3"

    monkeypatch.setattr("backend.main.sintetizar", fake)


class TestAudio:
    def test_returns_evaluation(self, client, fake_transcribe):
        resp = client.post(
            "/api/audio",
            files={"audio": ("a.webm", b"AUDIOBYTES", "audio/webm")},
            data={"expected": "hello world", "language": "en"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["score"] == 100
        assert body["transcript"] == "hello world"
        assert body["missing"] == []

    def test_transcribe_error_returns_500(self, client, monkeypatch):
        def boom(audio_bytes, language):
            raise RuntimeError("whisper exploded")

        monkeypatch.setattr("backend.main.transcribe", boom)
        resp = client.post(
            "/api/audio",
            files={"audio": ("a.webm", b"AUDIOBYTES", "audio/webm")},
            data={"expected": "hello", "language": "en"},
        )
        assert resp.status_code == 500
        assert "transcribiendo" in resp.json()["detail"]


class TestTTS:
    def test_returns_audio_mpeg(self, client, fake_sintetizar):
        resp = client.get("/api/tts", params={"text": "hello", "lang": "en"})
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("audio/mpeg")
        assert resp.content == b"FAKEMP3"

    def test_gender_parameter_passed_through(self, client, monkeypatch):
        seen = {}

        async def fake(text, language, gender="female", voice="", speed=1.0):
            seen.update(text=text, language=language, gender=gender, voice=voice)
            return b"FAKEMP3"

        monkeypatch.setattr("backend.main.sintetizar", fake)
        resp = client.get("/api/tts", params={"text": "hola", "lang": "de", "gender": "male"})
        assert resp.status_code == 200
        assert seen == {"text": "hola", "language": "de", "gender": "male", "voice": ""}

    def test_voice_parameter_passed_through(self, client, monkeypatch):
        seen = {}

        async def fake(text, language, gender="female", voice="", speed=1.0):
            seen.update(voice=voice)
            return b"FAKEMP3"

        monkeypatch.setattr("backend.main.sintetizar", fake)
        resp = client.get("/api/tts", params={"text": "hola", "lang": "es", "voice": "es_ES-davefx-medium"})
        assert resp.status_code == 200
        assert seen["voice"] == "es_ES-davefx-medium"

    def test_speed_parameter_passed_through(self, client, monkeypatch):
        seen = {}

        async def fake(text, language, gender="female", voice="", speed=1.0):
            seen.update(speed=speed)
            return b"FAKEMP3"

        monkeypatch.setattr("backend.main.sintetizar", fake)
        resp = client.get("/api/tts", params={"text": "hola", "lang": "en", "speed": "1.25"})
        assert resp.status_code == 200
        assert seen["speed"] == 1.25

    def test_speed_defaults_to_normal(self, client, monkeypatch):
        seen = {}

        async def fake(text, language, gender="female", voice="", speed=1.0):
            seen.update(speed=speed)
            return b"FAKEMP3"

        monkeypatch.setattr("backend.main.sintetizar", fake)
        resp = client.get("/api/tts", params={"text": "hola", "lang": "en"})
        assert resp.status_code == 200
        assert seen["speed"] == 1.0

    def test_gender_defaults_to_female(self, client, monkeypatch):
        seen = {}

        async def fake(text, language, gender="female", voice="", speed=1.0):
            seen.update(gender=gender)
            return b"FAKEMP3"

        monkeypatch.setattr("backend.main.sintetizar", fake)
        resp = client.get("/api/tts", params={"text": "hola", "lang": "en"})
        assert resp.status_code == 200
        assert seen["gender"] == "female"

    def test_sintetizar_error_returns_502(self, client, monkeypatch):
        async def fail(text, language, gender="female", voice="", speed=1.0):
            raise RuntimeError("no internet")

        monkeypatch.setattr("backend.main.sintetizar", fail)
        resp = client.get("/api/tts", params={"text": "hello", "lang": "en"})
        assert resp.status_code == 502
        assert "TTS failed" in resp.json()["detail"]


class TestTtsVoices:
    def test_language_returns_local_and_edge_voices(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.tts.config.PIPER_HOME", str(tmp_path))
        resp = client.get("/api/tts/voices", params={"lang": "es"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["lang"] == "es"
        sources = {v["source"] for v in body["voices"]}
        assert sources == {"local", "edge"}
        local_ids = [v["id"] for v in body["voices"] if v["source"] == "local"]
        edge_ids = [v["id"] for v in body["voices"] if v["source"] == "edge"]
        assert "es_ES-sharvard-medium" in local_ids
        assert "es_ES-davefx-medium" in local_ids
        assert "es-ES-ElviraNeural" in edge_ids
        assert all(v["installed"] is False for v in body["voices"] if v["source"] == "local")
        assert all(v["name"] for v in body["voices"])

    def test_marks_piper_voice_installed_when_model_on_disk(self, client, tmp_path, monkeypatch):
        from backend.tts import _piper_model_paths

        monkeypatch.setattr("backend.tts.config.PIPER_HOME", str(tmp_path))
        onnx, _json = _piper_model_paths("es_ES-davefx-medium")
        os.makedirs(os.path.dirname(onnx), exist_ok=True)
        open(onnx, "wb").close()
        resp = client.get("/api/tts/voices", params={"lang": "es"})
        local = {v["id"]: v["installed"] for v in resp.json()["voices"] if v["source"] == "local"}
        assert local["es_ES-davefx-medium"] is True
        assert local["es_ES-sharvard-medium"] is False

    def test_all_languages_grouped(self, client, tmp_path, monkeypatch):
        from backend import config

        monkeypatch.setattr(config, "PIPER_HOME", str(tmp_path))
        resp = client.get("/api/tts/voices")
        assert set(resp.json()["voices"].keys()) == set(config.SUPPORTED_LANGUAGES)


class TestIndex:
    def test_index_served(self, client):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "Nova" in resp.text


class TestServiceWorker:
    def test_serves_sw_with_root_scope(self, client, tmp_path, monkeypatch):
        sw = tmp_path / "sw.js"
        sw.write_text("self.addEventListener('fetch', () => {})", encoding="utf-8")
        monkeypatch.setattr("backend.main.FRONTEND_DIR", str(tmp_path))
        resp = client.get("/sw.js")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/javascript")
        assert resp.headers["service-worker-allowed"] == "/"
        assert "addEventListener" in resp.text

    def test_missing_sw_returns_404(self, client, tmp_path, monkeypatch):
        monkeypatch.setattr("backend.main.FRONTEND_DIR", str(tmp_path))
        resp = client.get("/sw.js")
        assert resp.status_code == 404
