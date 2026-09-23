"""Protección para compartir PracticeSpeak AI por URL con amigos.

Tres piezas independientes (todas opcionales):

- Código de acceso compartido (NOVA_ACCESS_CODE): si está definido, toda
  petición a /api debe presentarlo vía cabecera `X-Nova-Code` o `?code=…`
  (con tolerancia de mayúsculas y espacios, porque llega copiado a mano).
- Rate limit por IP (NOVA_RATE_LIMIT_PER_MINUTE) para los endpoints caros.
- Semáforo de streams simultáneos (NOVA_MAX_CONCURRENT_STREAMS) para que
  varias personas a la vez no saturen la CPU del LLM.
"""
import time
from collections import defaultdict, deque

from . import config

# ---------------------------------------------------------------- access code

PUBLIC_PATHS = ("/api/health",)


def _provided_code(request) -> str:
    """Código enviado por el cliente (cabecera primero, query como fallback)."""
    return (request.headers.get("x-nova-code") or "").strip() or (
        request.query_params.get("code") or ""
    ).strip()


def check_access_code(request) -> bool:
    """True si la petición puede pasar (o si no hay código configurado).

    La comparación ignora mayúsculas/minúsculas y espacios: el código suele
    copiarse a mano desde un chat de WhatsApp."""
    if not config.ACCESS_CODE:
        return True
    if request.url.path in PUBLIC_PATHS:
        return True
    return _provided_code(request).casefold() == config.ACCESS_CODE.casefold()


def code_ok(request) -> bool:
    """True si no hay código configurado o el presentado es el correcto.

    Helper para /api/health: la ruta es pública, pero gracias a este campo el
    frontend puede validar el código contra health (needs_code dinámico) sin
    necesitar un endpoint de login aparte."""
    return not config.ACCESS_CODE or _provided_code(request).casefold() == config.ACCESS_CODE.casefold()


# ---------------------------------------------------------------- rate limit

_WINDOW = 60.0
_hits: dict[str, deque[float]] = defaultdict(deque)
_last_sweep = 0.0


def _client_ip(request) -> str:
    return request.client.host if request.client else "?"


def _sweep(now: float) -> None:
    """Limpieza perezosa: tira las ventanas vacías para no crecer sin fin."""
    global _last_sweep
    if now - _last_sweep < 300:
        return
    _last_sweep = now
    for ip in [ip for ip, hits in _hits.items() if not hits]:
        del _hits[ip]


def check_rate_limit(request) -> bool:
    """True si la IP no ha superado el cupo de peticiones por minuto.

    Solo se invoca para endpoints caros (chat, grammar, tts, audio); el resto
    de rutas es barato y no cuenta.
    """
    limit = config.RATE_LIMIT_PER_MINUTE
    if limit <= 0:
        return True
    now = time.monotonic()
    ip = _client_ip(request)
    hits = _hits[ip]
    while hits and now - hits[0] > _WINDOW:
        hits.popleft()
    if len(hits) >= limit:
        _sweep(now)
        return False
    hits.append(now)
    _sweep(now)
    return True


# ------------------------------------------------- semáforo de streams (LLM)

class _StreamGate:
    """Limita las conversaciones en streaming simultáneas."""

    def __init__(self) -> None:
        self.limit = config.MAX_CONCURRENT_STREAMS
        self.active = 0
        self.waiting = 0

    @property
    def full(self) -> bool:
        return self.limit > 0 and self.active >= self.limit

    def enter(self) -> bool:
        """Ocupa una plaza; False si el límite está lleno."""
        if self.full:
            return False
        self.active += 1
        return True

    def leave(self) -> None:
        self.active = max(0, self.active - 1)


STREAM_GATE = _StreamGate()
