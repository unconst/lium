"""Configuration management for Lium CLI using an INI file."""

import os
import sys
import configparser
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt 
from typing import Optional, Any, Dict, List, Tuple
import json
from .styles import styled, get_theme

CONFIG_DIR = Path.home() / ".lium"
JSON_CONFIG_FILE = CONFIG_DIR / "config.json"
INI_CONFIG_FILE = CONFIG_DIR / "config.ini"
console = Console(theme=get_theme())

def _ensure_config_dir_exists() -> None:
    """Ensures the ~/.lium directory exists."""
    CONFIG_DIR.mkdir(exist_ok=True)

def _migrate_json_to_ini_if_needed():
    _ensure_config_dir_exists()
    if JSON_CONFIG_FILE.exists() and not INI_CONFIG_FILE.exists():
        # console.print(f"Migrating JSON config to INI format...", err=True) # Quieter for tests
        old_config_data = {}
        try:
            with open(JSON_CONFIG_FILE, "r") as f_json:
                old_config_data = json.load(f_json)
        except Exception: # Silently ignore if old JSON is corrupt, will create fresh INI
            pass # old_config_data remains {}

        config = configparser.ConfigParser()
        migrated_something = False
        for key, value in old_config_data.items():
            if isinstance(value, dict): 
                if key not in config: config.add_section(key) # Ensure section exists
                for sub_key, sub_value in value.items():
                    if sub_value is not None: config[key][sub_key] = str(sub_value); migrated_something = True
            else:
                # Handle api_key specifically
                if key == "api_key":
                    if "api" not in config: config.add_section("api")
                    if value is not None: config["api"][key] = str(value); migrated_something = True
                # Put other top-level keys into [default] or a specific section if preferred.
                # For simplicity, let's assume most other top-level keys from old JSON might be less critical
                # or would need explicit mapping. For now, only api_key gets special section treatment.
                # else: 
                #     if 'DEFAULT' not in config: config['DEFAULT'] = {}
                #     if value is not None: config['DEFAULT'][key] = str(value); migrated_something = True
       
        # Always write an INI file if JSON existed and INI didn't, even if JSON was empty/corrupt
        try:
            with open(INI_CONFIG_FILE, "w") as f_ini:
                config.write(f_ini)
            # if migrated_something: 
            #    console.print("Config migrated to INI. Old JSON can be removed.", err=True)
            # else: 
            #    console.print("Old JSON config found but was empty or unmigratable. Fresh INI created.", err=True)
            # JSON_CONFIG_FILE.rename(JSON_CONFIG_FILE.with_suffix('.json.migrated')) # Optional: auto-rename old file
        except Exception as e:
            # console.print(f"Error writing INI config during migration: {e}", err=True)
            pass # Avoid crashing CLI if migration save fails, next load will be empty

def load_config_parser() -> configparser.ConfigParser:
    """Loads the configuration from the INI file."""
    _ensure_config_dir_exists()
    _migrate_json_to_ini_if_needed()
    config = configparser.ConfigParser()
    if INI_CONFIG_FILE.exists():
        try:
            config.read(INI_CONFIG_FILE)
        except configparser.Error as e:
            print(f"Warning: Error reading INI config file {INI_CONFIG_FILE}: {e}")
            # Return empty config parser on error
            return configparser.ConfigParser()
    return config

def save_config_parser(config: configparser.ConfigParser) -> None:
    """Saves the configuration data to the INI file."""
    _ensure_config_dir_exists()
    with open(INI_CONFIG_FILE, "w") as f:
        config.write(f)

def get_config_value(key: str) -> Optional[str]:
    """Retrieves a value from the INI configuration.
    Dot notation 'section.option' is used for key.
    If no section is provided (no dot), it tries the 'DEFAULT' section.
    If key is 'api_key' and it's not found, it prompts the user and saves it.
    """
    config = load_config_parser()
    if '.' in key:
        section, option = key.split('.', 1)
    else: # Assume DEFAULT section or a predefined section for top-level keys if desired
        if key == "api_key":
            section, option = "api", "api_key"
        else: # Fallback to DEFAULT for other direct keys
            section, option = "DEFAULT", key
    
    value = None
    if config.has_option(section, option):
        value = config.get(section, option)
    # Check DEFAULT section as a fallback if section was specified but option not found
    elif section != 'DEFAULT' and config.has_option('DEFAULT', option):
        value = config.get('DEFAULT', option)

    return value

def set_config_value(key: str, value: Any) -> None:
    """Sets a value in the INI configuration.
    Dot notation 'section.option' is used for key.
    If no section is provided, it writes to the 'DEFAULT' section 
    (or a specific section like 'api' for 'api_key').
    """
    config = load_config_parser()
    if '.' in key:
        section, option = key.split('.', 1)
    else:
        if key == "api_key": 
            section, option = "api", "api_key"
        else:
            section, option = "DEFAULT", key

    if not config.has_section(section) and section != 'DEFAULT':
        config.add_section(section)
    
    config.set(section, option, str(value)) # All INI values are strings
    save_config_parser(config)

