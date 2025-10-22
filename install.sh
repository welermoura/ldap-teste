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

# --- Setup Node.js Environment and Dependencies ---
if [ -d "frontend" ]; then
    echo "[Node.js] Found 'frontend' directory. Setting up Node.js environment..."

    # Check for NVM and .nvmrc
    if [ -s "$NVM_DIR/nvm.sh" ]; then
        source "$NVM_DIR/nvm.sh"
        echo "[Node.js] NVM found. Using version specified in .nvmrc..."
        nvm install
        nvm use
    elif command -v nvm &> /dev/null; then
        echo "[Node.js] NVM found. Using version specified in .nvmrc..."
        nvm install
        nvm use
    else
        echo "[Node.js] Error: NVM (Node Version Manager) is not installed." >&2
        echo "Please install NVM to manage Node.js versions. See: https://github.com/nvm-sh/nvm#installing-and-updating" >&2
        exit 1
    fi

    echo "[Node.js] Using Node version: $(node --version) and npm version: $(npm --version)"

    cd frontend
    echo "[Node.js] Installing dependencies with npm..."
    npm install

    echo "[Node.js] Building frontend application..."
    npm run build

    echo "[Node.js] Frontend setup complete."
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
