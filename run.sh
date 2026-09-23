#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

# Carga .env (líneas KEY=VALUE) sin pisar variables ya exportadas
if [ -f .env ]; then
  while IFS= read -r line; do
    line="${line%$'\r'}"
    case "$line" in ''|\#*) continue ;; esac
    k="${line%%=*}"; v="${line#*=}"
    k="$(printf '%s' "$k" | tr -d '[:space:]')"
    v="${v%\"}"; v="${v#\"}"; v="${v%\'}"; v="${v#\'}"
    [ -n "$k" ] && [ -n "$v" ] && [ -z "${!k+x}" ] && export "$k=$v"
  done < .env
fi

OLLAMA_BIN="${NOVA_OLLAMA_BIN:-$HOME/.local/bin/ollama}"
PORT="${NOVA_PORT:-8000}"
PORT_HTTPS="${NOVA_HTTPS_PORT:-8443}"
PUBLIC_HOST="${NOVA_PUBLIC_HOSTNAME:-nova-tutor}"
RAM_GB=$(awk '/MemTotal/ {print int($2/1024/1024)}' /proc/meminfo 2>/dev/null || echo 16)
if [ "${NOVA_PROFILE:-}" = "low" ] || { [ -z "${NOVA_PROFILE:-}" ] && [ "$RAM_GB" -lt 10 ]; }; then
  DEFAULT_MODEL="qwen3:1.7b"
  export NOVA_PROFILE=low
else
  DEFAULT_MODEL="qwen3:4b"
fi
OLLAMA_MODEL="${NOVA_OLLAMA_MODEL:-$DEFAULT_MODEL}"

if [ ! -x .venv/bin/uvicorn ]; then
  echo "Creando entorno virtual…"
  python3 -m venv .venv
  .venv/bin/pip install -r requirements.txt
fi

LOG_DIR="${NOVA_LOG_DIR:-/tmp/nova}"
mkdir -p "$LOG_DIR"

