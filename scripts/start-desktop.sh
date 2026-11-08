#!/usr/bin/env bash
# Backwards-compatible entry point; the launcher handles single-instance start, logs and shutdown.
exec "$(dirname "$(readlink -f "$0")")/daily-intelligence-launcher.sh" "$@"
