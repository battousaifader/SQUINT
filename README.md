# S.Q.U.I.N.T. 
*(Super-resolution Quality Upgrades In Neural Tasks)*
> Because you won't have to squint at fuzzy video anymore.

A high-performance standalone desktop application for batch video upscaling using PyTorch `.pth` models (Real-CUGAN, Real-ESRGAN, ESRGAN) with direct dual-FFmpeg pipe streaming and full non-video stream-copying.

## Features
- **Dual-FFmpeg RAM Piping**: Streams raw RGB video frames directly through Python RAM queues. Zero temporary PNG image files written to disk.
- **Selectable `.pth` Models**: Dynamic scanner for `.pth` model checkpoints (Real-CUGAN 2x/3x/4x, Real-ESRGAN, Compact models).
- **100% Track Preservation**: Stream-copies all audio, subtitle, data, and attachment tracks from original video files (`-c:a copy -c:s copy ...`).
- **Hardware Acceleration**: Auto-detects NVIDIA NVENC hardware encoders (`hevc_nvenc`, `h264_nvenc`, `av1_nvenc`) with CPU fallbacks (`libx264`, `libx265`).
- **VRAM OOM Prevention**: Tile-based CUDA inference with overlap stitching and FP16 half-precision support.
- **Modern PySide6 GUI**: Dark-themed UI with drag-and-drop batch queue, resolution scaling, custom target FPS, quality controls, live progress, ETA meter, and log console.

---

## Installation & Setup

1. **Automated Setup**:
   Run the installation script to set up the virtual environment (`.venv`), install dependencies, and register a desktop shortcut:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```

2. **Add Model Checkpoints**:
   Place your PyTorch `.pth` model files (e.g. `RealCUGAN_2x.pth`, `RealESRGAN_x4plus.pth`) in the `models/` folder.

3. **Launch Application**:
   Launch via the launcher script or your desktop application menu:
   ```bash
   ./run.sh
   ```

---

## File Structure

```
/mnt/2tb/Video Upscaler/
├── app.py              # PySide6 GUI, batch queue management & worker thread
├── upscaler_engine.py  # Dual-FFmpeg pipe manager, async queue & PyTorch CUDA loop
├── model_loader.py     # Real-CUGAN & ESRGAN PyTorch model loader + auto-tiling
├── models/             # Directory for placing .pth model weights
├── requirements.txt    # Python dependencies
└── README.md           # Documentation
