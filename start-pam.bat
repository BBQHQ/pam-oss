@echo off
REM Double-click this file to start PAM. It activates the virtual
REM environment, launches the app, and keeps the window open if
REM something crashes so you can read the error.

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [PAM] No virtual environment found at .venv\
    echo [PAM] Run through the install steps in README.md first.
    pause
    exit /b 1
)

call .venv\Scripts\activate.bat
python -m app.main

echo.
echo [PAM] Server stopped. Press any key to close this window.
pause >nul
