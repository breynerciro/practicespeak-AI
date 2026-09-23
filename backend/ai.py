import json
import random
import re

import httpx

from . import config
from .log import log_info

OLLAMA_URL = config.OLLAMA_BASE_URL + "/api/chat"
OLLAMA_TAGS_URL = config.OLLAMA_BASE_URL + "/api/tags"
MODEL = config.OLLAMA_MODEL
OLLAMA_TIMEOUT = config.OLLAMA_TIMEOUT
# Modelo al que caer si el configurado no existe en Ollama (p. ej. un modelo
# personalizado creado con `ollama create` que falta en una instalación nueva).
FALLBACK_MODEL = config.os.environ.get("NOVA_OLLAMA_FALLBACK_MODEL", "qwen3:1.7b")


class NovaError(RuntimeError):
    """Error al comunicarse con Ollama (modelo local no disponible o respuesta inesperada)."""

SYSTEM_TEMPLATE = """You are an AI language tutor for __LANG__. You help the user practice and learn __LANG__.

Rules:
- The user's mother tongue is Spanish. Explain concepts in Spanish when needed.
- Always respond as a helpful, encouraging tutor.
- __MODE__
- When correcting, be precise but kind. Explain the rule briefly.
- Respond ONLY with valid JSON, no extra text."""

MODE_SPECIFIC = {
    "conversation": """- Carry a natural conversation in __LANG__.
- After replying, if the user made mistakes in their last message, list corrections.
- Reply JSON format:
  {"reply": "your natural reply in __LANG__", "corrections": [{"error": "text with the mistake", "correction": "correct version", "explanation": "brief rule in Spanish"}]}
- If there are no mistakes, corrections must be an empty array.""",
    "grammar": """- Correct the user's text.
- Reply JSON format:
  {"corrected": "the fully corrected text", "errors": [{"error": "part with mistake", "correction": "fixed part", "explanation": "brief rule in Spanish"}], "summary": "short summary in Spanish"}
- If the text has no errors, corrected equals the input and errors is empty.""",
}

IMMERSIVE_SYSTEM = """You are NOVA, a warm and encouraging voice language tutor for __LANG__. The student's mother tongue is Spanish. You practice with them ONLY by voice. Your name is Nova. In your FIRST message of a session you must greet the student by saying something like "Hi! I'm Nova, your language tutor" (in __LANG__).

Rules:
- Always speak in __LANG__, at an B1-C1 level: short, clear, natural sentences.
- ALWAYS end your reply with ONE follow-up question so the conversation keeps going.
- NEVER repeat a question you already asked in this conversation, and never rephrase one you already asked. Each follow-up must explore a NEW angle: a detail, a reason, a personal story, a comparison, or a hypothetical.
- React FIRST to what the student just said (be warm, curious, surprised, or sympathetic) before asking anything new. Reference a specific word or idea they used.
- Every 2-3 exchanges on one point, move the conversation to a related new sub-topic instead of circling the same idea.
- Vary your openers: never start two consecutive replies with the same words or the same pattern.
- If the student makes mistakes in their last message, correct them in real time with a kind, brief explanation in Spanish.
- If the student hesitates or goes off-topic, gently encourage them and steer back to the topic.
- Keep every reply SHORT: 1-3 sentences plus your question.
- Respond ONLY with valid JSON, no extra text:
  {"topic": "the current topic", "reply": "your words in __LANG__", "corrections": [{"error": "...", "correction": "...", "explanation": "brief rule in Spanish"}]}
- corrections must be an empty array if the student made no mistakes."""

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

# Temas usados recientemente (los últimos N de las sesiones) para no repetirlos.
RECENT_TOPICS: list[str] = []
RECENT_TOPICS_MAX = 6


