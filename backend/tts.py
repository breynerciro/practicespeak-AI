import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from urllib.request import urlretrieve

import edge_tts

from . import config
from .log import log_info

# Dos voces neuronales por idioma (edge-tts). La femenina es la voz por defecto.
VOICES = {
    "en": {"female": "en-US-AriaNeural", "male": "en-US-GuyNeural"},
    "pt": {"female": "pt-BR-FranciscaNeural", "male": "pt-BR-AntonioNeural"},
    "fr": {"female": "fr-FR-DeniseNeural", "male": "fr-FR-HenriNeural"},
    "de": {"female": "de-DE-KatjaNeural", "male": "de-DE-ConradNeural"},
    "it": {"female": "it-IT-ElsaNeural", "male": "it-IT-DiegoNeural"},
}

# Voces piper distribuidas (repo rhasspy/piper-voices, tag v1.0.0). Solo hay
# variantes por género donde existen; el resto cae a la única disponible.
PIPER_VOICES = {
    "en": {"female": "en_US-amy-medium", "male": "en_US-lessac-medium"},
    "pt": {"female": "pt_BR-faber-medium", "male": "pt_BR-faber-medium"},
    "fr": {"female": "fr_FR-siwis-medium", "male": "fr_FR-siwis-medium"},
    "de": {"female": "de_DE-thorsten-high", "male": "de_DE-thorsten-medium"},
    "it": {"female": "it_IT-paola-medium", "male": "it_IT-paola-medium"},
}

PIPER_VOICES_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"


def _resolve_voice(language: str, gender: str = "female") -> str:
    """Voz para el idioma/género; cae a inglés si el idioma es desconocido
    y a femenina si el género no es válido."""
    voices = VOICES.get(language, VOICES["en"])
    return voices.get(gender) or voices["female"]


def _piper_voice(language: str, gender: str = "female") -> str:
    """Voz piper para el idioma/género (cae a inglés y a femenina)."""
    voices = PIPER_VOICES.get(language, PIPER_VOICES["en"])
    return voices.get(gender) or voices["female"]


def _piper_rel_paths(voice_id: str) -> str:
    """Ruta relativa de una voz dentro del repo rhasspy/piper-voices.

    Los ids son {idioma}_{voz}-{calidad} (p. ej. it_IT-paola-medium) y el
    repo los guarda en {lang}/{idioma}/{voz}/{calidad}/{id}.onnx.
    """
    lang_dir, rest = voice_id.split("-", 1)
    family, quality = rest.rsplit("-", 1)
    return f"{lang_dir.split('_')[0]}/{lang_dir}/{family}/{quality}/{voice_id}.onnx"


def _piper_venv_bin() -> str | None:
    """Binario `piper` instalado dentro del propio entorno de Python.

    run.sh arranca uvicorn por rutas absolutas sin activar el venv, así que
    `shutil.which("piper")` no lo ve aunque `pip install piper-tts` lo dejara
    en `.venv/bin`. Se busca aquí para que el backend piper funcione igual.
    """
    local = os.path.join(sys.prefix, "bin", "piper.exe" if os.name == "nt" else "piper")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    return None


def _piper_binary() -> str | None:
    """Ruta al binario `piper` si el backend lo pide y está instalado."""
    if config.TTS_BACKEND != "piper":
        return None
    return shutil.which("piper") or _piper_venv_bin()


def _piper_model_paths(voice_id: str) -> tuple[str, str]:
    rel = _piper_rel_paths(voice_id)
    onnx = os.path.join(config.PIPER_HOME, rel)
    return onnx, onnx + ".json"


def _ensure_piper_model(voice_id: str) -> str:
    """Descarga bajo demanda el modelo (onnx + config) si no está en caché."""
    onnx, json_path = _piper_model_paths(voice_id)
    if os.path.isfile(onnx) and os.path.isfile(json_path):
        return onnx
    base = f"{PIPER_VOICES_BASE_URL}/{_piper_rel_paths(voice_id)}"
    os.makedirs(os.path.dirname(onnx), exist_ok=True)
    urlretrieve(base, onnx)
    urlretrieve(base + ".json", json_path)
    return onnx


def _synthesize_piper(piper_bin: str, texto: str, voice_id: str) -> bytes:
    """Sintetiza con el binario piper (CPU; puede descargar la voz a la
    primera) y devuelve el audio WAV. `piper_bin` es la ruta ya resuelta."""
    onnx = _ensure_piper_model(voice_id)
    out_fd, out_path = tempfile.mkstemp(suffix=".wav", dir=config.PIPER_HOME)
    os.close(out_fd)
    try:
        proc = subprocess.run(
            [piper_bin, "--model", onnx, "--output_file", out_path],
            input=texto.encode("utf-8"),
            capture_output=True,
            timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"piper exit {proc.returncode}: {proc.stderr.decode('utf-8', 'replace')[:200]}")
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(out_path):
            os.remove(out_path)


async def _sintetizar_edge(texto: str, voice: str) -> bytes:
    communicate = edge_tts.Communicate(texto, voice)
    chunks = []
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            chunks.append(chunk["data"])
    return b"".join(chunks)


async def sintetizar(texto: str, language: str, gender: str = "female") -> bytes:
    voice = _resolve_voice(language, gender)
    if piper_bin := _piper_binary():
        try:
            return await asyncio.to_thread(_synthesize_piper, piper_bin, texto, _piper_voice(language, gender))
        except Exception as exc:
            log_info(f"PIPER_FALLBACK edge motivo={exc}")
    return await _sintetizar_edge(texto, voice)
