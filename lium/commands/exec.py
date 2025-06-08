"""Execute commands on pods via SSH for Lium CLI."""

import sys
import click
import shlex
import socket
import paramiko
from pathlib import Path
from typing import Optional, Tuple

from ..config import get_or_set_api_key, get_config_value
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


@click.command(name="exec", help="Execute a command or a bash script on a running pod via SSH.")
@click.argument("pod_targets", type=str, required=True)
@click.argument("command_to_run", type=str, required=False)
@click.option("--script", "-s", "--scripts", "bash_script_path", type=click.Path(exists=True, dir_okay=False, readable=True), help="Path to a bash script to execute on the pod.")
@click.option("--env", '-e', "env_vars", multiple=True, help="Environment variables to set (format: KEY=VALUE). Can be used multiple times.")
@click.option("-k", "--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def exec_command(pod_targets: str, command_to_run: Optional[str], bash_script_path: Optional[str], env_vars: Tuple[str, ...], api_key: Optional[str]):
    """Executes COMMAND_TO_RUN or the content of the bash script on pod(s) identified by POD_TARGETS.
    
    POD_TARGETS should be a single argument that can contain:
    - Pod names/HUIDs: zesty-orbit-08
    - Index numbers from 'lium ps': 1 (or comma-separated: 1,2,3)
    - Comma-separated: 1,2,3 or 1,zesty-orbit-08
    - All pods: all
    
    Environment variables can be set using --env KEY=VALUE (can be used multiple times).
    Example: lium exec 1,2 --env MY_VAR=value "python script.py"
    Example: lium exec all "nvidia-smi"
    """
    if not command_to_run and not bash_script_path:
        console.print(styled("Error: Either COMMAND_TO_RUN or --script <script_path> must be provided.", "error"))
        return
    if command_to_run and bash_script_path:
        console.print(styled("Error: Cannot provide both COMMAND_TO_RUN and --script <script_path>.", "error"))
        return

    if not api_key: api_key = get_or_set_api_key()
    if not api_key: console.print(styled("Error:", "error") + styled(" No API key found.", "primary")); return

    client = LiumAPIClient(api_key)
    
    # Resolve pod targets using the new helper function
    pod_targets_list = tuple(target.strip() for target in pod_targets.split(',') if target.strip())
    resolved_pods, error_msg = resolve_pod_targets(client, pod_targets_list)
    
    if error_msg:
        console.print(styled(f"Error: {error_msg}", "error"))
        if not resolved_pods:
            return
        else:
            console.print(styled("Continuing with resolved pods...", "warning"))
    
    if not resolved_pods:
        console.print(styled("No valid pods to execute on.", "error"))
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

    ssh_key_path_str = get_config_value("ssh.key_path").rstrip('.pub')
    if not ssh_key_path_str:
        console.print(styled("Error: SSH key path not configured. Use 'lium config set ssh.key_path /path/to/your/private_key'", "error"))
        return
    
    private_key_path = Path(ssh_key_path_str).expanduser()
    if not private_key_path.exists():
        console.print(styled(f"Error: SSH private key not found at '{private_key_path}'", "error"))
        console.print(styled("Please ensure 'ssh.key_path' in your Lium config points to your private SSH key for 'lium exec'.", "info"))
        return

    # Show what we're about to execute
    console.print(styled(f"\nExecuting {operation_description} on {len(resolved_pods)} pod(s):", "info"))
    for pod, original_ref in resolved_pods:
        pod_huid = generate_human_id(pod.get("id", ""))
        console.print(styled(f"  - {pod_huid} ({original_ref})", "dim"))
    console.print()

    # Execute on each pod
    success_count = 0
    failure_count = 0
    
    for pod, original_ref in resolved_pods:
        pod_huid = generate_human_id(pod.get("id", ""))
        
        ssh_connect_cmd_str = pod.get("ssh_connect_cmd")
        if not ssh_connect_cmd_str:
            console.print(styled(f"⚠️  Pod '{pod_huid}' ({original_ref}) has no SSH connection command available.", "warning"))
            failure_count += 1
            continue

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
            console.print(styled(f"⚠️  Error parsing SSH command for '{pod_huid}' ({original_ref}): {str(e)}", "warning"))
            failure_count += 1
            continue

        console.print(styled(f"🔗 Connecting to '{pod_huid}' ({original_ref}) at {host}:{port} as {user}...", "info"))

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
                    console.print(styled(f"⚠️  SSH key '{private_key_path}' is encrypted and requires a passphrase.", "warning"))
                    failure_count += 1
                    break
                except paramiko.ssh_exception.SSHException as e:
                    last_key_error = e # Store last error to show if all fail
                    continue
            
            if not loaded_key:
                console.print(styled(f"⚠️  Could not load SSH private key for '{pod_huid}' ({original_ref}). Last error: {last_key_error}", "warning"))
                failure_count += 1
                continue

            ssh_client.connect(hostname=host, port=port, username=user, pkey=loaded_key, timeout=10)
            
            stdin, stdout, stderr = ssh_client.exec_command(final_command_to_run, get_pty=True)
            
            # For multiple pods, we'll show a header for each pod's output
            if len(resolved_pods) > 1:
                console.print(styled(f"\n--- Output from {pod_huid} ({original_ref}) ---", "header"))
            
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
                console.print(styled(f"✅ Command completed successfully on '{pod_huid}' ({original_ref})", "success"))
                success_count += 1
            else:
                console.print(styled(f"❌ Command failed on '{pod_huid}' ({original_ref}) with exit status: {exit_status}", "error"))
                failure_count += 1
            
        except socket.timeout:
            console.print(styled(f"⚠️  Connection to '{pod_huid}' ({original_ref}) timed out.", "warning"))
            failure_count += 1
        except paramiko.ssh_exception.AuthenticationException:
            console.print(styled(f"⚠️  Authentication failed for '{pod_huid}' ({original_ref}). Check your SSH key and permissions.", "warning"))
            failure_count += 1
        except paramiko.ssh_exception.SSHException as e:
            console.print(styled(f"⚠️  SSH connection error to '{pod_huid}' ({original_ref}): {str(e)}", "warning"))
            failure_count += 1
        except Exception as e:
            console.print(styled(f"⚠️  Unexpected error with '{pod_huid}' ({original_ref}): {str(e)}", "warning"))
            failure_count += 1
        finally:
            if ssh_client: ssh_client.close()
        
        # Add a separator between pods if executing on multiple
        if len(resolved_pods) > 1:
            console.print()

    # Summary
    console.print(styled(f"\n📊 Execution Summary: {success_count} successful, {failure_count} failed", "info")) 