def pick_topic() -> str:
    """Elige un tema al azar evitando los últimos usados; si todos están
    quemados, saca de la lista completa."""
    available = [t for t in TOPICS if t not in RECENT_TOPICS]
    if not available:
        available = TOPICS[:]
    topic = random.choice(available)
    RECENT_TOPICS.append(topic)
    if len(RECENT_TOPICS) > RECENT_TOPICS_MAX:
        del RECENT_TOPICS[:-RECENT_TOPICS_MAX]
    return topic


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
    """Preguntas que Nova ya hizo en esta conversación (normalizadas y sin duplicados).

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
    system = (
        SYSTEM_TEMPLATE.replace("__LANG__", lang)
        .replace("__MODE__", MODE_SPECIFIC[mode].replace("__LANG__", lang))
    )
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
    emitir deltas progresivos del texto de Nova sin esperar al JSON entero.
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
    system = IMMERSIVE_SYSTEM.replace("__LANG__", lang)
    if topic:
        user_msg = (
            f"BEGIN a new immersive session. The student suggested this topic: '{topic}'.\n"
            f"Greet the student briefly and ask your first engaging question about '{topic}' in {lang}. Keep it short."
        )
    else:
        chosen = pick_topic()
        log_info(f"TOPIC_ELEGIDO: {chosen}")
        topic = chosen
        user_msg = (
            f"BEGIN a new immersive session. The topic for this session is '{chosen}'.\n"
            f"Talk ONLY about '{chosen}'; do not pick a different topic.\n"
            f"Greet the student briefly and ask your first engaging question about '{chosen}' in {lang}. Keep it short."
        )
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
    system = IMMERSIVE_SYSTEM.replace("__LANG__", lang)
    msgs = [{"role": "system", "content": system}]
    for h in history[-12:]:
        if h.get("role") in ("user", "assistant"):
            msgs.append({"role": h["role"], "content": h["content"]})
    user_content = f"The student said (voice transcription): {user_text}"
    asked = _previous_questions(history)
    if asked:
        asked_block = "\n".join(f"- {q}" for q in asked[-8:])
        user_content += (
            "\n\nQuestions you ALREADY asked in this conversation (do NOT repeat them "
            "and do NOT rephrase them; ask something NEW that explores a different angle):\n"
            f"{asked_block}"
        )
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
    system = IMMERSIVE_SYSTEM.replace("__LANG__", lang)
    if mode == "start":
        chosen = resolve_start_topic(topic)
        yield {"type": "topic", "topic": chosen}
        user_msg = (
            f"BEGIN a new immersive session. The topic for this session is '{chosen}'.\n"
            f"Talk ONLY about '{chosen}'; do not pick a different topic.\n"
            f"Greet the student briefly and ask your first engaging question about '{chosen}' in {lang}. Keep it short."
        )
        msgs = [{"role": "system", "content": system}, {"role": "user", "content": user_msg}]
    else:
        msgs = [{"role": "system", "content": system}]
        for turn in history[-12:]:
            if turn.get("role") in ("user", "assistant"):
                msgs.append({"role": turn["role"], "content": turn["content"]})
        content = f"The student said (voice transcription): {user_text}"
        asked = _previous_questions(history)
        if asked:
            asked_block = "\n".join(f"- {q}" for q in asked[-8:])
            content += (
                "\n\nQuestions you ALREADY asked in this conversation (do NOT repeat them "
                "and do NOT rephrase them; ask something NEW that explores a different angle):\n"
                f"{asked_block}"
            )
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


async def resolve_model() -> str:
    """Devuelve el modelo configurado si existe en Ollama; si no, el fallback.

    Evita 503 en instalaciones donde falta un modelo personalizado. Muy barata:
    una petición GET local a /api/tags (sin generar tokens)."""
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(OLLAMA_TAGS_URL)
            resp.raise_for_status()
            names = {m.get("name", "") for m in resp.json().get("models", [])}
    except Exception:
        return MODEL
    if MODEL in names or not names:
        return MODEL
    for name in names:
        base = name.split(":")[0]
        if MODEL == base or MODEL.startswith(base + ":"):
            return MODEL
    fallback = FALLBACK_MODEL if FALLBACK_MODEL in names else next(iter(names), MODEL)
    if fallback != MODEL:
        log_info(f"MODEL_FALLBACK {MODEL} -> {fallback}")
    return fallback
