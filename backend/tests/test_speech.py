from backend import config
from backend.speech import _normalize, evaluate


class TestResourceProfile:
    def test_low_profile_by_low_ram(self):
        p = config.resolve_profile(env={}, total_ram_gb=8)
        assert p["low"] is True
        assert p["ollama_model"] == "qwen3:1.7b"
        assert p["whisper_model"] == "base"
        assert p["whisper_beam"] == 1

    def test_high_profile_by_ram(self):
        p = config.resolve_profile(env={}, total_ram_gb=32)
        assert p["low"] is False
        assert p["ollama_model"] == "qwen3:4b"

    def test_env_forces_low(self):
        p = config.resolve_profile(env={"NOVA_PROFILE": "low"}, total_ram_gb=64)
        assert p["low"] is True

    def test_env_forces_high(self):
        p = config.resolve_profile(env={"NOVA_PROFILE": "high"}, total_ram_gb=4)
        assert p["low"] is False


class TestNormalize:
    def test_lowercases_and_strips_punctuation(self):
        assert _normalize("Hello, World!") == "hello world"

    def test_keeps_apostrophes(self):
        assert _normalize("I'm fine") == "i'm fine"

    def test_collapses_whitespace(self):
        assert _normalize("  hi   there  ") == "hi there"


class TestEvaluate:
    def test_perfect_match_scores_100(self):
        result = evaluate("Good morning", "good morning!", "en")
        assert result["score"] == 100
        assert result["missing"] == []
        assert "Excellent" in result["feedback"][0]

    def test_empty_expected_scores_100(self):
        result = evaluate("", "anything", "en")
        assert result["score"] == 100
        assert result["missing"] == []

    def test_empty_transcript_scores_0_and_reports_missing(self):
        result = evaluate("hello world", "   ", "en")
        assert result["score"] == 0
        assert result["missing"] == ["hello", "world"]

    def test_transcript_is_returned_verbatim(self):
        assert evaluate("Hello", "hello there", "en")["transcript"] == "hello there"

    def test_partially_correct_score_between_0_and_100(self):
        result = evaluate("I like pizza and pasta", "I like pizza", "en")
        assert 0 < result["score"] < 100
        assert "pasta" in result["missing"]

    def test_missing_words_are_unique(self):
        # "the" se dice una vez; por alineamiento sobran "cat" y un "the"
        result = evaluate("the cat the cat", "the", "en")
        assert "cat" in result["missing"]
        assert "the" in result["missing"]

    def test_score_is_clamped_to_0_100(self):
        result = evaluate("hello", "completely different words here", "en")
        assert 0 <= result["score"] <= 100

    def test_feedback_present_for_all_scores(self):
        for transcript in ["hello", "hello wor", "xyz abc def"]:
            result = evaluate("hello world", transcript, "en")
            assert result["feedback"]
