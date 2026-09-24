import difflib
import json
import random
import re
import time
import unicodedata

import httpx

from . import config
from .log import log_info
from .prompts import (
    build_continue_user_message,
    build_immersive_system,
    build_pronunciation_system,
    build_start_user_message,
    build_system_prompt,
)

OLLAMA_URL = config.OLLAMA_BASE_URL + "/api/chat"
OLLAMA_TAGS_URL = config.OLLAMA_BASE_URL + "/api/tags"
MODEL = config.OLLAMA_MODEL
OLLAMA_TIMEOUT = config.OLLAMA_TIMEOUT
# Modelo al que caer si el configurado no existe en Ollama (p. ej. un modelo
# personalizado creado con `ollama create` que falta en una instalación nueva).
FALLBACK_MODEL = config.os.environ.get("NOVA_OLLAMA_FALLBACK_MODEL", "qwen3:1.7b")


class NovaError(RuntimeError):
    """Error al comunicarse con Ollama (modelo local no disponible o respuesta inesperada)."""


TOPICS = [
    "travel",
    "daily routine",
    "food and cooking",
    "hobbies and free time",
    "family",
    "work and studies",
    "weather and seasons",
    "movies and series",
    "sports",
    "music",
    "technology and gadgets",
    "animals and pets",
    "shopping and clothes",
    "health and fitness",
    "birthdays and celebrations",
    "books and reading",
    "nature and the environment",
    "cars and transport",
    "house and home",
    "weekend plans",
]


class TopicManager:
    """Gestiona la selección de temas evitando repeticiones recientes.

    Encapsula el estado de temas usados para hacerlo testable y thread-safe.
    """

    def __init__(self, max_recent: int = 6):
        self._recent: list[str] = []
        self._max_recent = max_recent

    def pick(self, available: list[str] | None = None) -> str:
        """Elige un tema al azar evitando los últimos usados.

        Si todos están quemados, saca de la lista completa.
        """
        pool = available if available is not None else TOPICS
        candidates = [t for t in pool if t not in self._recent]
        if not candidates:
            candidates = list(pool)
        topic = random.choice(candidates)
        self._recent.append(topic)
        if len(self._recent) > self._max_recent:
            self._recent = self._recent[-self._max_recent:]
        return topic

    def reset(self) -> None:
        """Limpia el historial de temas recientes."""
        self._recent = []


# Instancia global para mantener consistencia en la sesión
_topic_manager = TopicManager()


# Caché para resolve_model(): evita hacer HTTP a /api/tags en cada petición.
_MODEL_CACHE: dict = {"model": None, "ts": 0.0}
_MODEL_CACHE_TTL = 30.0  # segundos


def reset_model_cache() -> None:
    """Limpia la caché de modelos. Solo para tests."""
    _MODEL_CACHE["model"] = None
    _MODEL_CACHE["ts"] = 0.0


def reset_topic_history() -> None:
    """Limpia el historial de temas. Solo para tests."""
    _topic_manager.reset()


def pick_topic() -> str:
    """Elige un tema al azar evitando los últimos usados; si todos están
    quemados, saca de la lista completa."""
    return _topic_manager.pick()


LANG_NAMES = {
    "en": "English",
    "pt": "Portuguese (Brazilian)",
    "fr": "French",
    "de": "German",
    "it": "Italian",
    "es": "Spanish",
    "ru": "Russian",
    "zh": "Mandarin Chinese",
}

_QUESTION_RE = re.compile(r"[^.!?]*\?")


def _previous_questions(history: list[dict]) -> list[str]:
    """Preguntas que el tutor ya hizo en esta conversación (normalizadas y sin duplicados).

    Se extraen de los turnos del asistente del historial para poder decirle al
    modelo explícitamente qué NO volver a preguntar.
    """
    seen: set[str] = set()
    questions: list[str] = []
    for h in history:
        if h.get("role") != "assistant":
            continue
        for fragment in _QUESTION_RE.findall(h.get("content", "")):
            normalized = " ".join(fragment.lower().split())
            if normalized and normalized not in seen:
                seen.add(normalized)
                questions.append(fragment.strip())
    return questions


def _lang_name(language: str) -> str:
    return LANG_NAMES.get(language, "English")


def _lang_name_es(language: str) -> str:
    """Nombre del idioma en español, para mensajes al estudiante."""
    return {
        "en": "inglés",
        "pt": "portugués",
        "fr": "francés",
        "de": "alemán",
        "it": "italiano",
        "es": "español",
        "ru": "ruso",
        "zh": "chino mandarín",
    }.get(language, "inglés")


