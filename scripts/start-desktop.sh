#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="/home/biswajittamuli/projects/daily-intelligence"
cd "$PROJECT_DIR"

LOG_FILE="${DAILY_INTELLIGENCE_LOG_FILE:-$PROJECT_DIR/data/application.log}"
mkdir -p "$(dirname "$LOG_FILE")"
exec >>"$LOG_FILE" 2>&1
printf '\n=== Daily Intelligence launch %s ===\n' "$(date --iso-8601=seconds)"

if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "Daily Intelligence" "The project uv environment is missing. Run uv sync in $PROJECT_DIR." || true
  fi
  printf 'Daily Intelligence: missing .venv. Run uv sync in %s\n' "$PROJECT_DIR" >&2
  exit 1
fi

if ! curl --silent --show-error --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "Daily Intelligence" "Ollama is unavailable. The interface will open; start Ollama before running AI requests." || true
  else
    printf 'Daily Intelligence: Ollama is unavailable; AI requests will show an error.\n' >&2
  fi
fi

if ! "$PROJECT_DIR/.venv/bin/python" -m app.main serve; then
  if command -v notify-send >/dev/null 2>&1; then
    notify-send "Daily Intelligence" "The local interface could not start. Check whether the port is available and try again." || true
  fi
  exit 1
fi
