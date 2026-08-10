@echo off
set SCRIPT_DIR=%~dp0
set VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe

if exist "%VENV_PYTHON%" (
    echo Launching S.Q.U.I.N.T. AI Video Upscaler...
    "%VENV_PYTHON%" "%SCRIPT_DIR%app.py" %*
) else (
    echo Virtual environment not found. Running setup...
    py -3 "%SCRIPT_DIR%install.py" 2>nul || python "%SCRIPT_DIR%install.py"
    if exist "%VENV_PYTHON%" (
        "%VENV_PYTHON%" "%SCRIPT_DIR%app.py" %*
    ) else (
        echo ❌ Setup failed or Python not found. Please install Python 3.10+ from python.org.
        pause
    )
)
