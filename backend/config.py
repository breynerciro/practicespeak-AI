"""Configuración por variables de entorno.

Todos los valores tienen defaults que funcionan en local; en producción se
ajustan con .env o variables de entorno (ver .env.example).

Incluye un perfil de recursos autodetectado: en PCs con poca RAM (p. ej. 8 GB
sin GPU) baja automáticamente a un modelo LLM más pequeño, un Whisper más
ligero y generación más corta. NOVA_PROFILE=low|high fuerza el perfil.
"""
import os

# --- Perfil de recursos -----------------------------------------------------


def _read_total_ram_gb() -> float:
    """RAM total en GB. Fallback 16 si no se puede leer (fuera de Linux)."""
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1024 * 1024)
    except Exception:
        pass
    return 16.0


def resolve_profile(env: dict | None = None, total_ram_gb: float | None = None) -> dict:
    """Resuelve el perfil de recursos del PC.

    - NOVA_PROFILE=low|high lo fuerza.
    - Sin variable: autodetección (RAM < 10 GB => low, pensado para 8 GB).
    """
    env = dict(os.environ if env is None else env)
    ram = _read_total_ram_gb() if total_ram_gb is None else total_ram_gb
    requested = (env.get("NOVA_PROFILE") or "").strip().lower()
    if requested in ("low", "high"):
        low = requested == "low"
    else:
        low = ram < 10
    return {
        "low": low,
        "ollama_model": "qwen3:1.7b" if low else "qwen3:4b",
        "whisper_model": "base" if low else "small",
        "whisper_beam": 1 if low else 3,
        "num_predict": 160 if low else 220,
    }


_PROFILE = resolve_profile()

# --- Ollama / LLM ---
OLLAMA_BASE_URL = os.environ.get("NOVA_OLLAMA_BASE_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.environ.get("NOVA_OLLAMA_MODEL", _PROFILE["ollama_model"])
OLLAMA_TIMEOUT = int(os.environ.get("NOVA_OLLAMA_TIMEOUT", "180"))
NUM_PREDICT = int(os.environ.get("NOVA_NUM_PREDICT", str(_PROFILE["num_predict"])))

# --- Whisper ---
WHISPER_MODEL_SIZE = os.environ.get("NOVA_WHISPER_MODEL", _PROFILE["whisper_model"])
WHISPER_BEAM = int(os.environ.get("NOVA_WHISPER_BEAM", str(_PROFILE["whisper_beam"])))

# --- Acceso (compartir por URL) ---
# Código compartido: si está definido, toda petición a /api (salvo /api/health)
# debe presentarlo vía cabecera X-Nova-Code o ?code=. Vacío = sin protección.
ACCESS_CODE = os.environ.get("NOVA_ACCESS_CODE", "").strip()
# Máximo de conversaciones en streaming simultáneas (protege la CPU cuando
# varias personas usan PracticeSpeak AI a la vez). Cero = sin límite.
MAX_CONCURRENT_STREAMS = int(os.environ.get("NOVA_MAX_CONCURRENT_STREAMS", "2"))
# Peticiones por IP para endpoints caros (/api/chat, /api/grammar, /api/tts,
# /api/audio) en una ventana de 60 s. Cero = sin límite.
RATE_LIMIT_PER_MINUTE = int(os.environ.get("NOVA_RATE_LIMIT_PER_MINUTE", "30"))

# --- TTS ---
# NOVA_TTS_BACKEND=edge usa edge-tts (necesita internet) y
# NOVA_TTS_BACKEND=piper usa piper local con fallback a edge.
TTS_BACKEND = (os.environ.get("NOVA_TTS_BACKEND") or "edge").strip().lower()
if TTS_BACKEND not in ("edge", "piper"):
    TTS_BACKEND = "edge"
# Idiomas que se pueden practicar (espejo de schemas.Language). El selector de
# voces usa esta lista para agruparlas por idioma.
SUPPORTED_LANGUAGES = ("en", "pt", "fr", "de", "it", "es", "ru", "zh")
# Carpeta donde se descargan bajo demanda los modelos de piper (rhasspy/piper-voices).
PIPER_HOME = os.environ.get("NOVA_PIPER_HOME", os.path.expanduser("~/.local/share/nova/piper"))

# --- Servidor ---
HOST = os.environ.get("NOVA_HOST", "0.0.0.0")
PORT = int(os.environ.get("NOVA_PORT", "8000"))
HTTPS_PORT = int(os.environ.get("NOVA_HTTPS_PORT", "8443"))

# Dominio público HTTPS (para redirección y avisos del frontend); vacío = sin redirect
PUBLIC_HOSTNAME = os.environ.get("NOVA_PUBLIC_HOSTNAME", "")

# --- Datos persistentes ---
# Carpeta para la base SQLite (y logs de run.sh). IMPORTANTE: fuera de /tmp,
# para que las sesiones y correcciones sobrevivan a los reinicios cuando el
# servidor comparte con varias personas.
DATA_DIR = os.path.expanduser(os.environ.get("NOVA_DATA_DIR", "~/.local/share/nova"))
LOG_DIR = os.environ.get("NOVA_LOG_DIR", os.path.join(DATA_DIR, "logs"))
