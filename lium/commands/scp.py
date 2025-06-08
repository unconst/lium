"""Copy files to pods via SCP for Lium CLI."""

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


@click.command(name="scp", help="Copy a local file to a running pod.")
@click.argument("pod_targets", type=str, required=True)
@click.argument(
    "local_path_str",
    type=click.Path(exists=True, dir_okay=False, readable=True),
    required=False,   # ← now optional when --coldkey/--hotkey are used
)
@click.argument("remote_path_str", type=str, required=False)
@click.option(
    "--coldkey",
    type=str,
    help="Cold-wallet name (e.g. `kant`).  Copies "
         "`~/.bittensor/wallets/<coldkey>/coldkeypub.txt`.",
)
@click.option(
    "--hotkey",
    type=str,
    help="Hot-key filename inside the given cold wallet "
         "(`~/.bittensor/wallets/<coldkey>/hotkeys/<hotkey>`). "
         "Requires --coldkey.",
)
@click.option("-k", "--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def scp_command(
    pod_targets: str,
    local_path_str: Optional[str],
    remote_path_str: Optional[str],
    coldkey: Optional[str],
    hotkey: Optional[str],
    api_key: Optional[str],
):
    """
    Copies files to pod(s) identified by POD_TARGETS.

    POD_TARGETS should be a single argument that can contain:
    - Pod names/HUIDs: zesty-orbit-08
    - Index numbers from 'lium ps': 1 (or comma-separated: 1,2,3)
    - Comma-separated: 1,2,3 or 1,zesty-orbit-08
    - All pods: all

    Examples:
    - lium scp 1,2 ~/file.txt
    - lium scp all --coldkey my_wallet --hotkey my_hotkey
    - lium scp 1 ~/script.py /home/script.py

    If REMOTE_PATH_STR is omitted we copy the file into the pod user's $HOME,
    preserving only the filename (no host-side directories).  This prevents
    unwanted paths like /Users/<you>/… appearing on the pod.
    """
    # --------------------------------------------------------------------- #
    # 0.  tiny utilities
    # --------------------------------------------------------------------- #
    def q_remote(p: str) -> str:
        """Quote for remote shell – keep ~ unquoted so it expands to $HOME."""
        return p if p.startswith("~") else shlex.quote(p)

    # --------------------------------------------------------------------- #
    # 1.  sanity checks (unchanged)
    # --------------------------------------------------------------------- #
    if not shutil.which("scp"):
        console.print(
            styled(
                "Error: 'scp' command not found in your system PATH. "
                "Please install an SCP client (usually part of OpenSSH).",
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
    
    # Resolve pod targets
    pod_targets_list = tuple(target.strip() for target in pod_targets.split(',') if target.strip())
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

    # ------------------------------------------------------------------ #
    # 2.a Collect *all* local files that need copying
    # ------------------------------------------------------------------ #
    local_files: List[Path] = []

    # (i) CLI-provided path (the old behaviour)
    if local_path_str:
        lp = Path(local_path_str).expanduser().resolve()
        if not lp.is_file():
            console.print(styled(f"Error: '{lp}' is not a file", "error"))
            return
        local_files.append(lp)

    # (ii) wallet-derived paths (new behaviour)
    if coldkey:
        bt_root = Path.home() / ".bittensor" / "wallets" / coldkey
        ck_pub = bt_root / "coldkeypub.txt"
        if not ck_pub.exists():
            console.print(styled(f"Error: '{ck_pub}' not found", "error")); return
        local_files.append(ck_pub.resolve())

        if hotkey:
            hk_path = bt_root / "hotkeys" / hotkey
            if not hk_path.exists():
                console.print(styled(f"Error: '{hk_path}' not found", "error")); return
            local_files.append(hk_path.resolve())
    elif hotkey:
        console.print(styled("--hotkey requires --coldkey", "error")); return

    if not local_files:
        console.print(
            styled("Error:", "error")
            + styled(
                " You must supply either LOCAL_PATH_STR or --coldkey/--hotkey.",
                "primary",
            )
        )
        return

    # ------------------------------------------------------------------ #
    # 2.b Determine a remote *destination* for each local file
    # ------------------------------------------------------------------ #
    home = Path.home().resolve()
    to_copy: List[Tuple[Path, str]] = []

    for lf in local_files:
        if remote_path_str and len(local_files) == 1:
            # user explicitly supplied a single dest – respect it verbatim
            rp = remote_path_str
        else:
            try:
                # preserve path relative to $HOME (old behaviour)
                rel = lf.relative_to(home)
                rp = f"~/{rel.as_posix()}"
            except ValueError:
                rp = f"~/{lf.name}"
        to_copy.append((lf, rp))

    # Show what we're about to copy
    console.print(styled(f"\n📁 Copying {len(local_files)} file(s) to {len(resolved_pods)} pod(s):", "info"))
    for lf, rp in to_copy:
        console.print(styled(f"  - {lf} → {rp}", "dim"))
    for pod, original_ref in resolved_pods:
        pod_huid = generate_human_id(pod.get("id", ""))
        console.print(styled(f"  - Target: {pod_huid} ({original_ref})", "dim"))
    console.print()

    # --------------------------------------------------------------------- #
    # Copy to each pod
    # --------------------------------------------------------------------- #
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

        # --------------------------------------------------------------------- #
        # 4.  decompose the ssh command so we can re-use host / port / -o options
        # --------------------------------------------------------------------- #
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

        # ------------------------------------------------------------------ #
        # 5-6.  For *each* file:  mkdir -p (if needed) then scp
        # ------------------------------------------------------------------ #
        pod_success = True
        for lf, rp in to_copy:
            remote_dir = os.path.dirname(rp)
            if remote_dir and remote_dir not in ("~", "."):
                mkdir_cmd = [
                    "ssh",
                    "-i", str(private_key_path),
                    "-p", port,
                    *other_ssh_options,
                    f"{user}@{host}",
                    f"mkdir -p {q_remote(remote_dir)}",
                ]
                try:
                    subprocess.run(mkdir_cmd, check=True, capture_output=True, text=True)
                except subprocess.CalledProcessError as e:
                    console.print(styled(f"⚠️  Failed to create directory on '{pod_huid}' ({original_ref}): {e}", "warning"))
                    pod_success = False
                    break

            scp_cmd = [
                "scp",
                "-i", str(private_key_path),
                "-P", port,
                *other_ssh_options,
                str(lf),
                f"{user}@{host}:{rp}",
            ]

            console.print(styled(f"📤 Copying {lf.name} → {pod_huid} ({original_ref}):{rp}", "info"))
            proc = subprocess.run(scp_cmd, capture_output=True, text=True)
            if proc.returncode == 0:
                console.print(styled(f"  ✅ Done", "success"))
            else:
                console.print(
                    styled(f"  ❌ Failed (exit code {proc.returncode})", "error")
                )
                if proc.stderr:
                    console.print(styled(f"     {proc.stderr.strip()}", "dim"))
                pod_success = False
                break
        
        if pod_success:
            success_count += 1
        else:
            failure_count += 1

    # Summary
    console.print(styled(f"\n📊 Copy Summary: {success_count} pods successful, {failure_count} pods failed", "info")) 