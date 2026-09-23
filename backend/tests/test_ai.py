import asyncio
import json

import httpx
import pytest

import backend.ai as ai
from backend.ai import (
    NovaError,
    _clean_json,
    ask_ollama,
    check_ollama,
    correct_grammar,
    immersive_continue,
    immersive_start,
    tutor_chat,
)


class TestCleanJson:
    def test_plain_json(self):
        assert _clean_json('{"reply": "hi"}') == {"reply": "hi"}

    def test_fenced_code_block(self):
        assert _clean_json('```json\n{"reply": "hi"}\n```') == {"reply": "hi"}

    def test_json_embedded_in_prose(self):
        raw = 'Sure! Here you go:\n{"reply": "hi"}\nHope that helps!'
        assert _clean_json(raw) == {"reply": "hi"}

    def test_multiline_json(self):
        raw = '{"reply": "hi",\n  "corrections": []}'
        assert _clean_json(raw) == {"reply": "hi", "corrections": []}

    def test_garbage_raises_valueerror(self):
        with pytest.raises(ValueError, match="Could not parse JSON"):
            _clean_json("no json here at all")


class FakeAsyncClient:
    """Reemplazo mínimo de httpx.AsyncClient para no salir a la red."""

    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json):
        if self._error:
            raise self._error
        return self._response

    async def get(self, url):
        if self._error:
            raise self._error
        return self._response


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def run(coro):
    return asyncio.run(coro)


class TestAskOllama:
    def test_connection_error_wrapped_as_nova_error(self, monkeypatch):
        client = FakeAsyncClient(error=httpx.ConnectError("refused"))
        monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: client)
        with pytest.raises(NovaError, match="No se pudo contactar"):
            run(ask_ollama([{"role": "user", "content": "hi"}]))

    def test_unexpected_shape_wrapped_as_nova_error(self, monkeypatch):
        client = FakeAsyncClient(response=FakeResponse({"unexpected": "shape"}))
        monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: client)
        with pytest.raises(NovaError, match="Respuesta inesperada"):
            run(ask_ollama([{"role": "user", "content": "hi"}]))

    def test_ok_returns_content(self, monkeypatch):
        payload = {"message": {"content": '{"reply": "hi"}'}}
        client = FakeAsyncClient(response=FakeResponse(payload))
        monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: client)
        assert run(ask_ollama([{"role": "user", "content": "hi"}])) == '{"reply": "hi"}'


class TestTutorChat:
    def test_reply_and_corrections_returned(self, monkeypatch):
        async def fake_ask(messages):
            return json.dumps({"reply": "Hello!", "corrections": []})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        result = run(tutor_chat("en", [], "hi"))
        assert result == {"reply": "Hello!", "corrections": []}

    def test_system_and_user_roles_only(self, monkeypatch):
        captured = {}

        async def fake_ask(messages):
            captured["roles"] = [m["role"] for m in messages]
            return json.dumps({"reply": "ok"})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        run(tutor_chat("en", [{"role": "user", "content": "a"}, {"role": "system", "content": "b"}], "hi"))
        assert set(captured["roles"]) == {"system", "user"}

    def test_garbage_model_output_raises_valueerror(self, monkeypatch):
        """El camino del 502: el modelo responde HTTP 200 pero con texto no-JSON."""
        async def fake_ask(messages):
            return "lorem ipsum sin json"

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        with pytest.raises(ValueError, match="Could not parse JSON"):
            run(tutor_chat("en", [], "hi"))


class TestPickTopic:
    def setup_method(self):
        ai.RECENT_TOPICS.clear()

    def test_catalog_has_20_unique_topics(self):
        assert len(ai.TOPICS) == 20
        assert len(set(ai.TOPICS)) == 20

    def test_returns_valid_topic(self):
        assert ai.pick_topic() in ai.TOPICS

    def test_no_repetition_within_buffer_window(self):
        first_six = [ai.pick_topic() for _ in range(6)]
        assert len(set(first_six)) == 6  # 20 temas, buffer 6 → sin repetir

    def test_recent_buffer_capped(self):
        for _ in range(15):
            ai.pick_topic()
        assert len(ai.RECENT_TOPICS) == ai.RECENT_TOPICS_MAX