is_ollama() { curl -s --max-time 2 "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; }
is_app() { curl -s "http://127.0.0.1:$PORT/api/health" >/dev/null 2>&1; }

build_frontend() {
  local dist="frontend/dist/index.html"
  local stale=""
  if [ ! -f "$dist" ]; then
    stale=1
  elif [ -n "$(find frontend/index.html frontend/package.json frontend/vite.config.ts frontend/src frontend/public -type f -newer "$dist" 2>/dev/null | head -1)" ]; then
    stale=1
  fi
  if [ -n "$stale" ]; then
    echo "🛠  Compilando el frontend (frontend/dist)…"
    if [ ! -d frontend/node_modules ]; then
      (cd frontend && npm ci)
    fi
    (cd frontend && npm run build)
  fi
}

TS_BIN="$HOME/.local/bin/tailscale"
TS_SOCK=/tmp/tailscaled.sock
is_ts() { systemctl --user is-active --quiet tailscaled; }
ts_ip() { "$TS_BIN" --socket="$TS_SOCK" ip -4 2>/dev/null | head -1; }

ts_up() {
  if ! is_ts; then
    systemctl --user start tailscaled
    sleep 2
  fi
  if "$TS_BIN" --socket="$TS_SOCK" status >/dev/null 2>&1; then
    echo "✅ Tailscale: conectado (IP: $(ts_ip))"
  else
    echo "🌐 Primera vez: abre este enlace en el navegador para autorizar:"
    setsid -f bash -c '"$0" --socket="$1" up --hostname=nova-tutor' "$TS_BIN" "$TS_SOCK" >>"$LOG_DIR"/tailscaled-up.log 2>&1 &
    sleep 3
    grep -oE "https://login\.tailscale\.com/a/[a-f0-9]+" "$LOG_DIR"/tailscaled-up.log 2>/dev/null | tail -1
  fi
}

lan_ip() {
  ip -4 addr show scope global 2>/dev/null | grep -oP '(?<=inet\s)\d+\.\d+\.\d+\.\d+' | grep -v '^172\.' | head -1
}

FUNNEL_URL_FILE="$LOG_DIR/funnel_url"

ts_dns_name() {
  "$TS_BIN" --socket="$TS_SOCK" status --json 2>/dev/null | .venv/bin/python -c '
import json, sys
try:
    print(json.load(sys.stdin)["Self"]["DNSName"].rstrip("."))
except Exception:
    pass' 2>/dev/null
}

funnel() {
  # Abre PracticeSpeak AI a internet con Tailscale Funnel (HTTPS público, sin abrir
  # puertos del router). Requiere Tailscale instalado y sesión iniciada.
  local action="${1:-status}"
  if ! is_ts; then
    systemctl --user start tailscaled 2>/dev/null || true
    sleep 2
  fi
  case "$action" in
    on|start)
      if ! is_app; then
        echo "❌ PracticeSpeak AI no está corriendo: arranca antes con $0 start" >&2
        return 1
      fi
      echo "🌐 Abriendo PracticeSpeak AI a internet con Tailscale Funnel…"
      if "$TS_BIN" --socket="$TS_SOCK" funnel --bg --https=443 "http://127.0.0.1:$PORT" 2>&1; then
        local host
        host="$(ts_dns_name)"
        if [ -n "$host" ]; then
          echo "✅ URL pública (compártela con tus amigos): https://$host"
          mkdir -p "$LOG_DIR"
          echo "https://$host" > "$FUNNEL_URL_FILE"
        fi
      else
        echo "❌ No se pudo activar el funnel (mira 'tailscale funnel status')."
      fi
      ;;
    off|stop)
      "$TS_BIN" --socket="$TS_SOCK" funnel off 2>/dev/null || true
      rm -f "$FUNNEL_URL_FILE"
      echo "🛑 Funnel cerrado: tu URL pública ya no responde."
      ;;
    *)
      "$TS_BIN" --socket="$TS_SOCK" funnel status 2>&1 || echo "Funnel inactivo."
      [ -f "$FUNNEL_URL_FILE" ] && echo "🌍 URL pública: $(cat "$FUNNEL_URL_FILE")"
      ;;
  esac
}

show_url() {
  local ip url tip
  ip="$(lan_ip)"
  url="http://${ip}:${PORT}"
  echo
  echo "📱 En tu red WiFi: ${url}"
  tip="$(ts_ip)"
  if [ -n "$tip" ]; then
    if [ -s certs/tailscale.crt ]; then
      url="https://${PUBLIC_HOST}.taile42733.ts.net:${PORT_HTTPS}"
      echo "📱 🔒 URL para el iPhone (HTTPS con micrófono): ${url}"
      echo "   Directa por IP (sin nombre): https://${tip}:${PORT_HTTPS}"
    else
      echo "🌐 Por Tailscale: http://${tip}:${PORT}"
      url="http://${tip}:${PORT}"
    fi
  fi
  if [ -f "$FUNNEL_URL_FILE" ]; then
    echo "🌍 URL pública (fuera de casa): $(cat "$FUNNEL_URL_FILE")"
  fi
  if [ -x .venv/bin/python ]; then
    if .venv/bin/python -c "import qrcode" >/dev/null 2>&1; then
      echo "   O escanea este código QR:"
      .venv/bin/python - "$url" <<'PY'
import sys
import qrcode
url = sys.argv[1]
qr = qrcode.QRCode(border=1)
qr.add_data(url)
qr.make()
qr.print_ascii(invert=True)
print("        " + url)
PY
    fi
  fi
}