def _build_messages(mode: str, language: str, history: list[dict], message: str) -> list[dict]:
    lang = LANG_NAMES.get(language, "English")
    system = build_system_prompt(mode, lang)
    msgs = [{"role": "system", "content": system}]
    for h in history:
        if h.get("role") in ("user", "assistant"):
            msgs.append({"role": h["role"], "content": h["content"]})
    msgs.append({"role": "user", "content": message})
    return msgs


def _ollama_options() -> dict:
    return {
        "temperature": 0.8,
        "top_p": 0.9,
        # penaliza re-generar tokens ya emitidos: menos frases y
        # preguntas repetidas por parte del modelo
        "repeat_penalty": 1.15,
        "num_predict": config.NUM_PREDICT,
    }


async def ask_ollama(messages: list[dict]) -> str:
    payload = {
        "model": await resolve_model(),
        "messages": messages,
        "stream": False,
        "format": "json",
        "think": False,
        "options": _ollama_options(),
    }
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            resp = await client.post(OLLAMA_URL, json=payload)
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise NovaError(f"No se pudo contactar con Ollama: {exc}") from exc
    try:
        return data["message"]["content"]
    except (KeyError, TypeError) as exc:
        raise NovaError(f"Respuesta inesperada de Ollama: {str(data)[:200]}") from exc


def _clean_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
        raise ValueError(f"Could not parse JSON from model: {raw[:200]}") from None


async def ask_ollama_stream(messages: list[dict]):
    """Igual que `ask_ollama` pero en streaming: Ollama devuelve NDJSON
    (un objeto JSON por línea) y este generador produce los fragmentos de
    `message.content` conforme se generan."""
    payload = {
        "model": await resolve_model(),
        "messages": messages,
        "stream": True,
        "format": "json",
        "think": False,
        "options": _ollama_options(),
    }
    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            async with client.stream("POST", OLLAMA_URL, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if chunk.get("error"):
                        raise NovaError(f"Ollama error: {chunk['error']}")
                    delta = (chunk.get("message") or {}).get("content") or ""
                    if delta:
                        yield delta
                    if chunk.get("done"):
                        return
    except NovaError:
        raise
    except (httpx.HTTPError, ValueError) as exc:
        raise NovaError(f"No se pudo contactar con Ollama: {exc}") from exc


_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "b": "\b",
    "f": "\f",
    '"': '"',
    "\\": "\\",
    "/": "/",
}

_FIELD_VALUE_RE_CACHE: dict[str, re.Pattern] = {}


def _field_value_re(field: str) -> re.Pattern:
    pattern = _FIELD_VALUE_RE_CACHE.get(field)
    if pattern is None:
        pattern = re.compile(r'"' + re.escape(field) + r'"\s*:\s*"')
        _FIELD_VALUE_RE_CACHE[field] = pattern
    return pattern


def _json_field_progressive(buffer: str, field: str) -> tuple[str | None, bool]:
    """Lee el valor string del campo `field` en el JSON que el modelo arma
    token a token.

    Devuelve (None, False) si la clave aún no apareció; (texto, False) si
    el valor está a medias (la comilla de cierre aún no llegó o un escape
    está truncado); (texto, True) si el valor está completo. Sirve para
    emitir deltas progresivos del texto del tutor sin esperar al JSON entero.
    """
    match = _field_value_re(field).search(buffer)
    if not match:
        return None, False
    out: list[str] = []
    i = match.end()
    n = len(buffer)
    while i < n:
        char = buffer[i]
        if char == '"':
            return "".join(out), True
        if char == "\\":
            if i + 1 >= n:
                return "".join(out), False
            nxt = buffer[i + 1]
            if nxt == "u":
                if i + 5 >= n:
                    return "".join(out), False
                try:
                    out.append(chr(int(buffer[i + 2 : i + 6], 16)))
                except ValueError:
                    out.append("u")
                i += 6
                continue
            out.append(_ESCAPES.get(nxt, nxt))
            i += 2
            continue
        out.append(char)
        i += 1
    return "".join(out), False


async def tutor_chat(language: str, history: list[dict], message: str) -> dict:
    messages = _build_messages("conversation", language, history, message)
    raw = await ask_ollama(messages)
    data = _clean_json(raw)
    return {
        "reply": data.get("reply", "I didn't understand, sorry."),
        "corrections": data.get("corrections", []),
    }


async def correct_grammar(language: str, text: str) -> dict:
    messages = _build_messages("grammar", language, [], text)
    raw = await ask_ollama(messages)
    data = _clean_json(raw)
    return {
        "corrected": data.get("corrected", text),
        "errors": data.get("errors", []),
        "summary": data.get("summary", ""),
    }


