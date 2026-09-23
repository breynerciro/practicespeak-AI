import json
import os

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles

from . import config, db
from .access import STREAM_GATE, check_access_code, check_rate_limit, code_ok
from .ai import (
    NovaError,
    check_ollama,
    correct_grammar,
    immersive_chat_stream,
    immersive_continue,
    immersive_start,
    resolve_start_topic,
    tutor_chat,
)
from .log import LOG_BUF, log_info
from .schemas import ChatRequest, GrammarRequest, ImmersiveRequest, ProfileCreate
from .speech import evaluate, transcribe
from .tts import sintetizar

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend", "dist")

# Página de aviso cuando el frontend aún no se ha compilado.
_FRONTEND_FALLBACK_HTML = """<!doctype html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>PracticeSpeak AI · frontend sin compilar</title><style>body{font-family:system-ui,ui-sans-serif,sans-serif;background:#171320;color:#efe9f4;display:grid;place-items:center;min-height:100vh;margin:0;text-align:center}.c{max-width:46ch;padding:24px}.code{font-family:ui-monospace,monospace;background:#241f2c;padding:3px 10px;border-radius:8px}</style></head><body><div class="c"><h1>PracticeSpeak AI</h1><p>El frontend no está compilado. En la carpeta <b>frontend/</b> ejecuta:</p><p class="code">npm install &amp;&amp; npm run build</p><p>y recarga esta página.</p></div></body></html>"""


app = FastAPI(title="PracticeSpeak AI")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

