#!/bin/bash
set -e

echo "============================================"
echo " Camai - Perimeter Intrusion Detection System"
echo " Setup Script"
echo "============================================"

# 1. Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 is not installed. Please install Python 3.10 or higher."
    exit 1
fi

echo "[1/4] Creating virtual environment..."
python3 -m venv .venv

echo "[2/4] Activating virtual environment..."
source .venv/bin/activate

echo "[3/4] Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "[4/4] Setup complete!"
echo ""
echo "To start the system, run:"
echo "  source .venv/bin/activate"
echo "  python app.py"
echo ""
echo "Then open your browser to http://localhost:8000"