async def immersive_start(language: str, topic: str | None = None) -> dict:
    lang = _lang_name(language)
    system = build_immersive_system(lang)
    if topic:
        user_msg = (
            f"BEGIN a new immersive session. The student suggested this topic: '{topic}'.\n"
            f"Greet the student briefly and ask your first engaging question about '{topic}' in {lang}. Keep it short."
        )
    else:
        chosen = pick_topic()
        log_info(f"TOPIC_ELEGIDO: {chosen}")
        topic = chosen
        user_msg = build_start_user_message(lang, chosen)
    messages = [{"role": "system", "content": system}, {"role": "user", "content": user_msg}]
    raw = await ask_ollama(messages)
    data = _clean_json(raw)
    return {
        # El tema lo decide el backend (pedido por el usuario o sorteado),
        # nunca el eco del modelo.
        "topic": topic or TOPICS[0],
        "reply": data.get("reply", ""),
        "corrections": data.get("corrections", []),
    }


async def immersive_continue(language: str, history: list[dict], user_text: str) -> dict:
    lang = _lang_name(language)
    system = build_immersive_system(lang)
    msgs = [{"role": "system", "content": system}]
    for h in history[-12:]:
        if h.get("role") in ("user", "assistant"):
            msgs.append({"role": h["role"], "content": h["content"]})
    asked = _previous_questions(history)
    user_content = build_continue_user_message(user_text, asked)
    msgs.append({"role": "user", "content": user_content})
    raw = await ask_ollama(msgs)
    data = _clean_json(raw)
    return {
        "topic": data.get("topic", ""),
        "reply": data.get("reply", ""),
        "corrections": data.get("corrections", []),
    }


def resolve_start_topic(topic: str | None) -> str:
    """Tema de arranque de un modo inmersivo: si el estudiante sugiere uno lo
    usa; si no, sortea uno evitando repetir los recientes. Siempre devuelve un
    tema no vacío."""
    if topic:
        chosen = topic.strip()
        if chosen:
            return chosen
    chosen = pick_topic()
    log_info(f"TOPIC_ELEGIDO: {chosen}")
    return chosen


async def immersive_chat_stream(
    mode: str,
    language: str,
    history: list[dict],
    user_text: str,
    topic: str | None = None,
):
    """Genera los eventos de una sesión inmersiva en streaming.

    Secuencia de eventos: `topic` (el decidido por el backend en start, o el
    que el modelo devuelve en continue), `delta`* (texto parcial de `reply`),
    `corrections`? y `done`. Los errores de Ollama se propagan como
    `NovaError` para que el endpoint los convierta en evento `error`.
    """
    lang = _lang_name(language)
    system = build_immersive_system(lang)
    if mode == "start":
        chosen = resolve_start_topic(topic)
        yield {"type": "topic", "topic": chosen}
        user_msg = build_start_user_message(lang, chosen)
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user_msg}]
    else:
        msgs = [{"role": "system", "content": system}]
        for turn in history[-12:]:
            if turn.get("role") in ("user", "assistant"):
                msgs.append({"role": turn["role"], "content": turn["content"]})
        asked = _previous_questions(history)
        content = build_continue_user_message(user_text, asked)
        msgs.append({"role": "user", "content": content})

    buffer = ""
    reply_complete = False
    topic_sent = mode == "start"  # en start el tema ya se entregó
    async for chunk in ask_ollama_stream(msgs):
        buffer += chunk
        if mode == "continue" and not topic_sent:
            partial, complete = _json_field_progressive(buffer, "topic")
            if complete and partial:
                topic_sent = True
                yield {"type": "topic", "topic": partial}
        if reply_complete:
            continue
        partial, complete = _json_field_progressive(buffer, "reply")
        if partial:
            yield {"type": "delta", "text": partial}
            if complete:
                reply_complete = True

    data = _clean_json(buffer)
    reply = data.get("reply", "")
    corrections = data.get("corrections", []) or []
    if mode == "continue" and not topic_sent:
        model_topic = data.get("topic", "")
        if model_topic:
            yield {"type": "topic", "topic": model_topic}
    if corrections:
        yield {"type": "corrections", "corrections": corrections}
    yield {"type": "done", "reply": reply, "corrections": corrections}


async def check_ollama() -> bool:
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(OLLAMA_TAGS_URL)
            resp.raise_for_status()
            return True
    except Exception:
        return False


