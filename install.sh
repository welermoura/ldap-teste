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

    # Preferred method: Use NVM if available
    # NVM sourced from standard install paths
    if [ -s "$NVM_DIR/nvm.sh" ]; then
        echo "[Node.js] NVM found. Using version specified in .nvmrc..."
        source "$NVM_DIR/nvm.sh"
        nvm install
        nvm use
    elif command -v nvm &> /dev/null; then
        echo "[Node.js] NVM found. Using version specified in .nvmrc..."
        nvm install
        nvm use
    else
        # Fallback method: Check system-wide Node.js version
        echo "[Node.js] NVM not found. Checking for a compatible system-wide Node.js version..."

        if ! command -v node &> /dev/null; then
            echo "[Node.js] Error: Node.js is not installed and NVM is not available." >&2
            echo "Please install NVM (recommended: https://github.com/nvm-sh/nvm) or a compatible version of Node.js manually." >&2
            exit 1
        fi

        NODE_VERSION=$(node -v)
        NODE_MAJOR_VERSION=$(echo "$NODE_VERSION" | cut -d'v' -f2 | cut -d'.' -f1)
        REQUIRED_MAJOR_VERSION=$(cat .nvmrc)

        if [ "$NODE_MAJOR_VERSION" -lt "$REQUIRED_MAJOR_VERSION" ]; then
            echo "[Node.js] Error: Your system's Node.js version ($NODE_VERSION) is not compatible." >&2
            echo "Vite requires Node.js version $REQUIRED_MAJOR_VERSION+. Please upgrade your Node.js version or install NVM." >&2
            exit 1
        else
            echo "[Node.js] System Node.js version ($NODE_VERSION) is compatible. Proceeding..."
        fi
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
