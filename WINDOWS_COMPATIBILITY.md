# Windows Compatibility & Optimization Guide for S.Q.U.I.N.T.

> **Note for Repository Author**: This document details all identified Linux-specific assumptions in **S.Q.U.I.N.T.** and provides copy-pasteable scripts, code diffs, and best practices to achieve full, seamless Windows support alongside Linux.

---

## Table of Contents
1. [Overview of Windows Compatibility Blockers](#1-overview-of-windows-compatibility-blockers)
2. [New Windows Scripts (Add to Repository)](#2-new-windows-scripts-add-to-repository)
   - [`install.ps1`](#installps1)
   - [`run.ps1`](#runps1)
   - [`run.bat`](#runbat)
3. [Recommended Python Code Modifications](#3-recommended-python-code-modifications)
   - [`upscaler_engine.py`](#upscaler_enginepy)
   - [`app.py`](#apppy)
4. [README Updates & User Guidance](#4-readme-updates--user-guidance)
5. [Author Integration Checklist](#5-author-integration-checklist)

---

## 1. Overview of Windows Compatibility Blockers

| Component | Identified Issue on Windows | Impact | Resolution |
| :--- | :--- | :--- | :--- |
| **Setup & Launcher Scripts** | `install.sh` and `run.sh` use Linux bash syntax (`chmod +x`, `.venv/bin/`, `$HOME/.local/share/applications`). | Windows users cannot double-click or run installation scripts directly. | Add `install.ps1`, `run.ps1`, and `run.bat` scripts for Windows. |
| **Qt Platform Plugin** | `run.sh` sets `export QT_QPA_PLATFORM=xcb`. | `xcb` is X11-only. On Windows, PySide6 fails at startup with `qt.qpa.plugin: Could not load the Qt platform plugin "xcb"`. | Keep Linux environment exports inside `run.sh` only and do not export `QT_QPA_PLATFORM` on Windows (let PySide6 use default `windows` plugin). |
| **Subprocess Popups** | `subprocess.Popen` and `subprocess.run` calls spawn console windows on Windows. | Popping command prompt windows appear whenever `ffprobe` or `ffmpeg` runs. | Add `creationflags=subprocess.CREATE_NO_WINDOW` on Windows (`sys.platform == 'win32'`). |
| **FFmpeg Binary Lookup** | `ffmpeg` and `ffprobe` calls assume binaries are on system `PATH`. | Windows users without FFmpeg in PATH experience silent or noisy subprocess crashes. | Add `shutil.which` fallback checks and detect local `ffmpeg.exe`/`ffprobe.exe` or guide user to `winget install FFmpeg`. |
| **Virtualenv Paths** | Linux uses `.venv/bin/python3`, Windows uses `.venv\Scripts\python.exe`. | Hardcoded `.venv/bin/` paths break on Windows. | Use OS-aware virtual environment paths in launchers. |
| **PyTorch CUDA Wheels** | `pip install torch` on Windows can default to CPU-only builds. | PyTorch fails to utilize NVIDIA CUDA hardware acceleration on Windows. | Include `--index-url https://download.pytorch.org/whl/cu121` option in `install.ps1`. |

---

## 2. New Windows Scripts (Add to Repository)

Create the following files in the root directory of the repository:

### `install.ps1`
*Automated PowerShell setup script for Windows users.*

```powershell
# S.Q.U.I.N.T. Windows Environment Setup Script
$ErrorActionPreference = "Stop"

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " S.Q.U.I.N.T. Windows Environment Setup  " -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan

# 1. Check Python
$pythonCmd = Get-Command python -ErrorAction SilentlyContinue
if (-not $pythonCmd) {
    $pythonCmd = Get-Command python3 -ErrorAction SilentlyContinue
}

if (-not $pythonCmd) {
    Write-Host "❌ Error: Python is not found on PATH. Please install Python 3.9+ from python.org or Microsoft Store." -ForegroundColor Red
    Exit 1
}

$pyVer = & $pythonCmd.Source -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
Write-Host "✅ Found Python version: $pyVer" -ForegroundColor Green

# 2. Check FFmpeg and FFprobe
$ffmpegCmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
$ffprobeCmd = Get-Command ffprobe -ErrorAction SilentlyContinue

if (-not $ffmpegCmd) {
    Write-Host "⚠️ Warning: 'ffmpeg' is not found on PATH." -ForegroundColor Yellow
    Write-Host "   Install FFmpeg via Winget: winget install FFmpeg" -ForegroundColor Yellow
} else {
    Write-Host "✅ Found FFmpeg executable on PATH." -ForegroundColor Green
}

if (-not $ffprobeCmd) {
    Write-Host "⚠️ Warning: 'ffprobe' is not found on PATH. Video probing will fail." -ForegroundColor Yellow
}

# 3. Create Virtual Environment
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvDir = Join-Path $scriptDir ".venv"
$venvPython = Join-Path $venvDir "Scripts\python.exe"

if (-not (Test-Path $venvDir)) {
    Write-Host "📦 Creating virtual environment in .venv..." -ForegroundColor Cyan
    & $pythonCmd.Source -m venv $venvDir
} else {
    Write-Host "📦 Existing virtual environment found in .venv" -ForegroundColor Green
}

# 4. Install PyTorch & Dependencies
Write-Host "📥 Installing PyTorch, PySide6, and dependencies..." -ForegroundColor Cyan
& $venvPython -m pip install --upgrade pip setuptools wheel

# Check for CUDA availability
$hasNvidia = $false
try {
    $gpu = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
    if ($gpu) { $hasNvidia = $true }
} catch {}

if ($hasNvidia) {
    Write-Host "🚀 NVIDIA GPU detected! Installing PyTorch with CUDA 12.1 acceleration..." -ForegroundColor Green
    & $venvPython -m pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121
    & $venvPython -m pip install PySide6>=6.5.0 numpy psutil
} else {
    Write-Host "ℹ️ Standard PyTorch installation..." -ForegroundColor Cyan
    & $venvPython -m pip install -r (Join-Path $scriptDir "requirements.txt")
}

# 5. Optional Desktop Shortcut Creation
$desktopDir = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktopDir "S.Q.U.I.N.T. Upscaler.lnk"

try {
    $wshShell = New-Object -ComObject WScript.Shell
    $shortcut = $wshShell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $scriptDir "run.bat"
    $shortcut.WorkingDirectory = $scriptDir
    $shortcut.Description = "S.Q.U.I.N.T. AI Video Upscaler"
    $shortcut.Save()
    Write-Host "✅ Desktop shortcut created successfully!" -ForegroundColor Green
} catch {
    Write-Host "ℹ️ Desktop shortcut creation skipped." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "🎉 Setup complete! You can start S.Q.U.I.N.T. using:" -ForegroundColor Green
Write-Host "   .\run.bat  or  .\run.ps1" -ForegroundColor Yellow
Write-Host "==========================================" -ForegroundColor Green

Read-Host "Press Enter to exit"
```

---

### `run.ps1`
*PowerShell launcher script.*

```powershell
# S.Q.U.I.N.T. PowerShell Launcher Script
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path $scriptDir ".venv\Scripts\python.exe"
$appPy = Join-Path $scriptDir "app.py"

if (Test-Path $venvPython) {
    Write-Host "🚀 Launching S.Q.U.I.N.T. AI Video Upscaler..." -ForegroundColor Green
    & $venvPython $appPy @args
} else {
    Write-Host "⚠️ Virtual environment not found in .venv" -ForegroundColor Yellow
    Write-Host "🔄 Running install.ps1 to setup environment..." -ForegroundColor Cyan
    & (Join-Path $scriptDir "install.ps1")
    if (Test-Path $venvPython) {
        & $venvPython $appPy @args
    }
}
```

---

### `run.bat`
*Zero-dependency batch launcher (Double-clickable on Windows).*

```bat
@echo off
set SCRIPT_DIR=%~dp0
set VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe

if exist "%VENV_PYTHON%" (
    echo Launching S.Q.U.I.N.T. AI Video Upscaler...
    "%VENV_PYTHON%" "%SCRIPT_DIR%app.py" %*
) else (
    echo Virtual environment not found. Running setup...
    powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%install.ps1"
    if exist "%VENV_PYTHON%" (
        "%VENV_PYTHON%" "%SCRIPT_DIR%app.py" %*
    }
)
```

---

## 3. Recommended Python Code Modifications

### `upscaler_engine.py`

#### A. Add `shutil` and Subprocess `CREATE_NO_WINDOW` Flag
Add OS detection for process creation flags to hide terminal windows on Windows:

```python
import shutil

# Cross-platform subprocess creation flags (hides popping console windows on Windows)
SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0

def find_executable(name):
    """
    Finds executable on system PATH or local project directory.
    """
    found = shutil.which(name)
    if found:
        return found
    # Check local fallback directory (e.g. ./ffmpeg/bin/ffmpeg.exe)
    base_dir = os.path.dirname(os.path.abspath(__file__))
    local_ext = f"{name}.exe" if sys.platform == 'win32' else name
    local_path = os.path.join(base_dir, "ffmpeg", "bin", local_ext)
    if os.path.exists(local_path):
        return local_path
    return name
```

#### B. Update `subprocess` Invocations
Update `probe_video`, `probe_system_encoders`, and `run_upscale_pipeline` to use resolved binary paths and `SUBPROCESS_FLAGS`:

```python
def probe_video(input_path):
    ffprobe_bin = find_executable('ffprobe')
    cmd = [
        ffprobe_bin, '-v', 'quiet', '-print_format', 'json',
        '-show_format', '-show_streams', input_path
    ]
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True, creationflags=SUBPROCESS_FLAGS)
        data = json.loads(res.stdout)
    ...
```

```python
def probe_system_encoders():
    ffmpeg_bin = find_executable('ffmpeg')
    cmd = [ffmpeg_bin, '-encoders']
    encoders = []
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=SUBPROCESS_FLAGS)
    ...
```

```python
    # In run_upscale_pipeline:
    ffmpeg_bin = find_executable('ffmpeg')
    
    decoder_proc = subprocess.Popen(
        decoder_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=10**7,
        creationflags=SUBPROCESS_FLAGS
    )
    
    encoder_proc = subprocess.Popen(
        encoder_cmd,
        stdin=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=10**7,
        creationflags=SUBPROCESS_FLAGS
    )
```

---

### `app.py`

#### Cross-Platform Path Normalization
Ensure model resolution and drag-and-drop paths handle Windows backslashes (`\`) cleanly:

```python
    def refresh_models(self):
        self.model_combo.clear()
        base_dir = os.path.dirname(os.path.abspath(__file__))
        found_models = []
        
        for root, _, files in os.walk(base_dir):
            if '.venv' in root:
                continue
            for f in sorted(files):
                if f.endswith('.pth'):
                    full_path = os.path.normpath(os.path.join(root, f))
                    rel_parent = os.path.basename(root)
                    display_name = f"{rel_parent}/{f}" if rel_parent != os.path.basename(base_dir) else f
                    found_models.append((display_name, full_path))

        for display_name, full_path in found_models:
            self.model_combo.addItem(display_name, userData=full_path)
```

---

## 4. README Updates & User Guidance

Add the following section to `README.md` to document Windows setup:

```markdown
## Installation & Setup

### 🪟 Windows Setup
1. **FFmpeg Prerequisite**: Ensure FFmpeg is installed and added to PATH (e.g. `winget install FFmpeg`).
2. **Automated Setup**: Right-click `install.ps1` and select **Run with PowerShell**, or double-click `run.bat`.
3. **Launch Application**: Double-click `run.bat` or the desktop shortcut **S.Q.U.I.N.T. Upscaler**.

### 🐧 Linux Setup
1. **Automated Setup**:
   ```bash
   chmod +x install.sh
   ./install.sh
   ```
2. **Launch Application**:
   ```bash
   ./run.sh
   ```
```

---

## 5. Author Integration Checklist

- [ ] Add `install.ps1`, `run.ps1`, and `run.bat` to root folder.
- [ ] Update `upscaler_engine.py` with `CREATE_NO_WINDOW` and `find_executable`.
- [ ] Normalize paths in `app.py` model scanner.
- [ ] Update `README.md` with Windows installation steps.
- [ ] Test on Windows 10/11 with NVIDIA GPU & CPU fallback modes.
