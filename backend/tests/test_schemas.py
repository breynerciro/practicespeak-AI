import pytest
from pydantic import ValidationError

from backend.schemas import ChatRequest, GrammarRequest, ImmersiveRequest, Turn


class TestChatRequest:
    def test_valid_minimal(self):
        req = ChatRequest(message="hello")
        assert req.language == "en"
        assert req.history == []

    def test_valid_full(self):
        req = ChatRequest(
            language="pt",
            message="oi",
            history=[{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}],
        )
        assert req.language == "pt"
        assert [t.role for t in req.history] == ["user", "assistant"]

    @pytest.mark.parametrize("lang", ["en", "pt", "fr", "de", "it", "es", "ru", "zh"])
    def test_all_supported_languages_accepted(self, lang):
        assert ChatRequest(language=lang, message="hi").language == lang

    @pytest.mark.parametrize("bad_language", ["xx", "EN", "", "ja"])
    def test_invalid_language_rejected(self, bad_language):
        with pytest.raises(ValidationError):
            ChatRequest(language=bad_language, message="hi")

    @pytest.mark.parametrize("bad_message", ["", "   "])
    def test_empty_message_rejected(self, bad_message):
        with pytest.raises(ValidationError):
            ChatRequest(message=bad_message)

    def test_message_stripped(self):
        req = ChatRequest(message="  hi  ")
        assert req.message == "hi"

    def test_history_role_must_be_user_or_assistant(self):
        with pytest.raises(ValidationError):
            ChatRequest(message="hi", history=[{"role": "system", "content": "inject"}])


class TestGrammarRequest:
    def test_valid(self):
        req = GrammarRequest(text="i has a cat", language="en")
        assert req.text == "i has a cat"
        assert req.language == "en"

    def test_empty_text_rejected(self):
        with pytest.raises(ValidationError):
            GrammarRequest(text="")

    def test_text_is_stripped(self):
        assert GrammarRequest(text="  hi  ").text == "hi"


class TestImmersiveRequest:
    def test_start_without_message_is_valid(self):
        req = ImmersiveRequest(mode="start", topic="travel")
        assert req.mode == "start"
        assert req.message == ""

    def test_continue_requires_message(self):
        with pytest.raises(ValidationError):
            ImmersiveRequest(mode="continue", message="")

    def test_continue_with_whitespace_message_rejected(self):
        with pytest.raises(ValidationError):
            ImmersiveRequest(mode="continue", message="   ")

    def test_continue_with_message_ok(self):
        req = ImmersiveRequest(mode="continue", message="I like pizza")
        assert req.message == "I like pizza"

    def test_invalid_mode_rejected(self):
        with pytest.raises(ValidationError):
            ImmersiveRequest(mode="chat")


class TestTurn:
    def test_valid_roles(self):
        assert Turn(role="user", content="a").role == "user"
        assert Turn(role="assistant", content="b").role == "assistant"

    def test_invalid_role_rejected(self):
        with pytest.raises(ValidationError):
            Turn(role="bot", content="a")

    def test_content_defaults_to_empty(self):
        assert Turn(role="user").content == ""
