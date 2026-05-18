#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
#  SkyDroid C12 Control Center — macOS / Linux one-click launcher
#  Run this script on a machine that is on the SAME network as the camera.
#  Usage:  chmod +x run_local.sh && ./run_local.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e
cd "$(dirname "$0")"

echo ""
echo "  ╔══════════════════════════════════════════════╗"
echo "  ║   SkyDroid C12 Control Center                ║"
echo "  ║   Requires Python 3.11+ on the camera LAN   ║"
echo "  ╚══════════════════════════════════════════════╝"
echo ""

# ── Find Python ──────────────────────────────────────────────────────────────
PYTHON=""
for cmd in python3.11 python3 python; do
    if command -v "$cmd" &>/dev/null; then
        PYTHON="$cmd"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo "  ERROR: Python 3.11+ not found. Install from https://python.org"
    exit 1
fi

echo "  Using: $($PYTHON --version)"

# ── Virtual environment ───────────────────────────────────────────────────────
if [ ! -f "venv/bin/activate" ]; then
    echo "  Creating virtual environment ..."
    $PYTHON -m venv venv
fi

source venv/bin/activate
echo "  Installing / updating dependencies ..."
pip install -q -r requirements.txt

# ── Launch ────────────────────────────────────────────────────────────────────
echo ""
echo "  Starting server on http://localhost:5000"
echo "  Open that URL in your browser, then scroll to Connection Settings"
echo "  to switch from Mock Mode to Real Mode."
echo "  Press Ctrl+C to stop."
echo ""

python app.py