_FUNC_WORDS = frozenset(
    """
    de do da dos das em no na nos nas um uma uns o a os as que com por para pra pra e ou se ao
    à às the an of to in on at is are was were be been am and or but if then than so as it he
    she we they you i me my your his her its our their this that these those there here what
    which who how why when where not yes does did done have has had will would can could should
    may might must shall get got go went le la les un une des el los las y en con del al su sus
    mi tu es son está muy ya muito poco bien well just also too very más
    """.split()
)


def _norm_word(w: str) -> str:
    """Minúsculas sin tildes, para comparar palabras entre sí."""
    nfd = unicodedata.normalize("NFD", w.lower().strip(".,!?¿¡;:'\""))
    return "".join(c for c in nfd if not unicodedata.combining(c))


def _is_function_word(w: str) -> bool:
    return len(w) <= 3 or _norm_word(w) in _FUNC_WORDS


def _pick_target_word(guessed: str, transcript: str) -> str:
    """Elige la palabra de `guessed` que el estudiante intentó decir y destrozó.

    Criterio: palabra de contenido de la frase reparada que NO está (bien dicha)
    en la transcripción pero sí tiene una versión garabateada parecida (ratio
    difflib >= 0.45). Preferimos la coincidencia más clara; desempate por largo
    (las palabras largas son las que valen la pena practicar)."""
    t_words = [_norm_word(t) for t in re.findall(r"[^\W\d_]+", transcript, re.UNICODE)]
    best, best_key = "", (-1.0, 0)
    for w in re.findall(r"[^\W\d_]+", guessed, re.UNICODE):
        lw = _norm_word(w)
        if _is_function_word(lw) or lw in t_words:
            continue
        ratio = max(
            (difflib.SequenceMatcher(None, lw, t).ratio() for t in t_words), default=0.0
        )
        if ratio < 0.45:
            continue
        key = (ratio, len(w))
        if key > best_key:
            best, best_key = w, key
    return best


