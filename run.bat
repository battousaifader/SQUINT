@echo off
set SCRIPT_DIR=%~dp0
set VENV_PYTHON=%SCRIPT_DIR%.venv\Scripts\python.exe

if exist "%VENV_PYTHON%" (
    echo Launching S.Q.U.I.N.T. AI Video Upscaler...
    "%VENV_PYTHON%" "%SCRIPT_DIR%app.py" %*
) else (
    echo Virtual environment not found. Running setup...
    python "%SCRIPT_DIR%install.py"
    if exist "%VENV_PYTHON%" (
        "%VENV_PYTHON%" "%SCRIPT_DIR%app.py" %*
    )
)
