"""Configuration management for Lium CLI using a JSON file."""

import os
import json
from pathlib import Path
from typing import Optional, Any, Dict, List

CONFIG_DIR = Path.home() / ".lium"
CONFIG_FILE = CONFIG_DIR / "config.json"

# Define default structure and known keys to help with validation/suggestions later
DEFAULT_CONFIG_STRUCTURE = {
    "api_key": None,
    "ssh": {
        "key_path": None,
        "user": None # Example of a future nested key
    },
}

def _ensure_config_dir_exists() -> None:
    """Ensures the ~/.lium directory exists."""
    CONFIG_DIR.mkdir(exist_ok=True)

def load_config() -> Dict[str, Any]:
    """Loads the configuration from the JSON file.

    Returns:
        A dictionary representing the configuration, or an empty dict if not found/error.
    """
    _ensure_config_dir_exists()
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except json.JSONDecodeError:
            # Handle corrupted JSON file, perhaps by logging and returning default or empty
            return {}
        except Exception:
            return {} # Fallback for other read errors
    return {}

def save_config(config_data: Dict[str, Any]) -> None:
    """Saves the configuration data to the JSON file.

    Args:
        config_data: The configuration dictionary to save.
    """
    _ensure_config_dir_exists()
    with open(CONFIG_FILE, "w") as f:
        json.dump(config_data, f, indent=4)

def get_config_value(key: str) -> Any:
    """Retrieves a value from the configuration using dot notation for nested keys.

    Args:
        key: The key to retrieve (e.g., 'api_key', 'ssh.key_path').

    Returns:
        The value if found, else None.
    """
    config = load_config()
    parts = key.split('.')
    current_level = config
    for part in parts:
        if isinstance(current_level, dict) and part in current_level:
            current_level = current_level[part]
        else:
            return None
    return current_level

def set_config_value(key: str, value: Any) -> None:
    """Sets a value in the configuration using dot notation for nested keys.

    Args:
        key: The key to set (e.g., 'api_key', 'ssh.key_path').
        value: The value to set.
    """
    config = load_config()
    parts = key.split('.')
    current_level = config
    
    for i, part in enumerate(parts[:-1]):
        if part not in current_level or not isinstance(current_level[part], dict):
            current_level[part] = {}
        current_level = current_level[part]
    
    current_level[parts[-1]] = value
    save_config(config)

def unset_config_value(key: str) -> bool:
    """Removes a key (and its value) from the configuration.

    Args:
        key: The key to unset (e.g., 'api_key', 'ssh.key_path').

    Returns:
        True if the key was found and removed, False otherwise.
    """
    config = load_config()
    parts = key.split('.')
    current_level = config
    
    for i, part in enumerate(parts[:-1]):
        if part not in current_level or not isinstance(current_level[part], dict):
            return False # Key path does not exist
        current_level = current_level[part]
    
    if parts[-1] in current_level:
        del current_level[parts[-1]]
        save_config(config)
        return True
    return False

def get_api_key() -> Optional[str]:
    """Gets the API key from environment or config file."""
    env_api_key = os.environ.get("LIUM_API_KEY")
    if env_api_key:
        return env_api_key
    return get_config_value("api_key")

def save_api_key(api_key: str) -> None: # Kept for compatibility if direct use is needed
    """Saves just the API key. Consider using set_config_value for general config.
    This will now save it under the 'api_key' field in the JSON config.
    """
    set_config_value("api_key", api_key)

def get_ssh_public_keys() -> List[str]:
    """Reads SSH public key(s) from the path specified in the config.
    
    Returns:
        A list of public key strings, or an empty list if not found or error.
    """
    key_path_str = get_config_value("ssh.key_path")
    if not key_path_str:
        return []

    key_path = Path(key_path_str).expanduser()
    public_keys: List[str] = []

    if not key_path.exists():
        # Attempt to find .pub if a private key path might have been given
        if not key_path_str.endswith(".pub"):
            pub_key_path_try = Path(f"{key_path_str}.pub").expanduser()
            if pub_key_path_try.exists():
                key_path = pub_key_path_try
            else:
                return [] # Neither original nor .pub path exists
        else:
             return [] # .pub path given but does not exist
    
    try:
        with open(key_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    public_keys.append(line)
    except Exception:
        # Log error or handle appropriately
        return []
    return public_keys

def get_config_path() -> Path:
    """Returns the path to the configuration file."""
    return CONFIG_FILE 