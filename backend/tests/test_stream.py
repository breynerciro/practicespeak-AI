import asyncio

import httpx
import pytest

import backend.ai as ai
from backend.ai import (
    NovaError,
    _json_field_progressive,
    ask_ollama_stream,
    immersive_chat_stream,
)


def run(coro):
    return asyncio.run(coro)


def drain(agen):
    async def _drain():
        out = []
        async for ev in agen:
            out.append(ev)
        return out

    return asyncio.run(_drain())


class TestJsonFieldProgressive:
    def test_field_not_present_yet(self):
        assert _json_field_progressive('{"topic": "x"}', "reply") == (None, False)
        assert _json_field_progressive('{"topic"', "topic") == (None, False)

    def test_partial_value_is_not_complete(self):
        assert _json_field_progressive('{"reply": "Hola', "reply") == ("Hola", False)
        assert _json_field_progressive('{"reply": "Hola mu', "reply") == ("Hola mu", False)

    def test_quoted_close_marks_complete(self):
        assert _json_field_progressive('{"reply": "Hola"', "reply") == ("Hola", True)
        assert _json_field_progressive('{"reply": ""}', "reply") == ("", True)

    def test_escapes_are_decoded(self):
        assert _json_field_progressive(r'{"reply": "a\n\tb"}', "reply") == ("a\n\tb", True)
        assert _json_field_progressive(r'{"reply": "caf\u00e9"}', "reply") == ("café", True)
        assert _json_field_progressive(r'{"reply": "a \x"}', "reply") == ("a x", True)

    def test_invalid_unicode_escape_is_kept_as_u(self):
        assert _json_field_progressive(r'{"reply": "caf\uZZZZ"}', "reply") == ("cafu", True)

    def test_truncated_unicode_escape_stays_partial(self):
        assert _json_field_progressive(r'{"reply": "caf\u00e', "reply") == ("caf", False)

    def test_truncated_backslash_stays_partial(self):
        assert _json_field_progressive('{"reply": "a\\', "reply") == ("a", False)

    def test_ignores_value_that_contains_quote_key(self):
        # El valor de otro campo tampoco tiene `"reply": "`.
        assert _json_field_progressive('{"topic": "reply: hola", "x": "y"}', "topic") == ("reply: hola", True)


class FakeResp:
    def __init__(self, lines):
        self._lines = lines

    def raise_for_status(self):
        return None

    async def aiter_lines(self):
        for line in self._lines:
            yield line


class FakeStreamCtx:
    def __init__(self, lines):
        self._lines = lines

    async def __aenter__(self):
        return FakeResp(self._lines)

    async def __aexit__(self, *args):
        return False


class FakeOllamaClient:
    """Reemplazo de httpx.AsyncClient que emula el NDJSON de /api/chat."""

    last_payload = None
    lines: list[str] = []
    error: Exception | None = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def stream(self, method, url, json=None):
        type(self).last_payload = json
        if type(self).error:
            raise type(self).error
        return FakeStreamCtx(list(type(self).lines))


class TestAskOllamaStream:
    def _patch(self, monkeypatch, lines=None, error=None):
        FakeOllamaClient.lines = lines or []
        FakeOllamaClient.error = error
        FakeOllamaClient.last_payload = None
        monkeypatch.setattr(ai.httpx, "AsyncClient", FakeOllamaClient)

    def test_yields_content_deltas_until_done(self, monkeypatch):
        self._patch(
            monkeypatch,
            [
                "not json at all",
                '{"message": {"role": "assistant", "content": "Hel"}, "done": false}',
                '{"message": {"content": "lo"}, "done": false}',
                '{"done": true}',
            ],
        )
        chunks = []
        for delta in drain(ask_ollama_stream([{"role": "user", "content": "hola"}])):
            chunks.append(delta)
        assert chunks == ["Hel", "lo"]
        assert FakeOllamaClient.last_payload["stream"] is True
        assert FakeOllamaClient.last_payload["format"] == "json"

    def test_connection_error_wrapped_as_nova_error(self, monkeypatch):
        self._patch(monkeypatch, error=httpx.ConnectError("refused"))
        with pytest.raises(NovaError, match="No se pudo contactar"):
            drain(ask_ollama_stream([{"role": "user", "content": "hi"}]))

    def test_model_error_chunk_raises_nova_error(self, monkeypatch):
        self._patch(monkeypatch, lines=['{"error": "model not found"}'])
        with pytest.raises(NovaError, match="model not found"):
            drain(ask_ollama_stream([{"role": "user", "content": "hi"}]))

    def test_final_delta_yielded_before_done(self, monkeypatch):
        self._patch(
            monkeypatch,
            [
                '{"message": {"content": "adiós"}, "done": true}',
            ],
        )
        chunks = list(drain(ask_ollama_stream([{"role": "user", "content": "hi"}])))
        assert chunks == ["adiós"]


