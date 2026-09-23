# Nova — Local Voice & Text Language Tutor

Practice **English, Portuguese, French, German, Italian** by voice *or* text with an ai tutor that runs
100% on your own machine. nova keeps the conversation going, corrects your mistakes
in real time (with explanations in spanish), and never sends your data anywhere.

![python](https://img.shields.io/badge/python-3.10%2b-3776ab?logo=python&logocolor=white)
![fastapi](https://img.shields.io/badge/fastapi-009688?logo=fastapi&logocolor=white)
![svelte](https://img.shields.io/badge/svelte-5-ff4c26?logo=svelte&logocolor=white)
![tests](https://img.shields.io/badge/tests-296%20passed-brightgreen)
![coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)
![lighthouse](https://img.shields.io/badge/lighthouse-a11y%20100%20%c2%b7%20perf%20100-24b47e?logo=lighthouse&logocolor=white)
![License](https://img.shields.io/badge/license-MIT-blue)

## Why Nova?

| | |
|---|---|
| 🎙️ **Inmersivo por voz** | Habla natural; el VAD detecta cuando terminas y envía solo. Whisper (local) transcribe, piper (local) responde sin gastar internet. |
| 🗣️ **Elige la voz de Nova** | En ajustes: una voz local o de nube concreta por idioma (con muestra audible), o "Auto" según tu género favorito. |
| ⚡ **Interrumpe a Nova** | Habla por encima (o toca el orbe) para cortarla a mitad de frase y tomar la palabra; ajusta la velocidad de su voz (lenta→turbo) y la sensibilidad del micrófono. |
| ⌨️ **Modo texto** | Practica escrita sin micrófono. Correcciones persistentes como tarjetas. |
| ⚡ **Respuestas en streaming** | Nova escribe mientras piensa y **habla frase a frase** en cuanto se completa, sin esperar a terminar. |
| 📝 **Correcciones en vivo** | Cada fallo se convierte en tarjeta: qué dijiste → cómo es → la regla, explicada en español. |
| ✍️ **Corrector de textos** | Pega o escribe una frase suelta y Nova la corrige y explica, sin iniciar conversación. |
| 🎯 **20 temas, siempre frescos** | Selector aleatorio que evita repetir tus últimas sesiones. |
| 🌓 **Tema dual** | Claro/oscuro automático (con override), glassmorphism, iconos SVG estilo Lucide. |
| 📲 **PWA instalable** | Añádela al menú del teléfono; el service worker da shell offline tras la primera visita. |
| 🔒 **100% local** | LLM (Ollama), speech-to-text (faster-whisper) y castellano TTS (piper) corren en tu máquina. |

## Architecture

```mermaid
flowchart LR
    subgraph Phone["📱 Teléfono / Navegador (PWA)"]
        UI["SPA Svelte 5\nstreaming + service worker"]
    end
    subgraph Server["🖥️ Tu máquina — FastAPI"]
        API["backend/main.py\nREST + SSE"]
        AI["backend/ai.py\nprompts + reparación JSON + streaming"]
        SP["backend/speech.py\nfaster-whisper (int8, CPU)"]
        DB["backend/db.py\nSQLite: sesiones y correcciones"]
    end
    O["🦙 Ollama\nqwen3:4b"]
    T["backend/tts.py\npiper local + fallback edge-tts"]

    UI <-->|HTTPS + getUserMedia + SSE| API
    API --> AI --> O
    API --> SP
    API --> DB
    API --> T
```

- **Backend**: FastAPI, payloads validados con Pydantic, errores tipados (`503` modelo caído,
  `502` salida malformada), respuestas de Nova por **SSE en streaming** y Whisper en un
  threadpool para no bloquear el event loop.
- **Frontend**: SPA en **Svelte 5** (runes) + Vite, iconos SVG propios, WCAG 2.2 AA
  (skip link, foco visible, focus trap en diálogos, live regions, reduced-motion, 4.5:1+ contraste).
- **TTS**: por defecto **piper** (local, solo CPU, descarga la voz a la primera) con caída a
  edge-tts si no hay voz instalada ni internet (`NOVA_TTS_BACKEND=piper`). El selector de
  ajustes lista las voces locales instaladas y disponibles más un catálogo de edge por idioma
  (`GET /api/tts/voices`); la elegida viaja en `/api/tts?voice=...`.
- **Idiomas**: inglés, portugués, francés, alemán, italiano, **español, ruso y chino (mandarín)** —
  todos con voces piper (descarga bajo demanda) y edge. El LLM adapta prompts, correcciones y
  la transcripción Whisper por idioma.

## Quickstart (one command)

Requirements: Linux (Debian/Ubuntu for the auto-installer), `curl` and internet for the first setup.

```bash
bash install.sh
```

That's it. The installer prepares everything (Ollama, AI model, dependencies) and puts a
**"Nova Tutor" icon on your desktop**. Double-click it, scan the QR with your phone and start practicing.

### Low-end PCs (8 GB RAM, no GPU)

Nova **auto-detects your hardware**: with less than 10 GB of RAM it switches to a smaller
LLM (`qwen3:1.7b`), a lighter Whisper (`base`) and shorter replies, so a 2015 i5 with 8 GB
runs it comfortably. Force it with `NOVA_PROFILE=low` or `NOVA_PROFILE=high`.

<details>
<summary><b>Manual setup</b> (if you prefer)</summary>

Requirements: Linux/macOS, Python 3.10+, [Ollama](https://ollama.com), `ffmpeg`.

```bash
ollama pull qwen3:4b          # or qwen3:1.7b on 8 GB machines
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./run.sh start                # QR code included
./run.sh status | stop | restart
```
</details>

Open `http://<your-lan-ip>:8000` — for microphone access use the HTTPS URL printed
by `run.sh` (browsers only grant `getUserMedia` on secure contexts).

<details>
<summary><b>Docker</b> (no local Python needed)</summary>

```bash
docker compose up --build
# app on :8000, Ollama on :11434 — pull the model once:
docker compose exec ollama ollama pull qwen3:4b
```
</details>

### Configuration

Copy `.env.example` to `.env` (or export the vars). Highlights:

| Variable | Default | Purpose |
|---|---|---|
| `NOVA_OLLAMA_MODEL` | `qwen3:4b` | Any Ollama chat model |
| `NOVA_WHISPER_MODEL` | `small` | tiny/base/small/medium/large-v3 |
| `NOVA_TTS_BACKEND` | `edge` | `piper` = voz local (solo CPU) o `edge` (necesita red) |
| `NOVA_PIPER_HOME` | `~/.local/share/nova/piper` | Where piper caches voice models |
| `NOVA_PUBLIC_HOSTNAME` | *(empty)* | Public HTTPS host used for the HTTP→HTTPS redirect |

## Development

```bash
make test    # pytest with coverage gate (fail-under 95)
make lint    # ruff + mypy
make dev     # uvicorn --reload
```

## Trucos

- **Corregir un texto suelto**: bajo la conversación está el botón *Corregir texto* — escribe (o pega)
  una frase y Nova la corrige y explica, sin iniciar una sesión.
- **Cortar mientras Nova habla**: el TTS va **por frases** en streaming: si tocas el orbe durante su
  respuesta la interrumpes y empiezas a hablar tú (aunque a veces querrás esperar a que termine).
- **Instalar como app (PWA)**: en el navegador del teléfono, menú → *Añadir a pantalla de inicio*.
  Tras la primera visita el service worker permite abrir Nova sin conexión (voz y LLM seguirán
  necesitando el servidor).

## Compartir Nova con amigos (URL pública)

Nova puede abrirse a internet para que tus amigos practiquen desde cualquier
red con una URL https fija, **sin abrir puertos del router**:

```bash
./run.sh start          # arranca Nova + Ollama
./run.sh funnel on      # publica https://<tu-host>.ts.net (Tailscale Funnel)
./run.sh funnel status  # muestra la URL pública
./run.sh funnel off     # cierra el acceso cuando quieras
```

Comparte la URL y el código de acceso por un canal privado (WhatsApp, etc.).

Para proteger tu CPU y tus datos, define antes en `.env`:

```ini
NOVA_ACCESS_CODE=nova2026        # código compartido que pedirán a tus amigos
NOVA_MAX_CONCURRENT_STREAMS=2    # conversaciones a la vez (protege la CPU)
NOVA_RATE_LIMIT_PER_MINUTE=30    # peticiones por IP y minuto en endpoints caros
```

Cuando el servidor tiene `NOVA_ACCESS_CODE`, los navegadores muestran una
pantalla pidiendo el código antes de usar la API (se recuerda en el
dispositivo; también se puede pasar en la URL como `?code=…`). `/api/health`
queda abierta a propósito para poder comprobar el estado sin credenciales.

Alternativas al Funnel: **cloudflared** (túnel gratuito, tu propio dominio) o
**Caddy** como proxy inverso con tu dominio y puertos abiertos.

> Datos: la base SQLite vive ahora en `~/.local/share/nova/nova.db`
> (`NOVA_DATA_DIR`), fuera de `/tmp`, para que el progreso de tus amigos
> sobreviva a los reinicios. Las instalaciones antiguas se migran solas.

### En Docker

Las mismas variables van en `docker-compose.yml` (`NOVA_ACCESS_CODE`, etc.) y
la base persiste en el volumen `nova-data`.

## HTTPS for the microphone

`getUserMedia` requires a secure context. Options:

1. **Tailscale Funnel** (recommended for sharing): `./run.sh funnel on` — public HTTPS, no port forwarding.
2. **Tailscale + MagicDNS certs** (LAN only): `tailscale cert` → mount in `certs/`.
3. **Caddy** reverse proxy with your own domain.
4. **cloudflared** tunnel (free, no port forwarding).

## Project layout

```
backend/
  main.py      # FastAPI app, endpoints, SSE streaming, error handling
  ai.py        # Ollama client, prompts, JSON repair, topic picker
  schemas.py   # Pydantic request models
  speech.py    # Whisper transcription + pronunciation scoring
  tts.py       # piper (local) + edge-tts fallback synthesis
  db.py        # SQLite persistence (sessions, corrections, stats)
  config.py    # Environment-based settings
  tests/       # 250 tests, no network required
frontend/      # SPA Svelte 5 + Vite (npm run build → dist/ served by FastAPI)
  src/         # components, stores and styles (app.css)
  public/      # PWA: manifest, icons, service worker (sw.js)
  dist/        # production build (generated, not committed)
run.sh         # start/stop/status with QR code
```

## License

[MIT](LICENSE) · Icons: [Lucide](https://lucide.dev) (ISC)
