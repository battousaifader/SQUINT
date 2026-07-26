#!/usr/bin/env python3
import os
import sys
import subprocess
import venv
import shutil
from pathlib import Path

print("==========================================")
print(" S.Q.U.I.N.T. Universal Environment Setup ")
print("==========================================")

script_dir = Path(__file__).parent.resolve()
venv_dir = script_dir / ".venv"

# 1. OS Detection
is_win = sys.platform == 'win32'
print(f"🖥️ Detected OS: {'Windows' if is_win else 'Linux/Unix'}")

# 2. FFmpeg Check
ffmpeg_cmd = shutil.which("ffmpeg")
if not ffmpeg_cmd:
    print("⚠️ Warning: 'ffmpeg' is not found on PATH. Video processing will fail.")
    if is_win:
        print("   -> Install via Winget: winget install FFmpeg")
    else:
        print("   -> Install via APT: sudo apt install ffmpeg")
else:
    print("✅ Found FFmpeg executable.")

ffprobe_cmd = shutil.which("ffprobe")
if not ffprobe_cmd:
    print("⚠️ Warning: 'ffprobe' is not found on PATH. Video probing will fail.")
else:
    print("✅ Found FFprobe executable.")

# 3. Create Virtual Environment
if not venv_dir.exists():
    print("📦 Creating virtual environment in .venv...")
    builder = venv.EnvBuilder(with_pip=True)
    builder.create(venv_dir)
else:
    print("📦 Existing virtual environment found in .venv")

# Determine venv python path
if is_win:
    venv_python = venv_dir / "Scripts" / "python.exe"
    venv_pip = venv_dir / "Scripts" / "pip.exe"
else:
    venv_python = venv_dir / "bin" / "python3"
    venv_pip = venv_dir / "bin" / "pip"

if not venv_python.exists():
    print("❌ Virtual environment Python not found. Setup failed.")
    sys.exit(1)

# 4. Install Dependencies
print("📥 Installing dependencies...")
subprocess.run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])

if is_win:
    # Windows: Attempt CUDA install
    print("🚀 Installing PyTorch for Windows (CUDA 12.1)...")
    subprocess.run([str(venv_python), "-m", "pip", "install", "torch", "torchvision", "--index-url", "https://download.pytorch.org/whl/cu121"])
    subprocess.run([str(venv_python), "-m", "pip", "install", "PySide6>=6.5.0", "numpy", "psutil"])
else:
    # Linux/Mac: Use requirements.txt
    print("ℹ️ Installing standard dependencies from requirements.txt...")
    req_file = script_dir / "requirements.txt"
    subprocess.run([str(venv_python), "-m", "pip", "install", "-r", str(req_file)])

# 5. Create Desktop Shortcut
if not is_win:
    # Linux Desktop Entry
    desktop_dir = Path.home() / ".local" / "share" / "applications"
    if desktop_dir.exists():
        desktop_file = desktop_dir / "ai-video-upscaler.desktop"
        print(f"🖥️ Creating Desktop Launcher at {desktop_file}...")
        with open(desktop_file, "w") as f:
            f.write(f"""[Desktop Entry]
Type=Application
Name=S.Q.U.I.N.T. Video Upscaler
Comment=PyTorch & PySide6 GPU Video Upscaling
Exec={script_dir}/run.sh
Icon=video-x-generic
Terminal=false
Categories=AudioVideo;Video;Graphics;
""")
        desktop_file.chmod(0o755)
        print("✅ Linux desktop launcher created!")
else:
    # Windows Shortcut (VBS script approach to avoid extra dependencies)
    desktop_dir = Path.home() / "Desktop"
    shortcut_path = desktop_dir / "S.Q.U.I.N.T. Upscaler.lnk"
    vbs_script = script_dir / "create_shortcut.vbs"
    
    with open(vbs_script, "w") as f:
        f.write(f'''
Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{script_dir / 'run.bat'}"
oLink.WorkingDirectory = "{script_dir}"
oLink.Description = "S.Q.U.I.N.T. AI Video Upscaler"
oLink.Save
''')
    try:
        subprocess.run(["cscript", "//nologo", str(vbs_script)])
        print("✅ Windows desktop shortcut created!")
    except Exception as e:
        print("⚠️ Could not create Windows shortcut automatically.")
    finally:
        if vbs_script.exists():
            vbs_script.unlink()

print("\n==========================================")
print("🎉 Setup complete! You can start S.Q.U.I.N.T. using:")
if is_win:
    print("   run.bat")
else:
    print("   ./run.sh")
print("==========================================")
