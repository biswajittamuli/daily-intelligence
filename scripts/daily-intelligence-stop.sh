#!/usr/bin/env bash
# Stop the Daily Intelligence server cleanly (cancels a running search).
set -uo pipefail
PORT="${DAILY_INTELLIGENCE_PORT:-8765}"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/daily-intelligence"
PID_FILE="$STATE_DIR/server.pid"
URL="http://127.0.0.1:${PORT}/"

if curl -fsS --max-time 2 "${URL}api/health" 2>/dev/null | grep -q '"app": *"daily-intelligence"'; then
  curl -s -o /dev/null --max-time 5 -X POST -H 'Content-Type: application/json' -d '{"force": true}' "${URL}api/shutdown"
  for _ in $(seq 1 40); do
    curl -fsS --max-time 1 "${URL}api/health" >/dev/null 2>&1 || { echo "Daily Intelligence stopped."; exit 0; }
    sleep 0.25
  done
fi
if [[ -f "$PID_FILE" ]]; then
  pid="$(cat "$PID_FILE")"
  if [[ -n "$pid" ]] && grep -q "app.main" "/proc/$pid/cmdline" 2>/dev/null; then
    kill -TERM "$pid" && echo "Sent SIGTERM to server $pid."
  fi
  rm -f "$PID_FILE"
fi
echo "Daily Intelligence is not running."
