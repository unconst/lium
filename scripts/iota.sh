
# Install git if not already installed
if ! command -v git &> /dev/null
then
    echo "git could not be found, installing..."
    apt-get update
    apt-get install -y git
else
    echo "git is already installed"
fi

# Install uv if not already installed
if ! command -v uv &> /dev/null
then
    echo "uv could not be found, installing..."
    apt-get update
    apt-get install -y uv
else
    echo "uv is already installed"
fi

rm -rf IOTA
git clone https://github.com/macrocosm-os/IOTA.git
cd IOTA

# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Source uv
source $HOME/.local/bin/env

# Make an env.
uv venv

# Source env
source .venv/bin/activate

# Install bittensor
uv pip install bittensor

# Install bittensor cli
uv pip install bittensor-cli

# Optional - update the bittensor-cli, if a new version is available
uv pip install --upgrade pip

# Install IOTA requirements.
uv sync

if [ ! -f .env ]; then
    echo "Creating .env file with default configurations..."
    cat <<EOL > .env
wallet_name="${COLD}"
MINER_HOTKEYS="${HOT}" 
netuid=9
network="finney"
MOCK=False
BITTENSOR=True
HF_TOKEN="${HF}"
ORCHESTRATOR_HOST="iota.api.macrocosmos.ai"
ORCHESTRATOR_PORT=443
ORCHESTRATOR_SCHEME=https
EOL
    echo ".env file created."
else
    echo ".env file already exists."
fi

source .env

# Launch miner 
python launch_miner.py

