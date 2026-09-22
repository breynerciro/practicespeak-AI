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
            ("es", "female", "es-ES-ElviraNeural"),
            ("es", "male", "es-ES-AlvaroNeural"),
            ("ru", "female", "ru-RU-SvetlanaNeural"),
            ("ru", "male", "ru-RU-DmitryNeural"),
            ("zh", "female", "zh-CN-XiaoxiaoNeural"),
            ("zh", "male", "zh-CN-YunxiNeural"),
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

    def test_edge_voice_override_used_as_is(self, monkeypatch):
        monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
        run(sintetizar("hola", "en", "female", "es-ES-ElviraNeural"))
        assert FakeCommunicate.last_args == ("hola", "es-ES-ElviraNeural")

    def test_piper_voice_override_uses_specified_id(self, monkeypatch):
        monkeypatch.setattr(tts.config, "TTS_BACKEND", "piper")
        monkeypatch.setattr(tts.shutil, "which", lambda _: "/usr/bin/piper")
        captured = {}

        def fake_synth(piper_bin, texto, voice_id):
            captured.update(piper_bin=piper_bin, texto=texto, voice_id=voice_id)
            return b"RIFFwav"

        monkeypatch.setattr(tts, "_synthesize_piper", fake_synth)
        data = run(sintetizar("hola", "en", "female", "es_ES-davefx-medium"))
        assert data == b"RIFFwav"
        assert captured == {
            "piper_bin": "/usr/bin/piper",
            "texto": "hola",
            "voice_id": "es_ES-davefx-medium",
        }

    def test_piper_voice_override_falls_back_to_edge_on_error(self, monkeypatch):
        monkeypatch.setattr(tts.config, "TTS_BACKEND", "piper")
        monkeypatch.setattr(tts.shutil, "which", lambda _: "/usr/bin/piper")

        def boom(*args, **kwargs):
            raise RuntimeError("no hay voz")

        monkeypatch.setattr(tts, "_synthesize_piper", boom)
        monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
        assert run(sintetizar("hola", "en", "female", "es_ES-davefx-medium")) == b"aabb"
        assert FakeCommunicate.last_args == ("hola", "es_ES-davefx-medium")

    def test_unknown_voice_override_goes_to_edge(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tts.config, "TTS_BACKEND", "piper")
        monkeypatch.setattr(tts.shutil, "which", lambda _: "/usr/bin/piper")
        monkeypatch.setattr(tts.edge_tts, "Communicate", FakeCommunicate)
        run(sintetizar("hola", "en", "female", "some-other-id"))
        assert FakeCommunicate.last_args == ("hola", "some-other-id")


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
            ("es", "female", "es_ES-sharvard-medium"),
            ("es", "male", "es_ES-davefx-medium"),
            ("ru", "female", "ru_RU-irina-medium"),
            ("ru", "male", "ru_RU-dmitri-medium"),
            ("zh", "female", "zh_CN-huayan-medium"),
            ("zh", "male", "zh_CN-huayan-medium"),
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
            ("es_ES-davefx-medium", "es/es_ES/davefx/medium/es_ES-davefx-medium.onnx"),
            ("ru_RU-irina-medium", "ru/ru_RU/irina/medium/ru_RU-irina-medium.onnx"),
            ("zh_CN-huayan-x_low", "zh/zh_CN/huayan/x_low/zh_CN-huayan-x_low.onnx"),
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


class TestListVoices:
    def test_es_lists_local_and_edge_without_duplicates(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tts.config, "PIPER_HOME", str(tmp_path))
        voices = tts.list_voices("es")
        ids = [v["id"] for v in voices]
        assert len(ids) == len(set(ids))
        local = [v for v in voices if v["source"] == "local"]
        edge = [v for v in voices if v["source"] == "edge"]
        assert "es_ES-sharvard-medium" in ids
        assert "es_ES-davefx-medium" in ids
        assert "es_ES-carlfm-x_low" in ids
        assert "es-ES-ElviraNeural" in ids
        assert "es-ES-AlvaroNeural" in ids
        assert any(v["name"] == "Davefx · es (medium, local)" for v in local)
        assert any(v["name"] == "Elvira · es-ES (nube)" for v in edge)
        assert all(v["installed"] is False for v in local)

    def test_unknown_language_falls_back_to_english_voices(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tts.config, "PIPER_HOME", str(tmp_path))
        assert tts.list_voices("xx")[0]["id"] == "en_US-amy-medium"

    def test_piper_extras_are_included(self, monkeypatch, tmp_path):
        monkeypatch.setattr(tts.config, "PIPER_HOME", str(tmp_path))
        ids = [v["id"] for v in tts.list_voices("en")]
        assert "en_GB-alan-medium" in ids
        assert "en_US-libritts-high" in ids
        assert "en-US-JennyNeural" in ids  # extra de edge también

    @pytest.mark.parametrize(
        "voice_id,source,expected",
        [
            ("es_ES-davefx-medium", "local", "Davefx · es (medium, local)"),
            ("en_US-amy-medium", "local", "Amy · en (medium, local)"),
            ("zh_CN-huayan-x_low", "local", "Huayan · zh (x_low, local)"),
            ("es-ES-ElviraNeural", "edge", "Elvira · es-ES (nube)"),
            ("en-GB-SoniaNeural", "edge", "Sonia · en-GB (nube)"),
        ],
    )
    def test_voice_name_formatting(self, voice_id, source, expected):
        assert tts._voice_name(voice_id, source) == expected
