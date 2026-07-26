#!/usr/bin/env bash
# AI Video Upscaler Environment Setup Script

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
echo "=== AI Video Upscaler Environment Setup ==="

# 1. Check Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: python3 is required but not found on PATH."
    exit 1
fi

PYTHON_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
echo "✅ Found Python version: $PYTHON_VER"

# 2. Check FFmpeg and FFprobe
if ! command -v ffmpeg &> /dev/null; then
    echo "⚠️ Warning: 'ffmpeg' is not found on PATH. Video processing will fail."
else
    echo "✅ Found FFmpeg: $(ffmpeg -version | head -n 1)"
fi

if ! command -v ffprobe &> /dev/null; then
    echo "⚠️ Warning: 'ffprobe' is not found on PATH. Video probing will fail."
fi

# 3. Create Virtual Environment
VENV_DIR="$SCRIPT_DIR/.venv"
if [ ! -d "$VENV_DIR" ]; then
    echo "📦 Creating virtual environment in .venv..."
    python3 -m venv "$VENV_DIR"
else
    echo "📦 Existing virtual environment found in .venv"
fi

# 4. Install Dependencies
echo "📥 Installing / Updating PyTorch, PySide6, and dependencies..."
"$VENV_DIR/bin/pip" install --upgrade pip setuptools wheel
"$VENV_DIR/bin/pip" install -r "$SCRIPT_DIR/requirements.txt"

# 5. Make Launcher Executable
chmod +x "$SCRIPT_DIR/run.sh"

# 6. Optional: Create Desktop Entry
DESKTOP_DIR="$HOME/.local/share/applications"
if [ -d "$DESKTOP_DIR" ]; then
    DESKTOP_FILE="$DESKTOP_DIR/ai-video-upscaler.desktop"
    echo "🖥️ Creating Desktop Launcher at $DESKTOP_FILE..."
    cat <<EOF > "$DESKTOP_FILE"
[Desktop Entry]
Type=Application
Name=AI Video Upscaler
Comment=PyTorch & PySide6 GPU Video Upscaling Application
Exec=$SCRIPT_DIR/run.sh
Icon=video-x-generic
Terminal=false
Categories=AudioVideo;Video;Graphics;
EOF
    chmod +x "$DESKTOP_FILE"
    echo "✅ Desktop launcher created successfully!"
fi

echo ""
echo "=========================================="
echo "🎉 Setup complete! You can start the app using:"
echo "   ./run.sh"
echo "=========================================="
