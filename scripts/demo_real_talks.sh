#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# 🧉 CharlaViva · prueba con charlas REALES de Nerdearla + Gemini Live
#
#   export GEMINI_API_KEY="tu-key"     # https://aistudio.google.com/apikey
#   ./scripts/demo_real_talks.sh
#
# Descarga el audio de 3 charlas de YouTube, levanta CharlaViva con el motor
# Gemini y crea una sesión por charla (subtítulos en vivo EN↔ES / ES↔EN).
#
# Variables opcionales:
#   PORT=8000     puerto del servidor
#   SPEED=1.0     velocidad de reproducción (>1 p/ pruebas rápidas, ej: 3)
#   OUTPUTS=es,en idiomas de salida por sesión
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail
cd "$(dirname "$0")/.."

: "${GEMINI_API_KEY:?⚠️  Exportá la API key primero:  export GEMINI_API_KEY=... }"
PORT="${PORT:-8000}"
SPEED="${SPEED:-1.0}"
OUTPUTS="${OUTPUTS:-es,en}"

# Los 3 videos de prueba del challenge
URLS=(
  "https://www.youtube.com/watch?v=Z2EHHfyAyC4"
  "https://www.youtube.com/watch?v=7rteJoZSSzo"
  "https://www.youtube.com/watch?v=GVadbxHks_A"
)

# ⚠️  .env queda fuera de git (.gitignore) — la key nunca se commitea.
cat > .env <<EOF
GEMINI_API_KEY=${GEMINI_API_KEY}
CHARLAVIVA_ENGINE=gemini
GEMINI_MODE=caption
DEFAULT_OUTPUTS=${OUTPUTS}
EOF

echo "📦 Instalando dependencias…"
python3 -m pip install -q -r requirements.txt yt-dlp >/dev/null 2>&1 || \
  python3 -m pip install -q -r requirements.txt yt-dlp

mkdir -p downloads
FILES=(); TITLES=()
for url in "${URLS[@]}"; do
  echo "⬇️  Descargando audio: $url"
  filepath=$(python3 -m yt_dlp -f "bestaudio/best" --no-playlist \
    --print after_move:filepath -o "downloads/%(id)s.%(ext)s" "$url" | tail -1)
  title=$(python3 -m yt_dlp --skip-download --no-playlist --print "%(title)s" "$url" | tail -1)
  echo "   🎤 $title"
  FILES+=("$filepath"); TITLES+=("$title")
done

echo
echo "🚀 Levantando CharlaViva (Gemini Live) en el puerto ${PORT}…"
python3 -m charlaviva serve --port "${PORT}" &
SERVER_PID=$!
trap 'kill ${SERVER_PID} 2>/dev/null || true' EXIT
until curl -sf "http://localhost:${PORT}/api/health" >/dev/null 2>&1; do sleep 0.5; done

py_json() { python3 -c "import json,sys; print(json.dumps(sys.argv[1]))" "$1"; }
py_outputs() { python3 -c "import json,sys; print(json.dumps([s.strip() for s in sys.argv[1].split(',') if s.strip()]))" "$1"; }

for i in "${!FILES[@]}"; do
  echo "🎬 Creando sesión: ${TITLES[$i]}"
  curl -sf -X POST "http://localhost:${PORT}/api/sessions" \
    -H 'content-type: application/json' -d @- <<JSON
{
  "name": $(py_json "${TITLES[$i]}"),
  "source": { "type": "file", "path": $(py_json "${FILES[$i]}"), "speed": ${SPEED} },
  "src_lang": "auto",
  "outputs": $(py_outputs "${OUTPUTS}"),
  "glossary": ["Nerdearla", "Kubernetes", "Gemini", "Whisper", "open source"]
}
JSON
  echo
done

cat <<EOF

──────────────────────────────────────────────────────
✅ ¡Listo! Las 3 charlas se están subtitulando en vivo:

  👥 Audiencia:   http://localhost:${PORT}/
  🎛️ Producción:  http://localhost:${PORT}/admin
  🎥 OBS overlay: http://localhost:${PORT}/overlay?session=SESION_ID&lang=es

  Export de una charla (SRT en español):
  curl "http://localhost:${PORT}/api/sessions/SESION_ID/export?format=srt&lang=es" -o charla.srt

Ctrl+C para apagar.
──────────────────────────────────────────────────────
EOF

wait ${SERVER_PID}
