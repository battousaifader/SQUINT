# S.Q.U.I.N.T. 
*(Super-resolution Quality Upgrades In Neural Tasks)*
> Because you won't have to squint at fuzzy video anymore.

A high-performance standalone desktop application for batch video upscaling using PyTorch `.pth` models (optimized for Real-CUGAN, with universal support for Real-ESRGAN, ESRGAN, and Compact models) via direct dual-FFmpeg RAM pipe streaming and full track preservation.

---

## ⚡ Model Optimization & Performance Tuning

### 🚀 **Optimized for Real-CUGAN (Maximum Speed)**
S.Q.U.I.N.T. has been specifically tuned for **Real-CUGAN** upscaler models (`RealCUGAN_2x.pth`, `RealCUGAN_3x.pth`, `RealCUGAN_4x.pth`):
- **Why Real-CUGAN?** Unlike heavy 23-block ESRGAN photo-restoration models that require ~115+ convolutions per frame, Real-CUGAN uses a highly streamlined neural architecture designed specifically for high-throughput video and anime upscaling.
- **Universal Compatibility**: Powered by `spandrel`, S.Q.U.I.N.T. still supports heavy ESRGAN, Real-ESRGAN, and Compact models out of the box when ultra-high detail reconstruction is required.

### 💡 **Pro-Tips for Maximum FPS**
1. **Tile Size Selection**:
   - `256` or `512`: Recommended for lower VRAM GPUs (4 GB - 6 GB) to prevent Out-Of-Memory (OOM) errors.
   - `1024` or `Off`: Recommended for GPUs with 8 GB+ VRAM. Turning tile size `Off` processes full video frames in a single CUDA pass, boosting speed by **2x to 4x**.
2. **Enable FP16 Precision**:
   - Checking "Enable FP16 Precision" in settings activates NVIDIA Tensor Cores for half-precision math, doubling execution speed with zero noticeable quality drop.
3. **Use Hardware NVENC Encoders**:
   - Select `hevc_nvenc` or `h264_nvenc` (`av1_nvenc` on RTX 40/50 series) to offload encoding from the CPU and prevent pipeline bottlenecks.
4. **Auto-Crop Black Bars**:
   - Enable Auto-Crop to dynamically remove letterboxing before PyTorch processing, saving up to 25% of wasted GPU compute.

---

## 💻 System & Hardware Requirements

To get intended GPU performance, high-speed dual-piping, and NVENC hardware video encoding, the following hardware is recommended:

| Component | Minimum Requirement | Recommended (Intended Experience) |
| :--- | :--- | :--- |
| **GPU** | NVIDIA GTX 10-series (Pascal) or newer with 4GB VRAM | **NVIDIA RTX 20 / 30 / 40 / 50 Series** (Turing, Ampere, Ada Lovelace, Blackwell) with 8GB+ VRAM |
| **CUDA Architecture** | CUDA Compute Capability 6.0+ | CUDA Compute Capability 7.5+ (Tensor Cores enabled via FP16 precision) |
| **NVENC Capabilities** | H.264 / HEVC Hardware Encoders (`h264_nvenc`, `hevc_nvenc`) | AV1 Hardware Encoder (`av1_nvenc` available on RTX 40 / 50 Series) |
| **VRAM Usage** | 4 GB VRAM *(use 256x256 or 512x512 tile size)* | 8 GB+ VRAM *(allows 1024x1024 or full-frame processing)* |
| **System RAM** | 8 GB RAM | 16 GB+ RAM |
| **OS** | Windows 10 / 11 (64-bit) or Linux | Windows 11 (64-bit) or Linux (Ubuntu / Debian / Arch / Fedora) |

> ℹ️ **CPU Fallback:** CPU software upscaling (`libx264`, `libx265`) is supported if no CUDA-compatible GPU is present, but processing speed will be substantially lower.

---

## 📦 Required Dependencies

`install.py` installs and verifies all necessary Python packages inside a managed `.venv` environment automatically.

### System Prerequisites
- **Python**: 3.10 or newer (`python3` / `py`)
- **FFmpeg & FFprobe**: Must be available on system `PATH` or placed in local `./ffmpeg/bin/` folder.

### Python Library Dependencies
- **`torch` & `torchvision`**: PyTorch runtime (configured with CUDA 12.1 acceleration on Windows).
- **`spandrel`**: Universal PyTorch model loader supporting Real-ESRGAN, Real-CUGAN, ESRGAN, Compact, and SwinIR architectures.
- **`PySide6`**: Qt 6 graphical interface framework.
- **`numpy`**: High-speed raw RGB24 frame buffer manipulation.
- **`psutil`**: Process and system resource tracking.

---

## 🚀 Features

- **Dual-FFmpeg RAM Piping**: Streams raw RGB video frames directly through Python RAM queues. Zero temporary PNG image files written to disk.
- **Universal `.pth` Model Support**: Powered by `spandrel` for auto-detecting Real-CUGAN (2x/3x/4x), Real-ESRGAN, ESRGAN, and Compact model checkpoints.
- **100% Track Preservation**: Stream-copies audio, subtitle, data, and attachment tracks from original video files (`-c:a copy -c:s copy ...`), with optional audio transcoding (AAC).
- **Hardware Acceleration**: Auto-detects NVIDIA NVENC hardware encoders (`hevc_nvenc`, `h264_nvenc`, `av1_nvenc`) with CPU fallbacks (`libx264`, `libx265`).
- **Post-AI Filters & Tuning**: Integrated color saturation controls, post-AI film grain injection, and automatic black bar crop detection (`cropdetect`).
- **VRAM OOM Prevention**: Tile-based CUDA inference with overlap stitching and FP16 half-precision support.
- **Auto Shutdown**: Option to automatically power down the PC upon completing long queue runs.

---

## 🔧 Installation & Setup

1. **Automated Cross-Platform Setup**:
   Run the universal Python installation script to detect your OS (Windows/Linux), set up `.venv`, install exact CUDA or CPU dependencies, verify all imports, and create a desktop shortcut:
   ```bash
   python3 install.py
   ```
   *(On Windows, simply double-click `run.bat`, which will auto-run setup if needed)*

2. **Add Model Checkpoints**:
   Place PyTorch `.pth` model files (e.g., `RealCUGAN_2x.pth`, `RealESRGAN_x4plus.pth`) in the `models/` folder.

3. **Launch Application**:
   - **Linux / macOS**: `./run.sh`
   - **Windows**: `run.bat`

---

## 📁 File Structure

```
/mnt/2tb/Video Upscaler/
├── app.py              # PySide6 GUI, batch queue management & worker thread
├── upscaler_engine.py  # Dual-FFmpeg pipe manager, async queue & PyTorch CUDA loop
├── models/             # Directory for placing .pth model weights
├── requirements.txt    # Python dependencies list
├── install.py          # Universal cross-platform setup & dependency verifier
├── run.sh              # Smart launcher script for Linux/macOS
└── run.bat             # Smart launcher script for Windows
```

---

## 📄 License

This project is licensed under the [MIT License](file:///mnt/2tb/Video%20Upscaler/LICENSE) - see the LICENSE file for details.
