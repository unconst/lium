# Lium CLI

A command-line interface for managing Lium compute executors with beautiful Solarized color themes.

## Features

- 🎨 **Solarized Color Themes**: Beautiful dark and light themes based on the Solarized color palette
- 📊 **Rich Display**: Elegant tables and panels for executor information
- 🔄 **Theme Switching**: Switch between dark and light themes on the fly
- 🔑 **Flexible Authentication**: Multiple ways to manage API keys
- 🐍 **Python API**: Use the client library directly in your Python code
- 🔍 **Interactive Browsing**: Drill down from GPU type summary to detailed executor listings

## Installation

Install using [uv](https://github.com/astral-sh/uv):

```bash
# Clone the repository
git clone <your-repo-url>
cd lium

# Install with uv
uv pip install -e .
```

Or install directly with pip:

```bash
pip install -e .
```

## Configuration

Before using the CLI, you need to set your API key. You can do this in one of three ways:

### 1. Environment Variable

```bash
export LIUM_API_KEY="your-api-key-here"
```

### 2. Config Command

```bash
lium config set-api-key "your-api-key-here"
```

This will save the API key to `~/.lium/config`.

### 3. Command Line Option

```bash
lium ls --api-key "your-api-key-here"
```

## Usage

### List Available Executors

The `lium ls` command now provides an interactive two-stage view:

```bash
lium ls
```

#### Stage 1: GPU Type Summary
First, you'll see a summary table showing:
- **GPU Type**: Model number (e.g., 4090, H100, A100)
- **Min $/GPU/Hour**: Lowest price per GPU for this type
- **Max $/GPU/Hour**: Highest price per GPU (or "-" if all same price)
- **Available**: Total number of GPUs of this type

#### Stage 2: Detailed View
After viewing the summary, you can:
- Enter a GPU type (e.g., "4090", "H100") to see all executors with that GPU
- Press Enter to exit

The detailed view shows:
- **Configuration**: Number of GPUs (e.g., 8x4090)
- **$/GPU/Hour**: Price per individual GPU
- **Country**: Location of the executor
- **Storage**: Available disk space in GB
- **Bandwidth**: Upload/download speeds in Mbps

### Theme Switching

The CLI uses Solarized Dark theme by default. You can switch between themes:

```bash
# Switch to light theme
lium theme light

# Switch back to dark theme
lium theme dark
```

## Styling System

Lium uses a comprehensive styling toolkit based on Solarized colors. The styling system provides:

- Consistent color scheme across all commands
- Semantic color usage (success=green, error=red, etc.)
- Beautiful tables with alternating row backgrounds
- Styled panels and borders
- Syntax highlighting for code output

### Using the Style Toolkit in Your Code

```python
from lium.display import StyledConsole

# Create a styled console
console = StyledConsole()

# Print styled messages
console.print_success("Operation completed successfully")
console.print_error("An error occurred")
console.print_warning("This is a warning")
console.print_info("Information message")

# Print key-value pairs
console.print_key_value("Status", "Active")
console.print_key_value("Price", "$0.50/hour")

# Create styled panels
panel = console.create_panel(
    "Panel content here",
    title="Panel Title",
    box_style="rounded"  # or "heavy", "double"
)
```

## Python API Usage

You can also use the Lium API client directly in Python:

```python
from lium.api import LiumAPIClient
from lium.config import get_api_key

# Get API key from environment or config
api_key = get_api_key()

# Or use your API key directly
api_key = "your-api-key-here"

# Create client
client = LiumAPIClient(api_key)

# Get all executors
executors = client.get_executors()

# Filter executors with specific GPUs
rtx_4090_executors = [
    e for e in executors 
    if "RTX 4090" in e.get("machine_name", "")
]

# Find cheapest executor
cheapest = min(executors, key=lambda x: x.get("price_per_hour", float('inf')))
print(f"Cheapest executor: {cheapest['machine_name']} at ${cheapest['price_per_hour']}/hour")
```

## Development

To set up a development environment:

```bash
# Create a virtual environment with uv
uv venv

# Install in development mode
uv pip install -e .
```

## License

[Your License Here]
