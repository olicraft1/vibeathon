#!/usr/bin/env bash
# Fetch a talk's audio from YouTube (or any site yt-dlp supports) and print
# the command to run it as a live session in CharlaViva.
#
#   ./scripts/fetch_talk.sh "https://www.youtube.com/watch?v=XXXX" [output.m4a]
#
# Uses yt-dlp's plain audio download — no ffmpeg needed: CharlaViva decodes
# m4a/webm/opus/mp3 directly with PyAV.
set -euo pipefail

URL="${1:?usage: fetch_talk.sh <video-url> [output-file]}"
OUT="${2:-downloads/$(echo "$URL" | tr -c 'a-zA-Z0-9' '_' | tail -c 40).m4a}"

mkdir -p "$(dirname "$OUT")"

if ! command -v yt-dlp >/dev/null 2>&1; then
  echo "yt-dlp not found. Install it with: pip install yt-dlp" >&2
  exit 1
fi

echo "⬇️  Downloading audio from $URL"
yt-dlp -f "bestaudio/best" -o "$OUT" "$URL"

cat <<EOF

✅ Audio saved to: $OUT

Run it as a live session (replayed at real-time pace):

  python -m charlaviva serve
  # then, in another terminal (or via the admin UI):
  curl -X POST localhost:8000/api/sessions -H 'content-type: application/json' -d '{
    "name": "My talk",
    "source": {"type": "file", "path": "$OUT", "speed": 1.0},
    "src_lang": "en",
    "outputs": ["es", "en"],
    "glossary": ["Nerdearla"]
  }'

Or pipe a real live stream (HLS from OBS/vMix/YouTube Live):

  curl -X POST localhost:8000/api/sessions -H 'content-type: application/json' -d '{
    "name": "Escenario en vivo",
    "source": {"type": "stream", "url": "https://example.com/stage1/index.m3u8"},
    "src_lang": "en", "outputs": ["es", "en"]
  }'
EOF
