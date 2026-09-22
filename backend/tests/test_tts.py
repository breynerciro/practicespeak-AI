import asyncio
import os
from types import SimpleNamespace

import pytest

import backend.tts as tts
from backend.tts import (
    _ensure_piper_model,
    _piper_binary,
    _piper_rel_paths,
    _piper_voice,
    _resolve_voice,
    sintetizar,
)


class FakeCommunicate:
    """Reemplazo de edge_tts.Communicate que registra sus argumentos."""

    last_args = None

    def __init__(self, text, voice):
        type(self).last_args = (text, voice)

    async def stream(self):
        yield {"type": "audio", "data": b"aa"}
        yield {"type": "WordBoundary", "data": b"no-es-audio"}
        yield {"type": "audio", "data": b"bb"}


def run(coro):
    return asyncio.run(coro)


class TestResolveVoice:
    @pytest.mark.parametrize(
        "language,gender,expected_voice",
        [
            ("en", "female", "en-US-AriaNeural"),
            ("en", "male", "en-US-GuyNeural"),
            ("pt", "female", "pt-BR-FranciscaNeural"),
            ("pt", "male", "pt-BR-AntonioNeural"),
            ("fr", "female", "fr-FR-DeniseNeural"),
            ("fr", "male", "fr-FR-HenriNeural"),
            ("de", "female", "de-DE-KatjaNeural"),
            ("de", "male", "de-DE-ConradNeural"),
            ("it", "female", "it-IT-ElsaNeural"),
            ("it", "male", "it-IT-DiegoNeural"),
        ],
    )
    def test_all_language_gender_combinations(self, language, gender, expected_voice):
        assert _resolve_voice(language, gender) == expected_voice

    def test_unknown_language_falls_back_to_english(self):
        assert _resolve_voice("xx", "male") == "en-US-GuyNeural"

    def test_unknown_language_default_gender(self):
        assert _resolve_voice("xx") == "en-US-AriaNeural"

    @pytest.mark.parametrize("bad_gender", ["", "robot", "MALE", None])
    def test_invalid_gender_falls_back_to_female(self, bad_gender):
        assert _resolve_voice("en", bad_gender) == "en-US-AriaNeural"

    def test_module_default_is_female(self):
        # El endpoint /api/tts y el frontend usan "female" por defecto.
        assert tts.VOICES["en"]["female"] == "en-US-AriaNeural"


class TestSintetizar:
    @pytest.mark.parametrize(
        "language,gender,expected_voice",
        [
            ("en", "female", "en-US-AriaNeural"),
            ("pt", "male", "pt-BR-AntonioNeural"),
            ("xx", "male", "en-US-GuyNeural"),
        ],
    )
    def test_voice_passed_to_edge_tts(self, monkeypatch, language, gender, expected_voice):
        monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
        run(sintetizar("hola", language, gender))
        assert FakeCommunicate.last_args == ("hola", expected_voice)

    def test_default_gender_is_female(self, monkeypatch):
        monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
        run(sintetizar("hola", "en"))
        assert FakeCommunicate.last_args == ("hola", "en-US-AriaNeural")

    def test_joins_audio_chunks_and_skips_other_events(self, monkeypatch):
        monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
        assert run(sintetizar("hola", "en")) == b"aabb"


class TestPiperVoice:
    @pytest.mark.parametrize(
        "language,gender,expected",
        [
            ("it", "female", "it_IT-paola-medium"),
            ("it", "male", "it_IT-paola-medium"),  # solo hay paola: cae a femenina
            ("de", "female", "de_DE-thorsten-high"),
            ("de", "male", "de_DE-thorsten-medium"),
            ("fr", "female", "fr_FR-siwis-medium"),
            ("pt", "male", "pt_BR-faber-medium"),
            ("en", "female", "en_US-amy-medium"),
            ("en", "male", "en_US-lessac-medium"),
            ("xx", "female", "en_US-amy-medium"),
        ],
    )
    def test_mapping_all_combinations(self, language, gender, expected):
        assert _piper_voice(language, gender) == expected

    def test_invalid_gender_falls_back_to_female(self):
        assert _piper_voice("de", "") == "de_DE-thorsten-high"


class TestPiperRelPaths:
    @pytest.mark.parametrize(
        "voice,expected",
        [
            ("it_IT-paola-medium", "it/it_IT/paola/medium/it_IT-paola-medium.onnx"),
            ("fr_FR-siwis-medium", "fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx"),
            ("de_DE-thorsten-high", "de/de_DE/thorsten/high/de_DE-thorsten-high.onnx"),
            ("en_US-lessac-medium", "en/en_US/lessac/medium/en_US-lessac-medium.onnx"),
            ("pt_BR-faber-medium", "pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx"),
        ],
    )
    def test_paths_match_repo_layout(self, voice, expected):
        assert _piper_rel_paths(voice) == expected