class TestImmersiveChatStream:
    def test_start_yields_topic_then_deltas_then_done(self, monkeypatch):
        async def fake_stream(messages):
            yield '{"topic": "tra'
            yield 'vel", "reply": "Ho'
            yield "la, que tal"
            yield '"'
            yield ', "corrections": []}'

        monkeypatch.setattr(ai, "ask_ollama_stream", fake_stream)
        events = drain(immersive_chat_stream("start", "en", [], "", "travel"))

        assert events[0] == {"type": "topic", "topic": "travel"}
        assert events[-1] == {"type": "done", "reply": "Hola, que tal", "corrections": []}
        deltas = events[1:-1]
        assert all(e["type"] == "delta" for e in deltas)
        assert deltas[-1]["text"] == "Hola, que tal"
        # los deltas son prefijos crecientes hasta completar la respuesta
        for prev, cur in zip(deltas, deltas[1:], strict=False):
            assert cur["text"].startswith(prev["text"])

    def test_start_prompt_uses_decided_topic(self, monkeypatch):
        captured = {}

        async def fake_stream(messages):
            captured["messages"] = messages
            yield '{"reply": "hi"}'

        monkeypatch.setattr(ai, "ask_ollama_stream", fake_stream)
        events = drain(immersive_chat_stream("start", "pt", [], "", "food"))
        topics = [e for e in events if e["type"] == "topic"]
        assert topics[0]["topic"] == "food"
        assert "food" in captured["messages"][-1]["content"]
        assert "Portuguese (Brazilian)" in captured["messages"][0]["content"]

    def test_continue_parses_topic_and_emits_corrections(self, monkeypatch):
        async def fake_stream(messages):
            assert "voice transcription" in messages[-1]["content"]
            yield '{"topic": "food", "rep'
            yield 'ly": "Try pasta", "corrections": [{"error": "i go", "correction": "I go"}]}'

        monkeypatch.setattr(ai, "ask_ollama_stream", fake_stream)
        events = drain(immersive_chat_stream("continue", "en", [], "i go home"))

        assert events[0] == {"type": "topic", "topic": "food"}
        deltas = [e for e in events if e["type"] == "delta"]
        assert "".join(e["text"] for e in deltas) == "Try pasta"
        corrections_ev = [e for e in events if e["type"] == "corrections"]
        assert corrections_ev == [
            {"type": "corrections", "corrections": [{"error": "i go", "correction": "I go"}]}
        ]
        assert events[-1] == {
            "type": "done",
            "reply": "Try pasta",
            "corrections": [{"error": "i go", "correction": "I go"}],
        }

    def test_continue_topic_missing_emits_at_end(self, monkeypatch):
        async def fake_stream(messages):
            yield '{"reply": "ok", "corrections": []}'

        monkeypatch.setattr(ai, "ask_ollama_stream", fake_stream)
        events = drain(immersive_chat_stream("continue", "en", [], "hola"))
        topics = [e for e in events if e["type"] == "topic"]
        assert topics == []
        assert events[-1] == {"type": "done", "reply": "ok", "corrections": []}

    def test_continue_topic_from_final_parse(self, monkeypatch):
        # El tema llega completo solo al final (después de las correcciones).
        async def fake_stream(messages):
            yield '{"corrections": []'
            yield ', "topic": "pets", "reply": "ok"}'

        monkeypatch.setattr(ai, "ask_ollama_stream", fake_stream)
        events = drain(immersive_chat_stream("continue", "en", [], "hola"))
        topics = [e for e in events if e["type"] == "topic"]
        assert topics == [{"type": "topic", "topic": "pets"}]
        assert events[-1]["reply"] == "ok"

    def test_no_corrections_when_empty(self, monkeypatch):
        async def fake_stream(messages):
            yield '{"topic": "t", "reply": "hi", "corrections": []}'

        monkeypatch.setattr(ai, "ask_ollama_stream", fake_stream)
        events = drain(immersive_chat_stream("continue", "en", [], "hola"))
        assert all(e["type"] != "corrections" for e in events)

    def test_nova_error_propagates(self, monkeypatch):
        async def fail(messages):
            raise NovaError("down")
            yield

        monkeypatch.setattr(ai, "ask_ollama_stream", fail)
        with pytest.raises(NovaError):
            drain(immersive_chat_stream("start", "en", [], "", "travel"))

    def test_garbage_output_raises_valueerror(self, monkeypatch):
        async def garbage(messages):
            yield "no es json"

        monkeypatch.setattr(ai, "ask_ollama_stream", garbage)
        with pytest.raises(ValueError, match="Could not parse JSON"):
            drain(immersive_chat_stream("continue", "en", [], "x"))

    def test_history_truncated_to_last_12(self, monkeypatch):
        captured = {}

        async def fake_stream(messages):
            captured["messages"] = messages
            yield '{"topic": "t", "reply": "ok", "corrections": []}'

        monkeypatch.setattr(ai, "ask_ollama_stream", fake_stream)
        history = [{"role": "user", "content": f"m{i}"} for i in range(20)]
        drain(immersive_chat_stream("continue", "en", history, "hola"))
        assert len(captured["messages"]) == 14  # 1 system + 12 history + 1 user


