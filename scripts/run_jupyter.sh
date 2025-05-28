# Make the script robust by exiting on errors and handling pipe failures
set -e
set -o pipefail

echo "--- Starting JupyterLab Setup and Execution ---"
echo ""
echo "STEP 1: Installing uv (Python package manager and resolver)"
echo "Downloading and executing uv installation script from astral.sh..."
# The -L follows redirects, -s is silent, -S shows errors, -f fails on HTTP errors.
curl -LsSf https://astral.sh/uv/install.sh | sh
echo "uv installation script completed."
echo "--------------------------------------------------"
echo ""

echo "STEP 2: Configuring uv environment for the current session"
# The uv installer script typically installs uv to $HOME/.local/bin
# and provides an environment file to source for the current session.
UV_ENV_FILE="$HOME/.local/bin/env"
if [ -f "$UV_ENV_FILE" ]; then
    source "$UV_ENV_FILE"
    echo "Sourced uv environment from $UV_ENV_FILE."
else
    echo "Warning: uv environment file ($UV_ENV_FILE) not found."
    # Fallback: Attempt to add common uv installation paths to PATH.
    if [ -d "$HOME/.local/bin" ]; then
        export PATH="$HOME/.local/bin:$PATH"
        echo "Added $HOME/.local/bin to PATH."
    fi
    # Also check for cargo-installed uv, as it's another common method
    if [ -d "$HOME/.cargo/bin" ]; then
        export PATH="$HOME/.cargo/bin:$PATH"
        echo "Added $HOME/.cargo/bin to PATH."
    fi
fi

# Verify that the uv command is now available
if ! command -v uv &> /dev/null; then
    echo "ERROR: uv command not found after attempting to configure PATH."
    echo "Please ensure uv is installed correctly and its location is added to your PATH."
    exit 1
fi
echo "uv is available in PATH."
echo "uv version: $(uv --version)"
echo "--------------------------------------------------"
echo ""

echo "STEP 3: Creating Python virtual environment '.venv' using uv"
# Using --seed tells uv to use pip to install seed packages (pip, setuptools, wheel)
uv venv .venv --seed
echo "Python virtual environment '.venv' created or updated successfully."
echo "--------------------------------------------------"
echo ""

echo "STEP 4: Activating the virtual environment"
source .venv/bin/activate
echo "Virtual environment '.venv' activated."
echo "--------------------------------------------------"
echo ""

echo "STEP 5: Installing JupyterLab and required extensions into the virtual environment"
# Using uv pip to install JupyterLab.
uv pip install jupyterlab
echo "JupyterLab core installed successfully."

echo "Installing additional JupyterLab extensions (jupyter-archive, nbclassic, jupyter_nbextensions_configurator)..."
uv pip install jupyter-archive nbclassic jupyter_nbextensions_configurator
echo "JupyterLab extensions installed successfully."
echo "--------------------------------------------------"

PORT=20000
EXPORT=59391
TOKEN=$(openssl rand -base64 37 | tr -dc 'a-zA-Z0-9' | head -c 50)
# TOKEN='NSCDu3W4c9EkvoEOlYH93kBJ7ABjWoqcD252XgID4Jqu1Ng'
# Run JupyterLab using nohup
nohup jupyter lab --ip=0.0.0.0 --port=$PORT --no-browser --allow-root --NotebookApp.token="$TOKEN" &

EXTERNAL_IP=$(curl -s ifconfig.me)
echo ""
echo ""
echo "--------------------------------------------------"
echo "Access your Jupyter notebook on the following url: "
echo ""
echo "           http://$EXTERNAL_IP:$EXPORT/lab?token=$TOKEN"
echo ""
echo "--------------------------------------------------"
echo ""
echo ""