class TestPiperBackend:
    def test_default_backend_is_edge(self):
        assert _piper_binary() is None

    def test_invalid_backend_id_value_means_edge(self, monkeypatch):
        monkeypatch.setattr(tts.config, "TTS_BACKEND", "piperx")
        assert _piper_binary() is None

    def test_piper_binary_missing_falls_back_to_edge(self, monkeypatch):
        monkeypatch.setattr(tts.config, "TTS_BACKEND", "piper")
        monkeypatch.setattr(tts.shutil, "which", lambda _: None)
        monkeypatch.setattr(tts, "_piper_venv_bin", lambda: None)
        monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
        run(sintetizar("hola", "it"))
        assert FakeCommunicate.last_args == ("hola", "it-IT-ElsaNeural")

    def test_piper_venv_bin_found_without_activation(self, monkeypatch, tmp_path):
        bin_dir = tmp_path / "bin"
        bin_dir.mkdir()
        piper = bin_dir / "piper"
        piper.write_text("#!/bin/sh\n", encoding="utf-8")
        piper.chmod(0o755)
        monkeypatch.setattr(tts.sys, "prefix", str(tmp_path))
        monkeypatch.setattr(tts.config, "TTS_BACKEND", "piper")
        assert _piper_binary() == str(piper)

    def test_piper_venv_bin_missing_returns_none(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tts.sys, "prefix", str(tmp_path))
        monkeypatch.setattr(tts.shutil, "which", lambda _: None)
        monkeypatch.setattr(tts.config, "TTS_BACKEND", "piper")
        assert _piper_binary() is None

    def test_piper_synthesis_error_falls_back_to_edge(self, monkeypatch):
        monkeypatch.setattr(tts.config, "TTS_BACKEND", "piper")
        monkeypatch.setattr(tts.shutil, "which", lambda _: "/usr/bin/piper")

        def boom(*args, **kwargs):
            raise RuntimeError("modelo descargado no")

        monkeypatch.setattr(tts, "_synthesize_piper", boom)
        monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
        assert run(sintetizar("hola", "fr")) == b"aabb"
        assert FakeCommunicate.last_args == ("hola", "fr-FR-DeniseNeural")

    def test_piper_synthesis_returns_wav(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tts.config, "TTS_BACKEND", "piper")
        monkeypatch.setattr(tts.shutil, "which", lambda _: "/usr/bin/piper")
        monkeypatch.setattr(tts.config, "PIPER_HOME", str(tmp_path))
        onnx = tmp_path / "pretend.onnx"
        onnx.write_bytes(b"onnx")
        monkeypatch.setattr(tts, "_ensure_piper_model", lambda _voice: str(onnx))
        captured = {}

        class FakeRun:
            def __call__(self, cmd, input=None, capture_output=False, timeout=120):
                captured["cmd"] = cmd
                captured["input"] = input
                out = cmd[cmd.index("--output_file") + 1]
                with open(out, "wb") as fh:
                    fh.write(b"RIFFwav")
                return SimpleNamespace(returncode=0, stderr=b"")

        monkeypatch.setattr(tts.subprocess, "run", FakeRun())
        data = run(sintetizar("hola", "de", "male"))
        assert data == b"RIFFwav"
        assert captured["input"] == b"hola"
        assert "--model" in captured["cmd"]
        assert captured["cmd"][captured["cmd"].index("--model") + 1] == str(onnx)
        assert [] == [p for p in tmp_path.iterdir() if p.suffix == ".wav"]  # limpia el temporal

    def test_piper_nonzero_exit_raises_and_falls_back(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tts.config, "TTS_BACKEND", "piper")
        monkeypatch.setattr(tts.shutil, "which", lambda _: "/usr/bin/piper")
        monkeypatch.setattr(tts.config, "PIPER_HOME", str(tmp_path))
        monkeypatch.setattr(tts, "_ensure_piper_model", lambda _voice: str(tmp_path / "m.onnx"))
        monkeypatch.setattr(
            tts.subprocess,
            "run",
            lambda cmd, input=None, capture_output=False, timeout=120: SimpleNamespace(returncode=1, stderr=b"boom"),
        )
        monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
        assert run(sintetizar("hola", "en")) == b"aabb"  # cae a edge

    def test_ensure_piper_model_downloads_then_caches(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tts.config, "PIPER_HOME", str(tmp_path))
        downloads = []

        def fake_urlretrieve(url, dest):
            downloads.append(url)
            with open(dest, "wb") as fh:
                fh.write(b"x")

        monkeypatch.setattr(tts, "urlretrieve", fake_urlretrieve)
        onnx = _ensure_piper_model("it_IT-paola-medium")
        assert os.path.isfile(onnx)
        assert os.path.isfile(onnx + ".json")
        assert len(downloads) == 2
        assert downloads[0].endswith("it_IT-paola-medium.onnx")
        assert downloads[1].endswith("it_IT-paola-medium.onnx.json")
        # ya en caché: no vuelve a descargar
        downloads.clear()
        assert _ensure_piper_model("it_IT-paola-medium") == onnx
        assert downloads == []
