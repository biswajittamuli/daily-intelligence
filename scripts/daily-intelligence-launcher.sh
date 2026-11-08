#!/usr/bin/env bash
# Daily Intelligence desktop launcher (Fedora KDE).
#
# - one server per user: a healthy server on the port is reused, never duplicated
# - launch lock prevents two simultaneous starts
# - opens a dedicated app window (Chrome/Chromium --app with its own profile); its
#   Wayland/X11 app id is "chrome-127.0.0.1__-Default", matched by StartupWMClass so it
#   groups and pins in the KDE taskbar; falls back to the default browser
# - when the app window closes, the server is asked to shut down (it refuses while a
#   search is running, and then stops by itself after the idle timeout)
# - persistent logs in ~/.local/state/daily-intelligence/logs
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
STATE_DIR="${XDG_STATE_HOME:-$HOME/.local/state}/daily-intelligence"
LOG_DIR="$STATE_DIR/logs"
LAUNCH_LOG="$LOG_DIR/launcher.log"
SERVER_LOG="$LOG_DIR/server.log"
PID_FILE="$STATE_DIR/server.pid"
PORT="${DAILY_INTELLIGENCE_PORT:-8765}"
URL="http://127.0.0.1:${PORT}/"
IDLE_TIMEOUT="${DAILY_INTELLIGENCE_IDLE_TIMEOUT:-900}"
APP_CLASS="daily-intelligence"
mkdir -p "$LOG_DIR"

log() { printf '%s [launcher %s] %s\n' "$(date --iso-8601=seconds)" "$$" "$*" >>"$LAUNCH_LOG"; }

notify_error() {
  log "ERROR: $1"
  if command -v kdialog >/dev/null 2>&1; then
    kdialog --title "Daily Intelligence" --error "$1" >/dev/null 2>&1 &
  elif command -v notify-send >/dev/null 2>&1; then
    notify-send -a "Daily Intelligence" -i "$APP_CLASS" -u critical "Daily Intelligence" "$1" || true
  fi
  printf 'Daily Intelligence: %s\n' "$1" >&2
}

healthy() {
  curl -fsS --max-time 2 "${URL}api/health" 2>/dev/null | grep -q '"app": *"daily-intelligence"'
}

port_busy() {
  (exec 3<>"/dev/tcp/127.0.0.1/${PORT}") 2>/dev/null
}

start_server() {
  if [[ ! -x "$PROJECT_DIR/.venv/bin/python" ]]; then
    notify_error "The Python environment is missing. Run 'uv sync' in $PROJECT_DIR."
    return 1
  fi
  if port_busy; then
    # An older Daily Intelligence (without /api/health) from this project: stop it and upgrade.
    old_pids="$(pgrep -f "$PROJECT_DIR/.venv/bin/python -m app.main serve" || true)"
    if [[ -n "$old_pids" ]] && curl -fsS --max-time 2 "${URL}api/bootstrap" 2>/dev/null | grep -q '"version"'; then
      log "stopping older Daily Intelligence server(s): $old_pids"
      kill -TERM $old_pids 2>/dev/null || true
      for _ in $(seq 1 40); do port_busy || break; sleep 0.25; done
    fi
    if port_busy; then
      notify_error "Port ${PORT} is used by another program. Close it or set DAILY_INTELLIGENCE_PORT."
      return 1
    fi
  fi
  # Rotate a large server log.
  if [[ -f "$SERVER_LOG" && $(stat -c %s "$SERVER_LOG") -gt 5242880 ]]; then
    mv -f "$SERVER_LOG" "$SERVER_LOG.1"
  fi
  if ! curl -fsS --max-time 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    log "Ollama is not reachable; AI extraction will fall back to deterministic parsing"
    command -v notify-send >/dev/null 2>&1 && notify-send -a "Daily Intelligence" -i "$APP_CLASS" \
      "Daily Intelligence" "Ollama is not running. The app opens, but local-model features are limited." || true
  fi
  log "starting server (idle timeout ${IDLE_TIMEOUT}s)"
  printf '\n=== server start %s ===\n' "$(date --iso-8601=seconds)" >>"$SERVER_LOG"
  ( cd "$PROJECT_DIR" && setsid nohup "$PROJECT_DIR/.venv/bin/python" -m app.main serve --no-browser \
      --idle-timeout "$IDLE_TIMEOUT" --pid-file "$PID_FILE" >>"$SERVER_LOG" 2>&1 </dev/null & )
  for _ in $(seq 1 80); do
    if healthy; then log "server healthy (pid $(cat "$PID_FILE" 2>/dev/null))"; return 0; fi
    sleep 0.25
  done
  notify_error "The local server did not start within 20 seconds. See $SERVER_LOG"$'\n\n'"$(tail -n 8 "$SERVER_LOG" 2>/dev/null)"
  return 1
}

find_browser() {
  for candidate in google-chrome google-chrome-stable chromium chromium-browser brave-browser microsoft-edge; do
    if command -v "$candidate" >/dev/null 2>&1; then printf '%s' "$candidate"; return 0; fi
  done
  return 1
}

# ---------------------------------------------------------------- start
exec 8>"$STATE_DIR/launch.lock"
if ! flock -w 30 8; then
  notify_error "Another launch is still in progress."
  exit 1
fi
if healthy; then
  log "server already running; reusing it"
else
  start_server || exit 1
fi
flock -u 8

BROWSER="$(find_browser || true)"
if [[ -z "$BROWSER" ]]; then
  log "no Chromium-based browser; opening default browser"
  xdg-open "$URL" >/dev/null 2>&1 &
  exit 0
fi

PROFILE_DIR="$STATE_DIR/browser-profile"
exec 9>"$STATE_DIR/window.lock"
if ! flock -n 9; then
  # A window owned by another launcher is open: focus/open a window there and exit.
  # A window owned by another launcher is open: bring it to the front (KWin), else open one.
  match="$(gdbus call --session --dest org.kde.KWin --object-path /WindowsRunner \
    --method org.kde.krunner1.Match "Daily Intelligence" 2>/dev/null | grep -o "'0_{[^}]*}'" | head -n1 | tr -d "'")"
  if [[ -n "$match" ]] && gdbus call --session --dest org.kde.KWin --object-path /WindowsRunner \
      --method org.kde.krunner1.Run "$match" "" >/dev/null 2>&1; then
    log "app window already open; activated it"
  else
    log "app window already open; opening another window"
    "$BROWSER" --user-data-dir="$PROFILE_DIR" --app="$URL" >/dev/null 2>&1 &
  fi
  exit 0
fi

log "opening app window with $BROWSER"
"$BROWSER" --user-data-dir="$PROFILE_DIR" --app="$URL" \
  --no-first-run --no-default-browser-check >>"$LAUNCH_LOG" 2>&1
log "app window closed"

# Window closed: stop the server unless a search is still running (then idle timeout applies).
if healthy; then
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 5 -X POST -H 'Content-Type: application/json' \
    -d '{}' "${URL}api/shutdown")
  if [[ "$code" == "202" ]]; then
    log "server shutdown requested"
  else
    log "server kept running (HTTP $code: a search may still be running; it stops after ${IDLE_TIMEOUT}s idle)"
  fi
fi
exit 0