class TestImmersiveStart:
    def test_returns_topic_reply_and_corrections(self, monkeypatch):
        async def fake_ask(messages):
            return json.dumps({"topic": "food", "reply": "Hi! I'm Nova.", "corrections": []})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        result = run(immersive_start("en", "food"))
        assert result == {"topic": "food", "reply": "Hi! I'm Nova.", "corrections": []}

    def test_topic_prompt_includes_requested_topic(self, monkeypatch):
        captured = {}

        async def fake_ask(messages):
            captured["messages"] = messages
            return json.dumps({"topic": "travel", "reply": "hi"})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        run(immersive_start("en", "travel"))
        user_msg = captured["messages"][-1]["content"]
        assert "travel" in user_msg
        assert "BEGIN" in user_msg

    def test_no_topic_prompt_uses_backend_chosen_topic(self, monkeypatch):
        captured = {}

        async def fake_ask(messages):
            captured["messages"] = messages
            return json.dumps({"topic": "music", "reply": "hi"})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        monkeypatch.setattr(ai, "pick_topic", lambda: "music")
        result = run(immersive_start("en", None))
        user_msg = captured["messages"][-1]["content"]
        assert "The topic for this session is 'music'" in user_msg
        assert result["topic"] == "music"

    def test_system_prompt_uses_language_name(self, monkeypatch):
        captured = {}

        async def fake_ask(messages):
            captured["messages"] = messages
            return json.dumps({"topic": "x", "reply": "hi"})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        run(immersive_start("pt", None))
        system_msg = captured["messages"][0]["content"]
        assert "Portuguese (Brazilian)" in system_msg
        assert "__LANG__" not in system_msg

    def test_missing_fields_fall_back_to_defaults(self, monkeypatch):
        async def fake_ask(messages):
            return json.dumps({})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        result = run(immersive_start("en", "hobbies"))
        assert result["topic"] == "hobbies"
        assert result["reply"] == ""
        assert result["corrections"] == []

    def test_nova_error_propagates(self, monkeypatch):
        async def fail_ask(messages):
            raise NovaError("down")

        monkeypatch.setattr(ai, "ask_ollama", fail_ask)
        with pytest.raises(NovaError):
            run(immersive_start("en", None))


class TestImmersiveContinue:
    def test_history_truncated_to_last_12_turns(self, monkeypatch):
        captured = {}

        async def fake_ask(messages):
            captured["messages"] = messages
            return json.dumps({"topic": "t", "reply": "ok"})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        history = [{"role": "user", "content": f"msg {i}"} for i in range(20)]
        run(immersive_continue("en", history, "hello"))
        # 1 system + 12 history + 1 user
        assert len(captured["messages"]) == 14
        assert captured["messages"][1]["content"] == "msg 8"
        assert captured["messages"][-1]["content"].endswith("hello")

    def test_invalid_roles_filtered_from_history(self, monkeypatch):
        captured = {}

        async def fake_ask(messages):
            captured["messages"] = messages
            return json.dumps({"topic": "t", "reply": "ok"})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        history = [
            {"role": "user", "content": "a"},
            {"role": "system", "content": "evil"},
            {"role": "assistant", "content": "b"},
        ]
        run(immersive_continue("en", history, "hello"))
        roles = [m["role"] for m in captured["messages"]]
        assert "evil" not in [m["content"] for m in captured["messages"]]
        assert roles == ["system", "user", "assistant", "user"]

    def test_user_transcription_wrapped_with_prefix(self, monkeypatch):
        captured = {}

        async def fake_ask(messages):
            captured["messages"] = messages
            return json.dumps({"topic": "t", "reply": "ok"})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        run(immersive_continue("en", [], "I like pizza"))
        last = captured["messages"][-1]
        assert last["role"] == "user"
        assert "voice transcription" in last["content"]
        assert "I like pizza" in last["content"]

    def test_missing_fields_fall_back_to_defaults(self, monkeypatch):
        async def fake_ask(messages):
            return json.dumps({})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        result = run(immersive_continue("en", [], "hi"))
        assert result == {"topic": "", "reply": "", "corrections": []}