if os.path.isdir(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Devolver 400 con `detail` legible para que el cliente muestre un toast útil."""
    errors = [
        f"{'.'.join(str(loc) for loc in err['loc'][1:]) or 'payload'}: {err['msg']}"
        for err in exc.errors()
    ]
    return JSONResponse(status_code=400, content={"detail": "; ".join(errors)})


@app.middleware("http")
async def redirect_hostname_https(request, call_next):
    host = (request.headers.get("host") or "").lower()
    # Detrás del proxy de Tailscale Funnel la petición llega por HTTP interno
    # pero el visitante ya está en HTTPS: no redirigir en ese caso.
    forwarded = (request.headers.get("x-forwarded-proto") or "").lower()
    if (
        config.PUBLIC_HOSTNAME
        and request.url.scheme != "https"
        and forwarded != "https"
        and host.startswith(config.PUBLIC_HOSTNAME.lower())
    ):
        url = f"https://{host}:{config.HTTPS_PORT}{request.url.path}"
        if request.url.query:
            url += "?" + request.url.query
        return Response(status_code=308, headers={"Location": url})
    return await call_next(request)


@app.middleware("http")
async def cache_static(request, call_next):
    """Cabeceras de caché para estáticos: fuentes e imágenes cambian poco."""
    response = await call_next(request)
    path = request.url.path
    if path.startswith("/static/fonts/"):
        response.headers["Cache-Control"] = "public, max-age=604800, immutable"
    elif path.startswith("/static/") or path == "/":
        response.headers["Cache-Control"] = "public, max-age=3600"
    return response


@app.middleware("http")
async def log_requests(request, call_next):
    path = request.url.path
    if path.startswith("/api/") and path not in ("/api/health", "/api/logs"):
        log_info(f"REQ {request.client.host} {request.method} {path} len={request.headers.get('content-length', '-')}")
    return await call_next(request)


@app.middleware("http")
async def access_code_guard(request, call_next):
    """Puerta compartida: exige el código (cabecera X-Nova-Code o ?code=) en
    /api salvo /api/health. El estático y el service worker quedan abiertos
    para que el navegador pueda cargar la pantalla que pide el código."""
    path = request.url.path
    if path.startswith("/api") and not check_access_code(request):
        headers = {"WWW-Authenticate": "Nova-Code"} if path.startswith("/api/") else None
        return JSONResponse({"detail": "Código de acceso incorrecto."}, status_code=401, headers=headers)
    return await call_next(request)


@app.get("/api/logs")
async def logs(limit: int = 60):
    items = list(LOG_BUF)
    return JSONResponse({"logs": items[-limit:]})


@app.post("/api/log")
async def client_log(payload: dict):
    msg = str(payload.get("msg", ""))[:500]
    log_info(f"NAVEGADOR: {msg}")
    return JSONResponse({"ok": True})


@app.get("/")
async def index():
    path = os.path.join(FRONTEND_DIR, "index.html")
    if os.path.isfile(path):
        return FileResponse(path)
    return Response(_FRONTEND_FALLBACK_HTML, media_type="text/html")


@app.get("/sw.js")
async def service_worker():
    """Service worker de la PWA (alcance raíz para poder instalarla)."""
    path = os.path.join(FRONTEND_DIR, "sw.js")
    if os.path.isfile(path):
        return FileResponse(path, media_type="text/javascript", headers={"Service-Worker-Allowed": "/"})
    return Response("", status_code=404)


CERTS_DIR = os.path.join(BASE_DIR, "certs")


@app.get("/profile.mobileconfig")
async def mobileconfig():
    path = os.path.join(CERTS_DIR, "NovaHTTPS.mobileconfig")
    if not os.path.exists(path):
        return JSONResponse({"error": "Perfil no encontrado"}, status_code=404)
    return FileResponse(path, media_type="application/x-apple-aspen-config", filename="NovaHTTPS.mobileconfig")


@app.get("/ca.der")
async def ca_der():
    path = os.path.join(CERTS_DIR, "ca.der")
    if not os.path.exists(path):
        return JSONResponse({"error": "CA no encontrada"}, status_code=404)
    return FileResponse(path, media_type="application/pkix-cert", filename="ca.der")


@app.get("/api/health")
async def health(request: Request):
    ollama_up = await check_ollama()
    return JSONResponse(
        {
            "ollama": ollama_up,
            "model": config.OLLAMA_MODEL,
            "whisper": config.WHISPER_MODEL_SIZE,
            "ok": ollama_up,
            "public_hostname": config.PUBLIC_HOSTNAME,
            "https_port": config.HTTPS_PORT,
            # Estado de ESTA petición: true = el servidor pide código y el que
            # trae la petición (si trae) no es válido. Health sigue abierto para
            # que el frontend monte la pantalla de acceso y valide contra aquí.
            "needs_code": bool(config.ACCESS_CODE) and not code_ok(request),
        }
    )



@app.get("/api/profiles")
async def profiles():
    return JSONResponse(await run_in_threadpool(db.list_profiles))


@app.post("/api/profiles")
async def create_profile(payload: ProfileCreate):
    try:
        profile_id = await run_in_threadpool(db.create_profile, payload.name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"id": profile_id, "name": payload.name.strip()})


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request):
    if not check_rate_limit(request):
        raise HTTPException(status_code=429, detail="Demasiadas peticiones. Espera un minuto.")
    try:
        result = await tutor_chat(payload.language, [h.model_dump() for h in payload.history], payload.message)
    except NovaError as exc:
        raise HTTPException(status_code=503, detail=f"Modelo local no disponible. {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"PracticeSpeak dio una respuesta inválida. {exc}") from exc
    return JSONResponse(result)


@app.post("/api/immersive")
async def immersive(payload: ImmersiveRequest):
    try:
        if payload.mode == "start":
            topic = payload.topic.strip() or None
            log_info(f"IMMERSIVE start lang={payload.language} topic={topic!r} profile={payload.profile_id}")
            result = await immersive_start(payload.language, topic)
            session_id: int | None = await run_in_threadpool(
                db.start_session, payload.language, result.get("topic"), payload.mode, payload.profile_id
            )
            log_info(f"SESSION start id={session_id}")
            result["session_id"] = session_id
        else:
            text = payload.message.strip()
            log_info(f"IMMERSIVE continue lang={payload.language} user={text!r}")
            result = await immersive_continue(payload.language, [h.model_dump() for h in payload.history], text)
            session_id = payload.session_id
            if session_id:
                saved = await run_in_threadpool(
                    db.save_corrections, session_id, payload.language, result.get("topic"), text, result.get("corrections", [])
                )
                if saved:
                    log_info(f"SESSION corrections saved={saved}")
    except NovaError as exc:
        raise HTTPException(status_code=503, detail=f"Modelo local no disponible. {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"PracticeSpeak dio una respuesta inválida. {exc}") from exc
    if isinstance(result, dict) and "reply" in result:
        log_info(f"IMMERSIVE reply: {result['reply']!r}")
    return JSONResponse(result)


def _sse(data: dict) -> str:
    """Serializa un evento SSE (`data: <json>`); ASCII puro para que el
    cliente no se encuentre bytes UTF-8 directos en la línea."""
    return f"data: {json.dumps(data, ensure_ascii=True)}\n\n"


@app.post("/api/immersive/stream")
async def immersive_stream(payload: ImmersiveRequest):
    """PracticeSpeak responde en streaming (SSE) con el mismo contrato que
    `/api/immersive`, pero entregando cada fragmento mientras se genera:
    `session_id` (solo start), `topic`, `delta`*, `corrections`? y `done`;
    ante un fallo de Ollama se envía un evento `error`. Un semáforo limita
    las conversaciones simultáneas para no saturar la CPU compartida."""

    if not STREAM_GATE.enter():
        return JSONResponse(
            {"detail": "PracticeSpeak está ocupada con otras conversaciones. Prueba en unos segundos."},
            status_code=503,
        )

    async def events():
        try:
            if payload.mode == "start":
                topic = resolve_start_topic(payload.topic)
                log_info(f"IMMERSIVE_STREAM start lang={payload.language} topic={topic!r} profile={payload.profile_id}")
                session_id = await run_in_threadpool(
                    db.start_session, payload.language, topic, payload.mode, payload.profile_id
                )
                log_info(f"SESSION start id={session_id}")
                yield _sse({"type": "session_id", "session_id": session_id})
                done: dict | None = None
                async for ev in immersive_chat_stream("start", payload.language, [], "", topic):
                    if ev["type"] == "done":
                        done = ev
                    yield _sse(ev)
                if done:
                    log_info(f"IMMERSIVE reply: {done['reply']!r}")
            else:
                text = payload.message.strip()
                log_info(f"IMMERSIVE_STREAM continue lang={payload.language} user={text!r}")
                done = None
                topic = ""
                async for ev in immersive_chat_stream(
                    "continue",
                    payload.language,
                    [t.model_dump() for t in payload.history],
                    text,
                ):
                    if ev["type"] == "done":
                        done = ev
                    elif ev["type"] == "topic":
                        topic = ev.get("topic", "")
                    yield _sse(ev)
                if done:
                    log_info(f"IMMERSIVE reply: {done['reply']!r}")
                if payload.session_id and done:
                    saved = await run_in_threadpool(
                        db.save_corrections,
                        payload.session_id,
                        payload.language,
                        topic,
                        text,
                        done.get("corrections", []),
                    )
                    if saved:
                        log_info(f"SESSION corrections saved={saved}")
        except NovaError as exc:
            yield _sse({"type": "error", "detail": f"Modelo local no disponible. {exc}"})
        except ValueError as exc:
            yield _sse({"type": "error", "detail": f"PracticeSpeak dio una respuesta inválida. {exc}"})
        finally:
            STREAM_GATE.leave()

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.post("/api/grammar")
async def grammar(payload: GrammarRequest, request: Request):
    if not check_rate_limit(request):
        raise HTTPException(status_code=429, detail="Demasiadas peticiones. Espera un minuto.")
    try:
        result = await correct_grammar(payload.language, payload.text)
    except NovaError as exc:
        raise HTTPException(status_code=503, detail=f"Modelo local no disponible. {exc}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"PracticeSpeak dio una respuesta inválida. {exc}") from exc
    return JSONResponse(result)


@app.post("/api/audio")
async def audio(
    request: Request,
    audio: UploadFile = File(...),
    expected: str = Form(""),
    language: str = Form("en"),
):
    if not check_rate_limit(request):
        raise HTTPException(status_code=429, detail="Demasiadas peticiones. Espera un minuto.")
    content = await audio.read()
    log_info(f"AUDIO recibido lang={language} bytes={len(content)} expected={expected!r}")
    try:
        # Whisper en CPU es bloqueante: se ejecuta en un threadpool para no
        # congelar el event loop ni bloquear otras peticiones.
        transcript = await run_in_threadpool(transcribe, content, language)
    except Exception as exc:
        log_info(f"TRANSCRIBE_ERR {exc}")
        raise HTTPException(status_code=500, detail="Error transcribiendo el audio.") from exc
    log_info(f"TRANSCRIPCIÓN ({language}): {transcript!r}")
    result = evaluate(expected, transcript, language)
    return JSONResponse(result)


@app.get("/api/stats")
async def stats_endpoint(profile_id: int | None = None):
    return JSONResponse(await run_in_threadpool(db.stats, profile_id))


@app.get("/api/export/anki")
async def export_anki(profile_id: int | None = None):
    csv_data = await run_in_threadpool(db.export_anki_csv, profile_id)
    return Response(
        content=csv_data,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="nova-corrections-anki.csv"'},
    )


@app.post("/api/session/finish")
async def session_finish(payload: dict):
    session_id = payload.get("session_id")
    if isinstance(session_id, int):
        await run_in_threadpool(db.finish_session, session_id)
    return JSONResponse({"ok": True})


@app.get("/api/tts/voices")
async def tts_voices(lang: str = ""):
    """Voces disponibles para elegir en los ajustes: las locales (piper) y las
    de nube (edge) por idioma. No depende de Ollama ni de internet."""
    from .tts import list_voices

    if lang:
        return JSONResponse({"lang": lang, "voices": list_voices(lang)})
    return JSONResponse({"voices": {code: list_voices(code) for code in config.SUPPORTED_LANGUAGES}})


@app.get("/api/tts")
async def tts(request: Request, text: str, lang: str = "en", gender: str = "female", voice: str = "", speed: float = 1.0):
    if not check_rate_limit(request):
        raise HTTPException(status_code=429, detail="Demasiadas peticiones. Espera un minuto.")
    log_info(f"TTS lang={lang} gender={gender} voice={voice or '-'} speed={speed:g} texto={text!r}")
    try:
        data = await sintetizar(text, lang, gender, voice, speed)
        # piper genera WAV; edge-tts genera MP3. El navegador lo detecta solo,
        # pero se anuncia el tipo correcto por si acaso.
        media = "audio/wav" if data.startswith(b"RIFF") else "audio/mpeg"
        return Response(content=data, media_type=media)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"TTS failed (needs internet). {exc}") from exc