class TestStreamEndpoint:
    def test_start_sends_session_id_topic_deltas_done(self, client, monkeypatch):
        async def fake_stream(mode, language, history, user_text, topic=None):
            assert mode == "start"
            assert topic == "travel"
            yield {"type": "delta", "text": "Ho"}
            yield {"type": "delta", "text": "Hola"}
            yield {"type": "done", "reply": "Hola", "corrections": []}

        monkeypatch.setattr("backend.ai.resolve_start_topic", lambda t: t or "travel")
        monkeypatch.setattr("backend.db.start_session", lambda *a, **k: 42)
        monkeypatch.setattr("backend.main.immersive_chat_stream", fake_stream)
        resp = client.post(
            "/api/immersive/stream",
            json={"mode": "start", "language": "en", "topic": "travel"},
        )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        assert '"type": "session_id"' in resp.text
        assert '"session_id": 42' in resp.text
        assert '"type": "delta"' in resp.text
        assert '"type": "done"' in resp.text
        assert '"text": "Hola"' in resp.text
        assert not resp.text.strip().startswith("event:")

    def test_continue_saves_corrections_after_done(self, client, monkeypatch):
        saved = []

        async def fake_stream(mode, language, history, user_text, topic=None):
            yield {"type": "topic", "topic": "food"}
            yield {"type": "done", "reply": "Try pasta", "corrections": [{"error": "i go", "correction": "I go"}]}

        def fake_save(session_id, language, topic_, text, corrections):
            saved.append((session_id, language, topic_, text, corrections))
            return 1

        monkeypatch.setattr("backend.main.immersive_chat_stream", fake_stream)
        monkeypatch.setattr("backend.db.save_corrections", fake_save)
        resp = client.post(
            "/api/immersive/stream",
            json={
                "mode": "continue",
                "language": "en",
                "message": "i go home",
                "session_id": 7,
                "history": [],
            },
        )
        assert resp.status_code == 200
        assert '"type": "topic"' in resp.text
        assert '"type": "done"' in resp.text
        assert saved == [(7, "en", "food", "i go home", [{"error": "i go", "correction": "I go"}])]

    def test_error_produces_error_event_and_no_save(self, client, monkeypatch):
        calls = []

        async def fail(mode, language, history, user_text, topic=None):
            raise NovaError("down")
            yield

        def fake_save(*args, **kwargs):
            calls.append(args)
            return 1

        monkeypatch.setattr("backend.main.immersive_chat_stream", fail)
        monkeypatch.setattr("backend.db.save_corrections", fake_save)
        resp = client.post(
            "/api/immersive/stream",
            json={"mode": "continue", "language": "en", "message": "hi", "session_id": 1, "history": []},
        )
        assert resp.status_code == 200
        assert '"type": "error"' in resp.text
        assert "Modelo local no disponible" in resp.text
        assert calls == []

    def test_garbage_output_becomes_invalid_error_event(self, client, monkeypatch):
        async def garbage(mode, language, history, user_text, topic=None):
            raise ValueError("Could not parse JSON from model")
            yield

        monkeypatch.setattr("backend.main.immersive_chat_stream", garbage)
        resp = client.post(
            "/api/immersive/stream",
            json={"mode": "continue", "language": "en", "message": "hi", "session_id": 1, "history": []},
        )
        assert resp.status_code == 200
        assert '"type": "error"' in resp.text
        assert "Could not parse JSON" in resp.text

    def test_invalid_payload_still_validates(self, client, monkeypatch):
        called = []

        async def fake(mode, language, history, user_text, topic=None):
            called.append(1)

        monkeypatch.setattr("backend.main.immersive_chat_stream", fake)
        resp = client.post(
            "/api/immersive/stream",
            json={"mode": "continue", "language": "en", "message": "   ", "session_id": 1},
        )
        assert resp.status_code == 400
        assert called == []
