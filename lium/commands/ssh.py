"""SSH to pods command for Lium CLI."""

import click
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from ..config import get_or_set_api_key, get_config_value
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


@click.command(name="ssh", help="Open an interactive SSH session to a running pod.")
@click.argument("pod_name_huid", type=str)
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def ssh_command(pod_name_huid: str, api_key: Optional[str]):
    """Opens an interactive SSH session to the pod identified by POD_NAME_HUID."""
    if not shutil.which("ssh"): # Check if ssh client is installed/in PATH
        console.print(styled("Error: 'ssh' command not found in your system PATH. Please install an SSH client.", "error"))
        return

    if not api_key: api_key = get_or_set_api_key()
    if not api_key: console.print(styled("Error:", "error") + styled(" No API key found.", "primary")); return

    private_key_path_str = get_config_value("ssh.key_path").rstrip('.pub')
    if not private_key_path_str:
        console.print(styled("Error: SSH private key path not configured. Use 'lium config set ssh.key_path /path/to/your/private_key'", "error"))
        return
    
    private_key_path = Path(private_key_path_str).expanduser()
    if not private_key_path.exists():
        console.print(styled(f"Error: Configured SSH private key not found at '{private_key_path}'", "error"))
        return

    client = LiumAPIClient(api_key)
    target_pod_info = None

    try:
        active_pods = client.get_pods()
        if not active_pods: console.print(styled("No active pods found.", "info")); return

        for pod in active_pods:
            current_pod_id = pod.get("id")
            if not current_pod_id: continue
            current_huid = generate_human_id(current_pod_id)
            if current_huid == pod_name_huid.lower():
                target_pod_info = pod
                break
        
        if not target_pod_info:
            console.print(styled(f"Error: Pod with Name (HUID) '{pod_name_huid}' not found or not active.", "error"))
            return

    except Exception as e: console.print(styled(f"Error fetching active pods: {str(e)}", "error")); return

    ssh_connect_cmd_str = target_pod_info.get("ssh_connect_cmd")
    if not ssh_connect_cmd_str:
        console.print(styled(f"Error: Pod '{pod_name_huid}' has no SSH connection command available (it might not be fully RUNNING).", "error")); return

    # Parse original SSH command to extract user, host, port, and other options
    try:
        original_parts = shlex.split(ssh_connect_cmd_str)
        # Example: ssh user@host -p 12345 -o SomeOption=value
        if original_parts[0].lower() != 'ssh':
            raise ValueError("Not a valid ssh command string")

        user_host_part = original_parts[1]
        user, host = user_host_part.split('@')
        
        port = "22" # Default SSH port
        other_options = []
        i = 2
        while i < len(original_parts):
            if original_parts[i] == '-p' and (i + 1) < len(original_parts):
                port = original_parts[i+1]
                i += 2
            else:
                other_options.append(original_parts[i])
                i += 1

    except Exception as e:
        console.print(styled(f"Error parsing provided SSH command '{ssh_connect_cmd_str}': {str(e)}", "error"))
        return

    # Construct the new SSH command with the configured private key
    ssh_command_list = [
        "ssh",
        "-i", str(private_key_path),
        "-p", port,
    ]
    ssh_command_list.extend(other_options) # Add any other options from original command
    ssh_command_list.append(f"{user}@{host}")

    console.print(styled(f"Attempting SSH connection for '{pod_name_huid}':", "info"))
    console.print(styled(f"  Executing: {' '.join(ssh_command_list)}", "dim"))
    
    try:
        # Using subprocess.run will wait for the command to complete.
        # For an interactive SSH session, this effectively hands over terminal control.
        process = subprocess.run(ssh_command_list, check=False) # check=False to handle non-zero exit codes manually if needed
        if process.returncode != 0:
            console.print(styled(f"SSH session for '{pod_name_huid}' ended with exit code {process.returncode}.", "warning" if process.returncode != 255 else "info" )) # 255 often means connection closed by remote or failure
        # No specific success message needed as user controls the session.
    except FileNotFoundError:
        console.print(styled("Error: 'ssh' command not found. Is it installed and in your PATH?", "error"))
    except Exception as e:
        console.print(styled(f"Error executing SSH command: {str(e)}", "error")) 