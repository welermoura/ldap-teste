#!/bin/bash

# Exit immediately if a command exits with a non-zero status.
set -e

echo "--- Starting Full Environment Setup ---"

# --- Setup Python Virtual Environment ---
echo "[Python] Setting up virtual environment..."
if ! python3 -m venv venv; then
    echo "[Python] Error: Failed to create virtual environment."
    exit 1
fi

# Activate virtual environment
source venv/bin/activate
echo "[Python] Virtual environment activated."

# --- Install/Upgrade Python Dependencies ---
echo "[Python] Upgrading pip..."
pip install --upgrade pip

echo "[Python] Installing/Upgrading dependencies from requirements.txt..."
pip install --upgrade -r requirements.txt

# Deactivate after finishing Python setup
deactivate
echo "[Python] Python setup complete."

# --- Setup Node.js Frontend Dependencies ---
if [ -d "frontend" ]; then
    echo "[Node.js] Found 'frontend' directory. Setting up dependencies..."
    cd frontend

    if command -v npm &> /dev/null; then
        echo "[Node.js] Installing dependencies with npm..."
        npm install
        echo "[Node.js] Frontend setup complete."
    else
        echo "[Node.js] Warning: 'npm' command not found. Skipping frontend dependency installation."
        echo "Please install Node.js and npm to set up the frontend."
    fi

    cd .. # Return to the root directory
else
    echo "[Node.js] 'frontend' directory not found. Skipping frontend setup."
fi

echo ""
echo "--- Full Setup Complete! ---"
echo ""
echo "To run the application, first activate the Python environment:"
echo "source venv/bin/activate"
echo ""
echo "Then, run the Flask application:"
echo "python app.py"
echo "--------------------------------"
