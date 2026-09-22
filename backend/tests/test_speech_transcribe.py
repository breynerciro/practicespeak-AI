import sys
import types

import pytest

import backend.speech as speech
from backend.speech import transcribe


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeWhisperModel:
    """Reemplazo de WhisperModel que graba sus argumentos."""

    last_init = None
    last_transcribe = None
    text_to_return = "hello world"

    def __init__(self, model_size, device, compute_type):
        type(self).last_init = (model_size, device, compute_type)

    def transcribe(self, path, language, beam_size):
        # el archivo se borra al terminar transcribe(), así que leemos el
        # contenido ahora y lo guardamos para las aserciones
        with open(path, "rb") as fh:
            content = fh.read()
        type(self).last_transcribe = {
            "path": path,
            "language": language,
            "beam_size": beam_size,
            "content": content,
        }
        return [FakeSegment("hello "), FakeSegment("world ")], {"language": language}


@pytest.fixture()
def fake_whisper(monkeypatch):
    """Inyecta un faster_whisper falso y resetea el singleton del modelo."""
    fake_module = types.ModuleType("faster_whisper")
    fake_module.WhisperModel = FakeWhisperModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_module)
    speech._model = None
    yield FakeWhisperModel
    speech._model = None


class TestTranscribe:
    def test_joins_segment_texts_stripped(self, fake_whisper):
        assert transcribe(b"fake-audio", "en") == "hello world"

    def test_passes_language_and_beam_size(self, fake_whisper):
        transcribe(b"fake-audio", "pt")
        assert fake_whisper.last_transcribe["language"] == "pt"
        assert fake_whisper.last_transcribe["beam_size"] == 3

    def test_writes_bytes_to_tempfile_with_webm_suffix(self, fake_whisper):
        transcribe(b"AUDIOBYTES", "en")
        assert fake_whisper.last_transcribe["path"].endswith(".webm")
        assert fake_whisper.last_transcribe["content"] == b"AUDIOBYTES"

    def test_tempfile_removed_after_transcribe(self, fake_whisper):
        import os

        transcribe(b"fake-audio", "en")
        assert not os.path.exists(fake_whisper.last_transcribe["path"])

    def test_tempfile_removed_even_on_error(self, fake_whisper, monkeypatch):

        def boom(*args, **kwargs):
            raise RuntimeError("disk error")

        monkeypatch.setattr(FakeWhisperModel, "transcribe", boom)
        with pytest.raises(RuntimeError):
            transcribe(b"fake-audio", "en")
        assert speech._model is not None  # el modelo quedó cacheado igualmente

    def test_model_is_cached_between_calls(self, fake_whisper):
        transcribe(b"a", "en")
        first = speech._model
        transcribe(b"b", "en")
        assert speech._model is first

    def test_model_created_with_expected_config(self, fake_whisper):
        transcribe(b"a", "en")
        assert fake_whisper.last_init == ("small", "cpu", "int8")
