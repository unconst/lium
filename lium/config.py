"""Configuration management for Lium CLI."""

import os
from pathlib import Path
from typing import Optional


def get_api_key() -> Optional[str]:
    """Get the API key from environment variables or config file.
    
    Checks in order:
    1. LIUM_API_KEY environment variable
    2. ~/.lium/config file
    
    Returns:
        API key string if found, None otherwise
    """
    # Check environment variable first
    api_key = os.environ.get("LIUM_API_KEY")
    if api_key:
        return api_key
    
    # Check config file
    config_path = Path.home() / ".lium" / "config"
    if config_path.exists():
        try:
            with open(config_path, "r") as f:
                for line in f:
                    if line.strip().startswith("api_key="):
                        return line.strip().split("=", 1)[1]
        except Exception:
            pass
    
    return None


def save_api_key(api_key: str) -> None:
    """Save the API key to the config file.
    
    Args:
        api_key: The API key to save
    """
    config_dir = Path.home() / ".lium"
    config_dir.mkdir(exist_ok=True)
    
    config_path = config_dir / "config"
    with open(config_path, "w") as f:
        f.write(f"api_key={api_key}\n") 