start() {
  build_frontend

  if is_ollama; then
    echo "✅ Ollama ya estaba corriendo"
  elif [ -x "$OLLAMA_BIN" ]; then
    nohup env OLLAMA_HOST=127.0.0.1:11434 OLLAMA_KEEP_ALIVE=30m "$OLLAMA_BIN" serve >>"$LOG_DIR"/ollama.log 2>&1 &
    echo "🚀 Ollama iniciado"
  else
    echo "❌ No encuentro ollama en $OLLAMA_BIN" >&2
    return 1
  fi

  # Arranque en frío: espera (máx 30 s) a que Ollama acepte conexiones
  for _ in $(seq 1 30); do
    is_ollama && break
    sleep 1
  done
  if ! is_ollama; then
    echo "❌ Ollama no responde (mira $LOG_DIR/ollama.log)" >&2
    return 1
  fi

  if ! "$OLLAMA_BIN" list 2>/dev/null | grep -q "$OLLAMA_MODEL"; then
    echo "📥 Descargando el modelo de IA ($OLLAMA_MODEL, solo la primera vez)…"
    "$OLLAMA_BIN" pull "$OLLAMA_MODEL"
  fi

  if is_app; then
    echo "✅ PracticeSpeak AI ya estaba corriendo"
  else
    nohup .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port "$PORT" >>"$LOG_DIR"/tutor.log 2>&1 &
    echo "🚀 PracticeSpeak AI iniciado (http)"
  fi

  if curl -skf "https://127.0.0.1:$PORT_HTTPS/api/health" >/dev/null 2>&1; then
    echo "✅ PracticeSpeak AI HTTPS ya estaba corriendo"
  else
    local scrt scert skey
    scrt="certs/tailscale.crt"
    skey="certs/tailscale.key"
    if [ ! -s "$scrt" ] || [ ! -s "$skey" ]; then
      scrt="certs/server.pem"
      skey="certs/server.key"
    fi
    nohup .venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port "$PORT_HTTPS" \
      --ssl-certfile "$scrt" --ssl-keyfile "$skey" \
      >>"$LOG_DIR"/tutor.log 2>&1 &
    echo "🚀 PracticeSpeak AI iniciado (https :$PORT_HTTPS con $(basename "$scrt"))"
  fi

  ts_up
  show_url
  echo "   O localmente: http://127.0.0.1:$PORT"
  case "${NOVA_FUNNEL:-}" in
    on|1|true) funnel on ;;
  esac
}

stop() {
  pkill -f "uvicorn backend.main:app" && echo "🛑 PracticeSpeak AI detenido" || echo "PracticeSpeak AI ya estaba detenido"
  pkill -f "$OLLAMA_BIN serve" && echo "🛑 Ollama detenido" || echo "Ollama ya estaba detenido"
  systemctl --user stop tailscaled 2>/dev/null && echo "🛑 Tailscale detenido" || echo "Tailscale ya estaba detenido"
}

status() {
  [ "$(is_ollama && echo 1 || echo 0)" = "1" ] && echo "✅ Ollama: corriendo" || echo "❌ Ollama: detenido"
  [ "$(is_app && echo 1 || echo 0)" = "1" ] && echo "✅ PracticeSpeak AI: corriendo" || echo "❌ PracticeSpeak AI: detenido"
  curl -skf "https://127.0.0.1:$PORT_HTTPS/api/health" >/dev/null 2>&1 && echo "✅ PracticeSpeak AI HTTPS (:8443): corriendo" || echo "❌ PracticeSpeak AI HTTPS (:8443): detenido"
  if is_ts; then
    if "$TS_BIN" --socket="$TS_SOCK" status >/dev/null 2>&1; then
      echo "✅ Tailscale: conectado (IP: $(ts_ip))"
    else
      echo "🌐 Tailscale: sin autorizar (mirar el enlace de $0 start)"
    fi
  else
    echo "❌ Tailscale: detenido"
  fi
  if is_app; then show_url; fi
}

case "${1:-start}" in
  start) start ;;
  stop) stop ;;
  restart) stop; sleep 2; start ;;
  status) status ;;
  funnel) funnel "${2:-status}" ;;
  *) echo "Uso: $0 {start|stop|restart|status|funnel [on|off|status]}"; exit 1 ;;
esac