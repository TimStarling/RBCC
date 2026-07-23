#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ -z "${DISPLAY:-}" ]]; then
    export DISPLAY=:0
fi

# This is a fixed, unattended monitoring display.  Disable the X screen saver
# and DPMS so the Orange Pi does not blank the panel during a shift.  The
# commands are intentionally best-effort: the serial/TCP service must still
# start if a desktop session has not finished initialising yet.
if command -v xset >/dev/null 2>&1; then
    xset -display "$DISPLAY" s off || true
    xset -display "$DISPLAY" s noblank || true
    xset -display "$DISPLAY" -dpms || true
fi

export PYTHONUNBUFFERED=1

LOCK_DIR="${XDG_RUNTIME_DIR:-/tmp}"
LOCK_FILE="$LOCK_DIR/rbcc-interface-${USER:-HwHiAiUser}.lock"
PYTHON_BIN="/usr/bin/python3"

exec flock -n "$LOCK_FILE" "$PYTHON_BIN" "$SCRIPT_DIR/main.py" "$@"
