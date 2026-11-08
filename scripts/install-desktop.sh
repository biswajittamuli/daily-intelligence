#!/usr/bin/env bash
# Install the Daily Intelligence launcher and icon for the current user (KDE/freedesktop).
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/.." && pwd)"
APPS_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
ICON_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/icons/hicolor/scalable/apps"
# The app window is Chrome --app; on Wayland its app id is fixed by Chrome as
# "chrome-<host>__-Default" (--class is ignored). Installing the launcher under that id
# makes the KDE menu entry, window icon, Alt+Tab and taskbar pin all refer to one app.
DESKTOP_ID="chrome-127.0.0.1__-Default"
DESKTOP_FILE="$APPS_DIR/$DESKTOP_ID.desktop"
rm -f "$APPS_DIR/daily-intelligence.desktop"  # earlier install name

mkdir -p "$APPS_DIR" "$ICON_DIR"
chmod +x "$PROJECT_DIR/scripts/daily-intelligence-launcher.sh" "$PROJECT_DIR/scripts/daily-intelligence-stop.sh"
install -m 0644 "$PROJECT_DIR/desktop/daily-intelligence.svg" "$ICON_DIR/daily-intelligence.svg"

cat >"$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.5
Type=Application
Name=Daily Intelligence
GenericName=Personal Intelligence Assistant
Comment=Jobs, exams, AI news and research — local and private
Exec=$PROJECT_DIR/scripts/daily-intelligence-launcher.sh
Path=$PROJECT_DIR
Icon=daily-intelligence
Terminal=false
Categories=Utility;
Keywords=jobs;resume;news;research;briefing;
StartupNotify=true
StartupWMClass=$DESKTOP_ID
Actions=Stop;

[Desktop Action Stop]
Name=Stop Daily Intelligence server
Exec=$PROJECT_DIR/scripts/daily-intelligence-stop.sh
EOF
chmod 0644 "$DESKTOP_FILE"
# Keep the in-repo copy identical for reference.
cp "$DESKTOP_FILE" "$PROJECT_DIR/desktop/daily-intelligence.desktop"

desktop-file-validate "$DESKTOP_FILE"
command -v update-desktop-database >/dev/null && update-desktop-database "$APPS_DIR" || true
command -v gtk-update-icon-cache >/dev/null && gtk-update-icon-cache -q -t "${ICON_DIR%/scalable/apps}" || true
command -v kbuildsycoca6 >/dev/null && kbuildsycoca6 >/dev/null 2>&1 || true
echo "Installed $DESKTOP_FILE (menu: Daily Intelligence) and icon $ICON_DIR/daily-intelligence.svg"