def unset_config_value(key: str) -> bool:
    """Removes an option from the INI configuration.
    Dot notation 'section.option' is used for key.
    """
    config = load_config_parser()
    if '.' in key:
        section, option = key.split('.', 1)
    else:
        if key == "api_key": 
            section, option = "api", "api_key"
        else:
            section, option = "DEFAULT", key
            
    if config.has_option(section, option):
        config.remove_option(section, option)
        # If section becomes empty (and not DEFAULT), remove it
        if not config.options(section) and section != 'DEFAULT':
            config.remove_section(section)
        save_config_parser(config)
        return True
    return False

def get_api_key() -> Optional[str]:
    """Gets the API key from environment or config file."""
    return get_config_value("api.api_key")

def get_or_set_api_key() -> Optional[str]:
    """Gets the API key from environment or config file."""
    api_key = get_config_value("api.api_key")
    if api_key == None:
        # This import is local to avoid circular dependencies if config is imported early
        api_key_input = Prompt.ask(
            styled("Please enter your Lium API key (See: https://celiumcompute.ai/api-keys)", "info")
        )
        if api_key_input:
            set_config_value('api.api_key', api_key_input) # set_config_value handles section/option logic
    return get_config_value("api.api_key")

def get_ssh_public_keys() -> List[str]:
    """Reads SSH public key(s).
    It assumes ssh.key_path in config points to the PRIVATE key.
    It will attempt to find the corresponding .pub file.
    If ssh.key_path itself ends with .pub, it will try to read that directly.
    
    Returns:
        A list of public key strings, or an empty list if not found or error.
    """
    private_key_path_str = get_config_value("ssh.key_path")
    if not private_key_path_str:
        # console.print(styled("ssh.key_path not set in config.", "warning")) # Optional user feedback
        return []

    # Determine the public key path
    # Path objects are easier to manipulate for this.
    resolved_private_key_path = Path(private_key_path_str).expanduser()
    public_key_path_to_try: Optional[Path] = None

    if private_key_path_str.endswith(".pub"):
        # User might have directly configured the .pub file path
        public_key_path_to_try = resolved_private_key_path
    else:
        # Assume private_key_path_str is the private key, try to find corresponding .pub
        public_key_path_to_try = resolved_private_key_path.with_suffix(".pub")

    public_keys: List[str] = []
    if public_key_path_to_try and public_key_path_to_try.exists() and public_key_path_to_try.is_file():
        try:
            with open(public_key_path_to_try, "r") as f:
                for line in f:
                    line = line.strip()
                    # Basic validation for an SSH public key line
                    if line and (line.startswith("ssh-") or line.startswith("ecdsa-")):
                        public_keys.append(line)
            if not public_keys:
                # console.print(styled(f"No valid public keys found in {public_key_path_to_try}", "warning"))
                pass # No keys found
        except Exception as e:
            # console.print(styled(f"Error reading public key file {public_key_path_to_try}: {e}", "error"))
            return [] # Error reading file
    else:
        # console.print(styled(f"Public key file not found at {public_key_path_to_try} (derived from ssh.key_path: {private_key_path_str})", "warning"))
        # If .pub doesn't exist, and the original path wasn't a .pub file, then we have no public key to return.
        # If the original path *was* a .pub file but didn't exist, it's also an error handled here.
        pass 
        
    return public_keys

def get_or_set_ssh_key() -> List[str]:
    pubs = get_ssh_public_keys()
    if pubs == None or len(pubs) == 0:
        # This import is local to avoid circular dependencies if config is imported early
        ssh_key_input = Prompt.ask(
            styled("Please enter the path to your ssh private key (i.e.: ~/.ssh/id_rsa)", "info")
        )
        ssh_key_input = os.path.expanduser(ssh_key_input)
        if ssh_key_input:
            set_config_value('ssh.key_path', ssh_key_input) # set_config_value handles section/option logic
            set_config_value('ssh.user', 'root') # set_config_value handles section/option logic
        pubs = get_ssh_public_keys()
        if not pubs:
            console.print(styled(f'Key path: {ssh_key_input}.pub does not exist or is badly formatted.', 'info'))
            sys.exit()
    return get_ssh_public_keys()

def get_docker_credentials() -> Tuple[Optional[str],Optional[str]]:
    return get_config_value("docker.username"), get_config_value("docker.password")

def get_or_set_docker_credentials() -> Tuple[str,str]:
    user, pswd = get_docker_credentials()
    if user == None:
        docker_user = Prompt.ask(styled("Please enter your docker username (i.e.: const123)", "info"))
        set_config_value('docker.username', docker_user) # set_config_value handles section/option logic
    if pswd == None:
        docker_pwsd = Prompt.ask(styled("Please enter your docker access token (i.e.: dckr_pat_FUDINADNKSLvJZVMEdCLDMqa1FCIE)", "info"))
        set_config_value('docker.password', docker_pwsd) # set_config_value handles section/option logic
    return get_docker_credentials()    

def get_config_path() -> Path:
    """Returns the path to the configuration file."""
    return INI_CONFIG_FILE 