#!/usr/bin/env bash
# Run Feed the Faces on Arduino UNO Q (Debian Linux side). Use 1280×720 display via USB-C DP.
set -euo pipefail
cd "$(dirname "$0")/.."
export FTF_WS_SAME_ORIGIN=1
export FTF_EMBEDDED=1
npm run build:uno-q
pip3 install -q -r requirements-web.txt 2>/dev/null || pip install -q -r requirements-web.txt
python3 web_server.py &
SRV_PID=$!
sleep 2
URL="http://127.0.0.1:${PORT:-8080}/"
if command -v chromium >/dev/null 2>&1; then
  chromium --kiosk --app="$URL" --noerrdialogs --disable-translate &
elif command -v chromium-browser >/dev/null 2>&1; then
  chromium-browser --kiosk --app="$URL" &
else
  echo "Open in browser: $URL"
  wait $SRV_PID
  exit 0
fi
wait $SRV_PID
