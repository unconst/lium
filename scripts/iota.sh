# Install git if not already installed
if ! command -v git &> /dev/null
then
    echo "git could not be found, installing..."
    sudo apt-get update
    sudo apt-get install -y git
else
    echo "git is already installed"
fi

# Install uv if not already installed
if ! command -v uv &> /dev/null
then
    echo "uv could not be found, installing..."
    sudo apt-get update
    sudo apt-get install -y uv
else
    echo "uv is already installed"
fi

git clone https://github.com/macrocosm-os/IOTA.git
cd IOTA

# Make an env.
uv venv

# Source env
source .venv/bin/activate

# Install bittensor
uv pip install bittensor

# Install bittensor cli
uv pip install bittensor-cli

# Optional - update the bittensor-cli, if a new version is available
uv python -m pip install --upgrade pip

# Install IOTA requirements.
uv pip install -e .

