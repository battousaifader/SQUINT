#!/usr/bin/env bash
# AI Video Upscaler Launcher Script

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Ensure X11/Wayland display environment is exported
export DISPLAY="${DISPLAY:-:0}"
export QT_QPA_PLATFORM="${QT_QPA_PLATFORM:-xcb}"

VENV_PYTHON="$SCRIPT_DIR/.venv/bin/python3"

if [ -f "$VENV_PYTHON" ]; then
    echo "Launching AI Video Upscaler GUI..."
    exec "$VENV_PYTHON" "$SCRIPT_DIR/app.py" "$@"
else
    echo "⚠️ Virtual environment not found in $SCRIPT_DIR/.venv"
    echo "🔄 Running install.sh to setup environment..."
    bash "$SCRIPT_DIR/install.sh"
    exec "$VENV_PYTHON" "$SCRIPT_DIR/app.py" "$@"
fi
