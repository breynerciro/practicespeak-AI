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

# Parejas de voces neuronales por idioma (edge-tts). La femenina es la voz por
# defecto; estas son las que usa el selector cuando el usuario elige "Auto
# (según género)" y también el conjunto mínimo que siempre está disponible.
VOICES = {
    "en": {"female": "en-US-AriaNeural", "male": "en-US-GuyNeural"},
    "pt": {"female": "pt-BR-FranciscaNeural", "male": "pt-BR-AntonioNeural"},
    "fr": {"female": "fr-FR-DeniseNeural", "male": "fr-FR-HenriNeural"},
    "de": {"female": "de-DE-KatjaNeural", "male": "de-DE-ConradNeural"},
    "it": {"female": "it-IT-ElsaNeural", "male": "it-IT-DiegoNeural"},
    "es": {"female": "es-ES-ElviraNeural", "male": "es-ES-AlvaroNeural"},
    "ru": {"female": "ru-RU-SvetlanaNeural", "male": "ru-RU-DmitryNeural"},
    "zh": {"female": "zh-CN-XiaoxiaoNeural", "male": "zh-CN-YunxiNeural"},
}

# Variantes adicionales de edge-tts que el selector ofrece además de la pareja.
EDGE_EXTRA = {
    "en": ["en-GB-SoniaNeural", "en-AU-NatashaNeural", "en-US-JennyNeural"],
    "pt": ["pt-PT-RaquelNeural", "pt-PT-DuarteNeural"],
    "fr": ["fr-FR-JulieNeural", "fr-CA-SylvieNeural"],
    "de": ["de-AT-IngridNeural", "de-CH-RogerNeural"],
    "es": ["es-MX-DaliaNeural", "es-MX-JorgeNeural", "es-AR-ElenaNeural"],
    "zh": ["zh-CN-XiaoyiNeural", "zh-CN-YunjianNeural"],
}

# Parejas de voces piper (repo rhasspy/piper-voices, tag v1.0.0). Solo hay
# variantes por género donde existen; el resto cae a la única disponible.
PIPER_VOICES = {
    "en": {"female": "en_US-amy-medium", "male": "en_US-lessac-medium"},
    "pt": {"female": "pt_BR-faber-medium", "male": "pt_BR-faber-medium"},
    "fr": {"female": "fr_FR-siwis-medium", "male": "fr_FR-siwis-medium"},
    "de": {"female": "de_DE-thorsten-high", "male": "de_DE-thorsten-medium"},
    "it": {"female": "it_IT-paola-medium", "male": "it_IT-paola-medium"},
    "es": {"female": "es_ES-sharvard-medium", "male": "es_ES-davefx-medium"},
    "ru": {"female": "ru_RU-irina-medium", "male": "ru_RU-dmitri-medium"},
    "zh": {"female": "zh_CN-huayan-medium", "male": "zh_CN-huayan-medium"},
}

# Variantes piper adicionales (verificadas en el repo v1.0.0).
PIPER_EXTRA = {
    "en": ["en_GB-alan-medium", "en_US-libritts-high", "en_US-ryan-high"],
    "es": ["es_ES-carlfm-x_low", "es_ES-mls_9972-low"],
    "ru": ["ru_RU-ruslan-medium"],
    "zh": ["zh_CN-huayan-x_low"],
}

PIPER_VOICES_BASE_URL = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0"

# Tope para una síntesis de edge-tts (nube): una llamada colgada debe fallar
# rápido (502) y no congelar el habla del tutor.
EDGE_TTS_TIMEOUT = 20.0

# Índice de todas las voces piper conocidas (para reconocer un id en /api/tts).
_PIPER_IDS = frozenset(
    vid
    for voices in PIPER_VOICES.values()
    for vid in voices.values()
) | frozenset(vid for extra in PIPER_EXTRA.values() for vid in extra)


def _resolve_voice(language: str, gender: str = "female") -> str:
    """Voz edge por defecto para el idioma/género; cae a inglés si el idioma
    es desconocido y a femenina si el género no es válido."""
    voices = VOICES.get(language, VOICES["en"])
    return voices.get(gender) or voices["female"]


def _piper_voice(language: str, gender: str = "female") -> str:
    """Voz piper por defecto para el idioma/género (cae a inglés y a femenina)."""
    voices = PIPER_VOICES.get(language, PIPER_VOICES["en"])
    return voices.get(gender) or voices["female"]


def _voice_name(voice_id: str, source: str) -> str:
    """Nombre legible de una voz para mostrarlo en el selector.

    piper: `es_ES-davefx-medium`  -> "Davefx · es (medium, local)"
    edge:  `es-ES-ElviraNeural`   -> "Elvira · es-ES (nube)"
    """
    if source == "edge":
        parts = voice_id.split("-")
        speaker = parts[-1].removesuffix("Neural") or voice_id
        lang = parts[0] if parts else ""
        region = parts[1] if len(parts) > 1 else ""
        return f"{speaker} · {lang}-{region} (nube)"
    prefix, _, _rest = voice_id.partition("-")
    lang = prefix.split("_")[0]
    family, quality = _rest.rsplit("-", 1)
    return f"{family.capitalize()} · {lang} ({quality}, local)"


