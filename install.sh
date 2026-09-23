#!/usr/bin/env bash
# PracticeSpeak AI — instalador de un solo paso (pensado para quien no sabe de computadores)
# Uso:  bash install.sh
set -euo pipefail
cd "$(dirname "$0")"

say()  { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
ok()   { printf '\033[1;32m ✓\033[0m %s\n' "$*"; }
fail() { printf '\033[1;31m✗\033[0m %s\n' "$*"; exit 1; }

say "Bienvenido a la instalación de PracticeSpeak AI (tutor de idiomas local)"

# --- 1. Dependencias del sistema -------------------------------------------
if ! command -v python3 >/dev/null; then
  fail "Necesitas Python 3.10+. En Ubuntu/Debian: sudo apt install python3 python3-venv"
fi
ok "Python encontrado"

if ! command -v ffmpeg >/dev/null; then
  say "Instalando ffmpeg (necesario para el micrófono)…"
  if command -v apt-get >/dev/null; then
    sudo apt-get install -y ffmpeg || fail "Instala ffmpeg manualmente"
  else
    fail "Instala ffmpeg manualmente y vuelve a ejecutar"
  fi
else
  ok "ffmpeg encontrado"
fi

# --- 2. Ollama ---------------------------------------------------------------
if ! command -v ollama >/dev/null && [ ! -x "$HOME/.local/bin/ollama" ]; then
  say "Instalando Ollama (el motor de IA, ~1 GB de descarga)…"
  curl -fsSL https://ollama.com/install.sh | sh || fail "No se pudo instalar Ollama"
fi
ok "Ollama disponible"
OLLAMA_BIN="$(command -v ollama || echo "$HOME/.local/bin/ollama")"

# --- 3. Perfil según la RAM del PC ------------------------------------------
RAM_GB=$(awk '/MemTotal/ {print int($2/1024/1024)}' /proc/meminfo)
if [ "$RAM_GB" -lt 10 ]; then
  MODEL="qwen3:1.7b"
  say "Tu PC tiene ${RAM_GB} GB de RAM: usaremos el modelo ligero ($MODEL)"
else
  MODEL="qwen3:4b"
  say "Tu PC tiene ${RAM_GB} GB de RAM: usaremos el modelo completo ($MODEL)"
fi

if [ ! -d ".venv" ]; then
  say "Preparando el entorno de PracticeSpeak AI (unos minutos)…"
  python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt
ok "Programas de PracticeSpeak AI instalados"

say "Descargando el modelo de IA ($MODEL, una sola vez)…"
if ! "$OLLAMA_BIN" list 2>/dev/null | grep -q "$MODEL"; then
  "$OLLAMA_BIN" pull "$MODEL"
fi
ok "Modelo listo"

# --- 4. Lanzador en el escritorio -------------------------------------------
mkdir -p /tmp/nova
DESKTOP="$HOME/Desktop"
[ -d "$DESKTOP" ] || DESKTOP="$HOME/Escritorio"
if [ -d "$DESKTOP" ]; then
  cat > "$DESKTOP/nova-tutor.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=PracticeSpeak AI
Comment=Tutor de idiomas local
Exec=$PWD/run.sh start
Icon=audio-input-microphone
Terminal=true
EOF
  chmod +x "$DESKTOP/nova-tutor.desktop"
  ok "Icono 'PracticeSpeak AI' creado en tu escritorio"
fi

cat > "$PWD/nova" <<EOF
#!/usr/bin/env bash
exec "$PWD/run.sh" "\$@"
EOF
chmod +x "$PWD/nova"

cat <<EOF

=========================================================
  ¡Listo! Para usar PracticeSpeak AI:
    1. Doble clic en el icono "PracticeSpeak AI" del escritorio
       (o ejecuta:  ./nova start  en una terminal)
    2. En tu celular, escanea el código QR que aparecerá
    3. Elige un tema y empieza a hablar o escribir

  Otros comandos:  ./nova status   ./nova stop
=========================================================
EOF