def _repair_from_context(transcript: str, context: str) -> tuple[str, str] | None:
    """Reparación mínima determinista: alinea la transcripción con el contexto.

    Compara las palabras (normalizadas, sin tildes) de la transcripción con las
    del último mensaje del tutor usando difflib por bloques (opcodes), de modo
    que el orden importe: cada palabra de contenido "casi igual" (0.45 ≤ ratio
    < 1.0) a una del contexto en su misma posición se sustituye por esta — es
    lo que el estudiante intentó pronunciar. Devuelve (frase_reparada,
    ultima_palabra_sustituida) o None si no hay nada que reparar. Nunca inventa
    vocabulario: solo usa palabras que ya dijo el tutor."""
    if not context.strip():
        return None
    t_tokens = re.findall(r"[^\W\d_]+|[^\w]+", transcript, re.UNICODE)
    t_words = [t for t in t_tokens if re.match(r"[^\W\d_]+$", t)]
    t_norm = [_norm_word(w) for w in t_words]
    c_words = re.findall(r"[^\W\d_]+", context, re.UNICODE)
    c_norm = [_norm_word(w) for w in c_words]
    if not t_norm or not c_norm:
        return None

    fixes: dict[int, str] = {}
    assigned: list[tuple[int, int]] = []
    sm = difflib.SequenceMatcher(None, t_norm, c_norm, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag != "replace":
            continue
        # Dentro de cada bloque de sustitución buscamos las mejores parejas
        # fonéticas (los bloques pueden tener tamaños distintos entre ambas
        # frases, por lo que la posición absoluta no basta).
        pairs: list[tuple[float, int, int]] = []
        for i in range(i1, i2):
            lw = t_norm[i]
            if _is_function_word(lw) or len(lw) < 4:
                continue
            for j in range(j1, j2):
                cw = c_norm[j]
                if cw == lw or _is_function_word(cw):
                    continue
                ratio = difflib.SequenceMatcher(None, lw, cw).ratio()
                if 0.45 <= ratio < 1.0:
                    pairs.append((ratio, i, j))
        used_i, used_j = set(), set()
        for _, i, j in sorted(pairs, reverse=True):
            if i in used_i or j in used_j:
                continue
            used_i.add(i)
            used_j.add(j)
            assigned.append((i, j))
    if not assigned:
        return None
    for i, j in sorted(assigned):
        fixes[i] = c_words[j]
        last_fix = c_words[j]
    out: list[str] = []
    wi = 0
    for tok in t_tokens:
        if re.match(r"[^\W\d_]+$", tok):
            out.append(fixes.get(wi, tok))
            wi += 1
        else:
            out.append(tok)
    return "".join(out), last_fix


def _looks_like_context_copy(guessed: str, transcript: str, context: str) -> bool:
    """True si el LLM devolvió (en todo o en parte) el contexto en vez de reparar."""
    if not context.strip() or not guessed.strip():
        return False
    g_words = re.findall(r"[^\W\d_]+", guessed, re.UNICODE)
    if not g_words:
        return False
    ctx_norm = {_norm_word(w) for w in re.findall(r"[^\W\d_]+", context, re.UNICODE)}
    in_ctx = sum(1 for w in g_words if _norm_word(w) in ctx_norm)
    mostly_ctx = in_ctx / len(g_words) >= 0.8
    far_from_t = (
        difflib.SequenceMatcher(
            None, _norm_word(guessed), _norm_word(transcript)
        ).ratio()
        < 0.8
    )
    return mostly_ctx and far_from_t


async def pronunciation_coach(transcript: str, language: str, context: str = "") -> dict:
    """Adivina qué quiso decir el estudiante y da un tip fonético de la palabra.

    Usado por el entrenador de pronunciación: cuando Whisper no entiende, el
    LLM repara la frase y el frontend puede pedirle que repita la palabra
    clave hasta 2 veces antes de continuar la conversación. `context` es el
    último mensaje del tutor: ancla la reparación al vocabulario esperado."""
    lang = _lang_name(language)
    system = build_pronunciation_system(lang)
    user_content = ""
    if context.strip():
        user_content += f"CONTEXT (the tutor just said this): {context.strip()}\n\n"
    user_content += f"TRANSCRIPT to repair: {transcript}"
    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": user_content},
    ]
    try:
        raw = await ask_ollama(messages)
        data = _clean_json(raw)
    except Exception as exc:  # NovaError u otro: el flujo sigue sin coach
        log_info(f"PRON_COACH_ERR {exc}")
        data = {}
    guessed = str(data.get("guessed", "")).strip() or transcript
    if _looks_like_context_copy(guessed, transcript, context):
        log_info("PRON_COACH_CTX_COPY: el LLM devolvió el contexto; rescate determinista")
        data = {}
        guessed = transcript
    target = str(data.get("target_word", "")).strip()
    tip = str(data.get("tip", "")).strip()

    # Evidencia fonética determinista primero: alinear la transcripción con el
    # contexto del tutor (los modelos pequeños se dejan llevar por la semántica).
    aligned = _repair_from_context(transcript, context) if context.strip() else None
    if aligned:
        a_guessed, a_target = aligned
        if (
            target
            and _norm_word(target) != _norm_word(a_target)
            and _norm_word(a_target) not in _norm_word(tip)
        ):
            tip = ""  # el tip era para la palabra del LLM: mejor sin tip que uno equivocado
        if target and _norm_word(target) != _norm_word(a_target):
            log_info(f"PRON_TARGET_ALIGN '{target}' -> '{a_target}'")
        guessed, target = a_guessed, a_target

    n_target = _norm_word(target)
    guessed_words = {_norm_word(w) for w in re.findall(r"[^\W\d_]+", guessed, re.UNICODE)}
    if not target or _is_function_word(n_target) or n_target not in guessed_words:
        fallback = _pick_target_word(guessed, transcript)
        if fallback:
            log_info(f"PRON_TARGET_FIX '{target}' -> '{fallback}'")
            target = fallback
    return {"guessed": guessed, "target_word": target, "tip": tip}


async def resolve_model() -> str:
    """Devuelve el modelo configurado si existe en Ollama; si no, el fallback.

    Evita 503 en instalaciones donde falta un modelo personalizado. El resultado
    se cachea por 30 segundos para evitar HTTP excesivo a /api/tags.
    """
    now = time.monotonic()
    if _MODEL_CACHE["model"] is not None and now - _MODEL_CACHE["ts"] < _MODEL_CACHE_TTL:
        return _MODEL_CACHE["model"]

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(OLLAMA_TAGS_URL)
            resp.raise_for_status()
            names = {m.get("name", "") for m in resp.json().get("models", [])}
    except Exception:
        return MODEL

    result = MODEL
    if MODEL not in names and names:
        for name in names:
            base = name.split(":")[0]
            if MODEL == base or MODEL.startswith(base + ":"):
                break
        else:
            fallback = FALLBACK_MODEL if FALLBACK_MODEL in names else next(iter(names), MODEL)
            if fallback != MODEL:
                log_info(f"MODEL_FALLBACK {MODEL} -> {fallback}")
            result = fallback

    _MODEL_CACHE["model"] = result
    _MODEL_CACHE["ts"] = now
    return result