def list_voices(language: str) -> list[dict]:
    """Voces disponibles para un idioma: las locales (piper) primero y luego
    las de nube (edge). Cada voz lleva `id`, `name` y `source`."""
    voices: list[dict] = []
    seen: set[str] = set()
    piper_ids: list[str] = []
    for vid in PIPER_VOICES.get(language, PIPER_VOICES["en"]).values():
        if vid not in seen:
            piper_ids.append(vid)
            seen.add(vid)
    for vid in PIPER_EXTRA.get(language, []):
        if vid not in seen:
            piper_ids.append(vid)
            seen.add(vid)
    for vid in piper_ids:
        onnx, _json = _piper_model_paths(vid)
        voices.append(
            {
                "id": vid,
                "name": _voice_name(vid, "local"),
                "source": "local",
                "installed": os.path.isfile(onnx),
            }
        )
    edge_ids = list(VOICES.get(language, VOICES["en"]).values()) + EDGE_EXTRA.get(language, [])
    for vid in edge_ids:
        if vid in seen:
            continue
        voices.append({"id": vid, "name": _voice_name(vid, "edge"), "source": "edge"})
    return voices


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


def _synthesize_piper(piper_bin: str, texto: str, voice_id: str, length_scale: float = 1.0) -> bytes:
    """Sintetiza con el binario piper (CPU; puede descargar la voz a la
    primera) y devuelve el audio WAV. `piper_bin` es la ruta ya resuelta y
    `length_scale` ajusta la velocidad (1.0 = normal; <1 más rápido)."""
    onnx = _ensure_piper_model(voice_id)
    out_fd, out_path = tempfile.mkstemp(suffix=".wav", dir=config.PIPER_HOME)
    os.close(out_fd)
    try:
        cmd = [piper_bin, "--model", onnx, "--output_file", out_path]
        if length_scale != 1.0:
            cmd += ["--length_scale", f"{length_scale:.3f}"]
        proc = subprocess.run(
            cmd,
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


def _clamp_speed(speed: float) -> float:
    """Velocidad de habla acotada (0.5×–1.5×)."""
    try:
        speed = float(speed)
    except (TypeError, ValueError):
        return 1.0
    return max(0.5, min(1.5, speed))


def _rate_for_speed(speed: float) -> str | None:
    """Cadena `rate` de edge-tts para una velocidad; None si es la normal."""
    pct = round((_clamp_speed(speed) - 1.0) * 100)
    return None if pct == 0 else f"{pct:+d}%"


async def _sintetizar_edge(texto: str, voice: str, rate: str | None = None) -> bytes:
    communicate = edge_tts.Communicate(texto, voice, rate=rate) if rate else edge_tts.Communicate(texto, voice)
    chunks: list[bytes] = []

    async def _collect() -> None:
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.append(chunk["data"])

    try:
        await asyncio.wait_for(_collect(), timeout=EDGE_TTS_TIMEOUT)
    except asyncio.TimeoutError as exc:
        raise RuntimeError("edge-tts agotó el tiempo de espera") from exc
    return b"".join(chunks)


async def sintetizar(texto: str, language: str, gender: str = "female", voice: str = "", speed: float = 1.0) -> bytes:
    """Convierte texto en audio.

    Si `voice` viene dado, lo usa tal cual: un id de piper (`*_*-*`) se
    sintetiza en local (descargando el modelo a la primera) y cualquier otro
    id se envía a edge-tts. Sin `voice` se usa la pareja por defecto del
    idioma/género. `speed` (0.5×–1.5×) se aplica a ambos motores.
    """
    speed = _clamp_speed(speed)
    rate = _rate_for_speed(speed)
    length_scale = 1.0 / speed if speed != 1.0 else 1.0
    voice = voice.strip()
    if voice:
        piper_bin = _piper_binary()
        if piper_bin and voice in _PIPER_IDS:
            try:
                return await asyncio.to_thread(_synthesize_piper, piper_bin, texto, voice, length_scale)
            except Exception as exc:
                log_info(f"PIPER_FALLBACK edge motivo={exc}")
        return await _sintetizar_edge(texto, voice, rate)

    voice = _resolve_voice(language, gender)
    if piper_bin := _piper_binary():
        try:
            return await asyncio.to_thread(
                _synthesize_piper, piper_bin, texto, _piper_voice(language, gender), length_scale
            )
        except Exception as exc:
            log_info(f"PIPER_FALLBACK edge motivo={exc}")
    return await _sintetizar_edge(texto, voice, rate)