class TestPreviousQuestions:
    def test_extracts_questions_from_assistant_turns(self):
        history = [
            {"role": "assistant", "content": "Hi! What do you like to eat?"},
            {"role": "user", "content": "pizza"},
            {"role": "assistant", "content": "Nice! Do you cook at home?"},
        ]
        qs = ai._previous_questions(history)
        assert qs == ["What do you like to eat?", "Do you cook at home?"]

    def test_deduplicates_and_ignores_user_turns(self):
        history = [
            {"role": "user", "content": "Why? really?"},
            {"role": "assistant", "content": "What is your hobby? What is your hobby?"},
        ]
        assert ai._previous_questions(history) == ["What is your hobby?"]

    def test_empty_history(self):
        assert ai._previous_questions([]) == []

    def test_continue_injects_asked_questions_block(self, monkeypatch):
        captured = {}

        async def fake_ask(messages):
            captured["messages"] = messages
            return json.dumps({"topic": "t", "reply": "ok"})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        history = [{"role": "assistant", "content": "Where are you from?"}]
        run(immersive_continue("en", history, "I am from Spain"))
        last = captured["messages"][-1]["content"]
        assert "Where are you from?" in last
        assert "do NOT repeat" in last

    def test_continue_without_questions_has_no_block(self, monkeypatch):
        captured = {}

        async def fake_ask(messages):
            captured["messages"] = messages
            return json.dumps({"topic": "t", "reply": "ok"})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        run(immersive_continue("en", [], "hello"))
        assert "ALREADY asked" not in captured["messages"][-1]["content"]


class TestCorrectGrammar:
    def test_returns_corrected_errors_and_summary(self, monkeypatch):
        payload = {
            "corrected": "I have a cat",
            "errors": [{"error": "I has", "correction": "I have", "explanation": "tercera persona"}],
            "summary": "Concordancia sujeto-verbo",
        }

        async def fake_ask(messages):
            return json.dumps(payload)

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        result = run(correct_grammar("en", "I has a cat"))
        assert result == payload

    def test_no_errors_defaults(self, monkeypatch):
        async def fake_ask(messages):
            return json.dumps({})

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        result = run(correct_grammar("en", "perfect text"))
        assert result == {"corrected": "perfect text", "errors": [], "summary": ""}

    def test_garbage_model_output_raises_valueerror(self, monkeypatch):
        async def fake_ask(messages):
            return "no json"

        monkeypatch.setattr(ai, "ask_ollama", fake_ask)
        with pytest.raises(ValueError, match="Could not parse JSON"):
            run(correct_grammar("en", "hi"))


class TestCheckOllama:
    def test_up_returns_true(self, monkeypatch):
        client = FakeAsyncClient(response=FakeResponse({"models": []}))
        monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: client)
        assert run(check_ollama()) is True

    def test_down_returns_false(self, monkeypatch):
        client = FakeAsyncClient(error=httpx.ConnectError("refused"))
        monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: client)
        assert run(check_ollama()) is False


class TestResolveModel:
    """Fallback automático cuando el modelo configurado no existe en Ollama."""

    def test_configured_model_present(self, monkeypatch):
        client = FakeAsyncClient(
            response=FakeResponse({"models": [{"name": "nova-mini:latest"}, {"name": "qwen3:1.7b"}]})
        )
        monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: client)
        monkeypatch.setattr(ai, "MODEL", "nova-mini")
        assert run(ai.resolve_model()) == "nova-mini"

    def test_tag_with_version_counts_as_present(self, monkeypatch):
        client = FakeAsyncClient(response=FakeResponse({"models": [{"name": "qwen3:1.7b"}]}))
        monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: client)
        monkeypatch.setattr(ai, "MODEL", "qwen3:1.7b")
        assert run(ai.resolve_model()) == "qwen3:1.7b"

    def test_falls_back_when_model_missing(self, monkeypatch):
        client = FakeAsyncClient(response=FakeResponse({"models": [{"name": "qwen3:1.7b"}]}))
        monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: client)
        monkeypatch.setattr(ai, "MODEL", "nova-mini")
        monkeypatch.setattr(ai, "FALLBACK_MODEL", "qwen3:1.7b")
        assert run(ai.resolve_model()) == "qwen3:1.7b"

    def test_tags_down_returns_configured(self, monkeypatch):
        client = FakeAsyncClient(error=httpx.ConnectError("refused"))
        monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: client)
        monkeypatch.setattr(ai, "MODEL", "nova-mini")
        assert run(ai.resolve_model()) == "nova-mini"

    def test_empty_tags_returns_configured(self, monkeypatch):
        client = FakeAsyncClient(response=FakeResponse({"models": []}))
        monkeypatch.setattr(ai.httpx, "AsyncClient", lambda *a, **k: client)
        monkeypatch.setattr(ai, "MODEL", "nova-mini")
        assert run(ai.resolve_model()) == "nova-mini"
