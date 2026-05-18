@echo off
REM ─────────────────────────────────────────────────────────────────────────
REM  SkyDroid C12 Control Center — Windows one-click launcher
REM  Double-click this file on a PC that is on the same LAN as the camera.
REM ─────────────────────────────────────────────────────────────────────────

echo.
echo  ╔══════════════════════════════════════════════╗
echo  ║   SkyDroid C12 Control Center                ║
echo  ║   Requires Python 3.11+ on the camera LAN   ║
echo  ╚══════════════════════════════════════════════╝
echo.

REM Change to the folder this .bat lives in
cd /d "%~dp0"

REM ── Check Python ──────────────────────────────────────────────────────────
where python >nul 2>&1
if errorlevel 1 (
    echo  ERROR: Python not found. Download from https://python.org
    pause
    exit /b 1
)

REM ── Create venv if missing ────────────────────────────────────────────────
if not exist "venv\Scripts\activate.bat" (
    echo  Creating virtual environment ...
    python -m venv venv
)

REM ── Activate + install deps ───────────────────────────────────────────────
call venv\Scripts\activate.bat
echo  Installing / updating dependencies ...
pip install -q -r requirements.txt

REM ── Launch ────────────────────────────────────────────────────────────────
echo.
echo  Starting server on http://localhost:5000
echo  Open that URL in your browser, then use Connection Settings to enable Real Mode.
echo  Press Ctrl+C to stop.
echo.
python app.py

pause
