"""Execute commands on pods via SSH for Lium CLI."""

import click
import shlex
import socket
import sys
import paramiko
from pathlib import Path
from typing import Optional, Tuple

from ..config import get_or_set_api_key, get_config_value
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


@click.command(name="exec", help="Execute a command or a bash script on a running pod via SSH.")
@click.argument("pod_name_huid", type=str)
@click.argument("command_to_run", type=str, required=False)
@click.option("--script", "bash_script_path", type=click.Path(exists=True, dir_okay=False, readable=True), help="Path to a bash script to execute on the pod.")
@click.option("--env", "env_vars", multiple=True, help="Environment variables to set (format: KEY=VALUE). Can be used multiple times.")
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def exec_command(pod_name_huid: str, command_to_run: Optional[str], bash_script_path: Optional[str], env_vars: Tuple[str, ...], api_key: Optional[str]):
    """Executes COMMAND_TO_RUN or the content of the bash script on the pod identified by POD_NAME_HUID.
    
    Environment variables can be set using --env KEY=VALUE (can be used multiple times).
    Example: lium exec pod-name --env MY_VAR=value --env PATH=/custom:$PATH "python script.py"
    """
    if not command_to_run and not bash_script_path:
        console.print(styled("Error: Either COMMAND_TO_RUN or --script <script_path> must be provided.", "error"))
        return
    if command_to_run and bash_script_path:
        console.print(styled("Error: Cannot provide both COMMAND_TO_RUN and --script <script_path>.", "error"))
        return

    final_command_to_run = ""
    operation_description = ""
    
    # Parse and validate environment variables
    env_dict = {}
    if env_vars:
        for env_var in env_vars:
            if '=' not in env_var:
                console.print(styled(f"Error: Invalid environment variable format '{env_var}'. Expected format: KEY=VALUE", "error"))
                return
            key, value = env_var.split('=', 1)  # Split only on first '=' to allow '=' in values
            if not key:
                console.print(styled(f"Error: Empty key in environment variable '{env_var}'", "error"))
                return
            env_dict[key] = value

    if bash_script_path:
        try:
            with open(bash_script_path, 'r') as f:
                script_content = f.read()
            operation_description = f"script '{bash_script_path}'"
            # For scripts, prepend environment variable exports
            if env_dict:
                env_exports = '\n'.join([f'export {key}="{value}"' for key, value in env_dict.items()])
                final_command_to_run = f"{env_exports}\n{script_content}"
            else:
                final_command_to_run = script_content
        except Exception as e:
            console.print(styled(f"Error reading bash script '{bash_script_path}': {str(e)}", "error"))
            return
    elif command_to_run: # Ensure command_to_run is not None, though previous checks should cover this.
        operation_description = f"command: {command_to_run}"
        # For direct commands, prepend environment variable exports
        if env_dict:
            env_exports = ' && '.join([f'export {key}="{value}"' for key, value in env_dict.items()])
            final_command_to_run = f"{env_exports} && {command_to_run}"
        else:
            final_command_to_run = command_to_run
        
        # Add env vars to operation description if present
        if env_dict:
            env_str = ', '.join([f'{k}={v}' for k, v in env_dict.items()])
            operation_description = f"command with env [{env_str}]: {command_to_run}"

    if not final_command_to_run: # Should ideally not be reached if initial checks are correct
        console.print(styled("Error: No command or script content to execute.", "error"))
        return

    if not api_key: api_key = get_or_set_api_key()
    if not api_key: console.print(styled("Error:", "error") + styled(" No API key found.", "primary")); return

    ssh_key_path_str = get_config_value("ssh.key_path").rstrip('.pub')
    if not ssh_key_path_str:
        console.print(styled("Error: SSH key path not configured. Use 'lium config set ssh.key_path /path/to/your/private_key'", "error"))
        return
    
    # Note: paramiko needs the *private* key. get_or_set_ssh_key() was for API.
    # We should guide user to set private key path for `lium exec`.
    # For now, assume ssh.key_path in config IS the private key path for this command.
    # This might require a new config entry like ssh.private_key_path if ssh.key_path is strictly public.
    # Let's assume for now ssh.key_path can be the private key for `exec`.
    private_key_path = Path(ssh_key_path_str).expanduser()
    if not private_key_path.exists():
        console.print(styled(f"Error: SSH private key not found at '{private_key_path}'", "error"))
        console.print(styled("Please ensure 'ssh.key_path' in your Lium config points to your private SSH key for 'lium exec'.", "info"))
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
            console.print(styled(f"Error: Pod with Name (HUID) '{pod_name_huid}' not found among active pods.", "error"))
            return

    except Exception as e: console.print(styled(f"Error fetching active pods: {str(e)}", "error")); return

    ssh_connect_cmd_str = target_pod_info.get("ssh_connect_cmd")
    if not ssh_connect_cmd_str:
        console.print(styled(f"Error: Pod '{pod_name_huid}' has no SSH connection command available.", "error")); return

    # Parse SSH command (e.g., "ssh root@IP -p PORT")
    try:
        parts = shlex.split(ssh_connect_cmd_str)
        # Expected format: ssh user@host -p port
        user_host = parts[1]
        user, host = user_host.split('@')
        port = None
        if "-p" in parts:
            port_index = parts.index("-p") + 1
            if port_index < len(parts):
                port = int(parts[port_index])
        if port is None: port = 22 # Default SSH port
    except Exception as e:
        console.print(styled(f"Error parsing SSH command '{ssh_connect_cmd_str}': {str(e)}", "error"))
        return

    console.print(styled(f"Connecting to '{pod_name_huid}' ({host}:{port} as {user}) to run {operation_description}", "info"))

    ssh_client = None
    try:
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy()) # Automatically add host key
        
        # Attempt to load various key types, fail gracefully
        loaded_key = None
        key_types_to_try = [paramiko.Ed25519Key, paramiko.RSAKey, paramiko.ECDSAKey, paramiko.DSSKey]
        last_key_error = None
        for key_type in key_types_to_try:
            try:
                loaded_key = key_type.from_private_key_file(str(private_key_path))
                break
            except paramiko.ssh_exception.PasswordRequiredException:
                console.print(styled(f"Error: SSH key '{private_key_path}' is encrypted and requires a passphrase. Passphrase input is not supported yet.", "error"))
                return
            except paramiko.ssh_exception.SSHException as e:
                last_key_error = e # Store last error to show if all fail
                continue
        
        if not loaded_key:
            console.print(styled(f"Error: Could not load SSH private key '{private_key_path}'. Ensure it is a valid, unencrypted private key. Last error: {last_key_error}", "error"))
            return

        ssh_client.connect(hostname=host, port=port, username=user, pkey=loaded_key, timeout=10)
        
        stdin, stdout, stderr = ssh_client.exec_command(final_command_to_run, get_pty=True)
        
        # Stream output
        while not stdout.channel.exit_status_ready():
            if stdout.channel.recv_ready():
                data = stdout.channel.recv(1024)
                sys.stdout.write(data.decode(errors='replace'))
                sys.stdout.flush()
            if stderr.channel.recv_ready():
                data = stderr.channel.recv(1024)
                sys.stderr.write(data.decode(errors='replace'))
                sys.stderr.flush()
        
        # Get remaining output
        sys.stdout.write(stdout.read().decode(errors='replace'))
        sys.stderr.write(stderr.read().decode(errors='replace'))
        sys.stdout.flush()
        sys.stderr.flush()

        exit_status = stdout.channel.recv_exit_status()
        if exit_status == 0:
            console.print(styled(f"\nCommand completed on '{pod_name_huid}'. Exit status: {exit_status}", "success"))
        else:
            console.print(styled(f"\nCommand failed on '{pod_name_huid}'. Exit status: {exit_status}", "error"))
        
    except socket.timeout:
        console.print(styled(f"Error: Connection to '{host}:{port}' timed out.", "error"))
    except paramiko.ssh_exception.AuthenticationException:
        console.print(styled(f"Error: Authentication failed for {user}@{host}:{port}. Check your SSH key and permissions.", "error"))
    except paramiko.ssh_exception.SSHException as e:
        console.print(styled(f"Error: SSH connection error to {host}:{port}: {str(e)}", "error"))
    except Exception as e:
        console.print(styled(f"An unexpected error occurred during SSH execution: {str(e)}", "error"))
    finally:
        if ssh_client: ssh_client.close() 