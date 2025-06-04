"""Sync directories with pods via rsync for Lium CLI."""

import click
import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Optional, List, Tuple

from ..config import get_or_set_api_key, get_config_value
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


@click.command(name="rsync", help="Sync directories with running pods using rsync.")
@click.argument("source", type=str, required=True)
@click.argument("destination", type=str, required=True) 
@click.option(
    "--delete",
    is_flag=True,
    help="Delete extraneous files from destination dirs (use with caution)."
)
@click.option(
    "--exclude",
    type=str,
    multiple=True,
    help="Exclude files matching pattern. Can be used multiple times."
)
@click.option(
    "--dry-run", "-n",
    is_flag=True,
    help="Show what would be transferred without making changes."
)
@click.option(
    "--archive", "-a",
    is_flag=True,
    default=True,
    help="Archive mode (preserves permissions, times, etc). Enabled by default."
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    help="Extra verbose rsync output (shows transfer details and statistics)."
)
@click.option(
    "--compress", "-z", 
    is_flag=True,
    help="Compress file data during the transfer."
)
@click.option(
    "--quiet", "-q",
    is_flag=True,
    help="Suppress rsync output (silent operation)."
)
@click.option(
    "--retry-attempts",
    type=int,
    default=3,
    help="Number of retry attempts on failure (default: 3)."
)
@click.option(
    "--progress",
    is_flag=True,
    help="Show progress during transfer."
)
@click.option("-k", "--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def rsync_command(
    source: str,
    destination: str,
    delete: bool,
    exclude: tuple,
    dry_run: bool,
    archive: bool,
    verbose: bool,
    compress: bool,
    quiet: bool,
    retry_attempts: int,
    progress: bool,
    api_key: Optional[str],
):
    """
    Sync directories with pod(s) using rsync.

    SOURCE and DESTINATION can be:
    - Local paths: /path/to/dir/, ~/myproject/
    - Remote paths: pod_targets:/path/to/dir/
    
    POD_TARGETS in remote paths can be:
    - Pod names/HUIDs: zesty-orbit-08:/path/
    - Index numbers from 'lium ps': 1:/path/, 2:/path/
    - Comma-separated: 1,2:/path/ (syncs with multiple pods)
    - All pods: all:/path/

    Examples:
    - lium rsync ~/project/ 1,2:/home/project/     (local to multiple pods)
    - lium rsync 1:/home/project/ ~/backup/       (pod to local)
    - lium rsync all:/home/logs/ ~/collected/     (all pods to local)
    - lium rsync ~/data/ all:/workspace/ --delete --exclude '*.tmp'

    Files being transferred are shown by default. Use --quiet for silent operation,
    or --verbose for extra details and statistics.

    Note: Always end directory paths with / to sync contents, not the directory itself.
    """
    
    # Utility functions
    def q_remote(p: str) -> str:
        """Quote for remote shell – keep ~ unquoted so it expands to $HOME."""
        return p if p.startswith("~") else shlex.quote(p)
    
    def parse_remote_path(path: str) -> Tuple[Optional[str], str]:
        """Parse pod_targets:path format. Returns (pod_targets, path) or (None, path)."""
        if ":" in path and not path.startswith("/") and not path.startswith("~"):
            # Split on first colon to get potential pod_targets part
            parts = path.split(":", 1)
            pod_part = parts[0]
            
            # Check if this looks like a Windows drive letter (single alphabetic character)
            if len(pod_part) == 1 and pod_part.isalpha():
                # This looks like C:, D:, etc. - treat as local path
                return None, path
            
            # Otherwise treat as pod_targets:path format
            return parts[0], parts[1]
        return None, path
    
    # Sanity checks
    if not shutil.which("rsync"):
        console.print(
            styled(
                "Error: 'rsync' command not found in your system PATH. "
                "Please install rsync (available on most Unix-like systems).",
                "error",
            )
        )
        return
    
    if not api_key:
        api_key = get_or_set_api_key()
    if not api_key:
        console.print(styled("Error:", "error") + styled(" No API key found.", "primary"))
        return

    client = LiumAPIClient(api_key)
    
    # Parse source and destination
    source_pods, source_path = parse_remote_path(source)
    dest_pods, dest_path = parse_remote_path(destination)
    
    # Validate sync direction
    if source_pods and dest_pods:
        console.print(styled("Error: Remote-to-remote sync between pods not yet supported.", "error"))
        console.print(styled("Use a local intermediate directory or run sync in two steps.", "info"))
        return
    
    if not source_pods and not dest_pods:
        console.print(styled("Error: At least one path must be remote (pod_targets:path).", "error"))
        return
    
    # Determine operation mode
    if source_pods:
        # Remote to local
        operation_mode = "remote_to_local"
        pod_targets_str = source_pods
        remote_path = source_path
        local_path = dest_path
    else:
        # Local to remote  
        operation_mode = "local_to_remote"
        pod_targets_str = dest_pods
        remote_path = dest_path
        local_path = source_path
    
    # Validate local path
    local_path_obj = Path(local_path).expanduser().resolve()
    if operation_mode == "local_to_remote":
        if not local_path_obj.exists():
            console.print(styled(f"Error: Local source path '{local_path_obj}' does not exist.", "error"))
            return
    else:
        # For remote_to_local, ensure parent directory exists
        if not local_path_obj.parent.exists():
            console.print(styled(f"Error: Parent directory of '{local_path_obj}' does not exist.", "error"))
            return
    
    # Resolve pod targets
    pod_targets_list = [s.strip() for s in pod_targets_str.split(',') if s.strip()]
    resolved_pods, error_msg = resolve_pod_targets(client, pod_targets_list)
    
    if error_msg:
        console.print(styled(f"Error: {error_msg}", "error"))
        if not resolved_pods:
            return
        else:
            console.print(styled("Continuing with resolved pods...", "warning"))
    
    if not resolved_pods:
        console.print(styled("No valid pods found.", "error"))
        return

    # Get SSH key configuration
    private_key_path_config_str = get_config_value("ssh.key_path")
    if not private_key_path_config_str:
        console.print(
            styled(
                "Error: SSH private key path not configured. "
                "Use 'lium config set ssh.key_path /path/to/your/private_key'",
                "error",
            )
        )
        return
    private_key_path = Path(private_key_path_config_str.rstrip(".pub")).expanduser()
    if not private_key_path.exists():
        console.print(
            styled(f"Error: Configured SSH private key not found at '{private_key_path}'", "error")
        )
        return
    
    # Build rsync options
    rsync_options = []
    if archive:
        rsync_options.append("-a")
    if compress:
        rsync_options.append("-z")
    if delete:
        rsync_options.append("--delete")
    if dry_run:
        rsync_options.append("--dry-run")
    if progress:
        rsync_options.append("--progress")
    
    # Handle verbosity options (mutually exclusive)
    if quiet:
        rsync_options.append("--quiet")
    elif verbose:
        rsync_options.append("-vv")  # Extra verbose
    else:
        # Default: show files being transferred
        rsync_options.append("-v")
    
    # Add exclude patterns
    for pattern in exclude:
        rsync_options.extend(["--exclude", pattern])
    
    # SSH options for rsync
    ssh_options = f"-i {shlex.quote(str(private_key_path))}"
    
    # Show operation summary
    operation_desc = "DRY RUN of sync" if dry_run else "Syncing"
    direction_desc = f"{source} → {destination}"
    console.print(styled(f"\n🔄 {operation_desc}: {direction_desc}", "info"))
    console.print(styled(f"   Mode: {operation_mode.replace('_', ' ').title()}", "dim"))
    console.print(styled(f"   Pods: {len(resolved_pods)} target(s)", "dim"))
    if exclude:
        console.print(styled(f"   Excluding: {', '.join(exclude)}", "dim"))
    for pod, original_ref in resolved_pods:
        pod_huid = generate_human_id(pod.get("id", ""))
        console.print(styled(f"   - Target: {pod_huid} ({original_ref})", "dim"))
    console.print()
    
    # Execute sync for each pod
    success_count = 0
    failure_count = 0
    
    for pod, original_ref in resolved_pods:
        pod_huid = generate_human_id(pod.get("id", ""))
        
        ssh_connect_cmd_str = pod.get("ssh_connect_cmd")
        if not ssh_connect_cmd_str:
            console.print(
                styled(
                    f"⚠️  Pod '{pod_huid}' ({original_ref}) has no SSH connection command available "
                    "(it might not be fully RUNNING).",
                    "warning",
                )
            )
            failure_count += 1
            continue

        # Parse SSH command to extract connection details
        try:
            original_parts = shlex.split(ssh_connect_cmd_str)
            if original_parts[0].lower() != "ssh":
                raise ValueError("Not a valid ssh command string from pod info.")

            user, host = original_parts[1].split("@", 1)
            port = "22"
            other_ssh_options = []
            i = 2
            while i < len(original_parts):
                if original_parts[i] == "-p" and i + 1 < len(original_parts):
                    port = original_parts[i + 1]
                    i += 2
                elif original_parts[i] == "-o" and i + 1 < len(original_parts):
                    other_ssh_options.extend(original_parts[i : i + 2])
                    i += 2
                else:
                    other_ssh_options.append(original_parts[i])
                    i += 1
        except Exception as e:
            console.print(
                styled(
                    f"⚠️  Error parsing SSH command for '{pod_huid}' ({original_ref}): {e}",
                    "warning",
                )
            )
            failure_count += 1
            continue

        # Build complete SSH options string for rsync
        complete_ssh_options = f"{ssh_options} -p {port}"
        if other_ssh_options:
            complete_ssh_options += " " + " ".join(shlex.quote(opt) for opt in other_ssh_options)
        
        # Build rsync command
        rsync_cmd = ["rsync"] + rsync_options + ["-e", f"ssh {complete_ssh_options}"]
        
        if operation_mode == "local_to_remote":
            rsync_cmd.extend([str(local_path_obj), f"{user}@{host}:{q_remote(remote_path)}"])
        else:  # remote_to_local
            rsync_cmd.extend([f"{user}@{host}:{q_remote(remote_path)}", str(local_path_obj)])
        
        # Execute with retries
        pod_success = False
        for attempt in range(retry_attempts):
            if attempt > 0:
                console.print(styled(f"  🔄 Retry attempt {attempt + 1}/{retry_attempts}", "info"))
            
            console.print(styled(f"🔄 Syncing with '{pod_huid}' ({original_ref})...", "info"))
            
            proc = subprocess.run(rsync_cmd, capture_output=quiet, text=True)
            
            if proc.returncode == 0:
                console.print(styled(f"  ✅ Sync completed successfully", "success"))
                pod_success = True
                break
            else:
                console.print(
                    styled(f"  ❌ Sync failed (exit code {proc.returncode})", "error")
                )
                if proc.stderr and quiet:
                    # Show stderr only when we captured it (in quiet mode)
                    error_lines = proc.stderr.strip().split('\n')
                    for line in error_lines[:3]:  # Show first 3 lines of error
                        console.print(styled(f"     {line}", "dim"))
                    if len(error_lines) > 3:
                        console.print(styled(f"     ... ({len(error_lines) - 3} more lines)", "dim"))
                
                # Don't retry on certain errors (like permission denied)
                if proc.returncode in [1, 2, 3, 4, 5, 6, 10, 11, 12, 13, 14, 20, 21]:
                    # These are typically configuration or permission errors, not transient
                    console.print(styled(f"  ⚠️  Error type suggests retrying won't help, skipping retries", "warning"))
                    break
                
                if attempt < retry_attempts - 1:
                    console.print(styled(f"  ⏳ Will retry in a moment...", "info"))
        
        if pod_success:
            success_count += 1
        else:
            failure_count += 1

    # Summary
    if dry_run:
        console.print(styled(f"\n📊 Dry Run Summary: {success_count} pods would sync successfully, {failure_count} failed", "info"))
    else:
        console.print(styled(f"\n📊 Sync Summary: {success_count} pods synced successfully, {failure_count} failed", "info")) 