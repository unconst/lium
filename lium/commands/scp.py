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
@click.argument("pod_name_huid", type=str)
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
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def scp_command(
    pod_name_huid: str,
    local_path_str: Optional[str],
    remote_path_str: Optional[str],
    coldkey: Optional[str],
    hotkey: Optional[str],
    api_key: Optional[str],
):
    """
    Copies LOCAL_PATH_STR to REMOTE_PATH_STR on pod POD_NAME_HUID.

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

    # --------------------------------------------------------------------- #
    # 3.  fetch pod connection details (unchanged except minor refactor)
    # --------------------------------------------------------------------- #
    client = LiumAPIClient(api_key)
    try:
        target_pod_info = next(
            (p for p in client.get_pods() or [] if generate_human_id(p.get("id", "")).lower() == pod_name_huid.lower()),
            None,
        )
    except Exception as e:
        console.print(styled(f"Error fetching active pods: {e}", "error"))
        return
    if not target_pod_info:
        console.print(
            styled(f"Error: Pod with Name (HUID) '{pod_name_huid}' not found or not active.", "error")
        )
        return

    ssh_connect_cmd_str = target_pod_info.get("ssh_connect_cmd")
    if not ssh_connect_cmd_str:
        console.print(
            styled(
                f"Error: Pod '{pod_name_huid}' has no SSH connection command available "
                "(it might not be fully RUNNING).",
                "error",
            )
        )
        return

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
                f"Error parsing pod's SSH connection command ('{ssh_connect_cmd_str}'): {e}",
                "error",
            )
        )
        return

    # ------------------------------------------------------------------ #
    # 5-6.  For *each* file:  mkdir -p (if needed) then scp
    # ------------------------------------------------------------------ #
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
            subprocess.run(mkdir_cmd, check=True, capture_output=True, text=True)

        scp_cmd = [
            "scp",
            "-i", str(private_key_path),
            "-P", port,
            *other_ssh_options,
            str(lf),
            f"{user}@{host}:{rp}",
        ]

        console.print(styled(f"Copying {lf} → {pod_name_huid}:{rp}", "info"))
        proc = subprocess.run(scp_cmd, capture_output=True, text=True)
        if proc.returncode == 0:
            console.print(styled(f"  ✅  done", "success"))
        else:
            console.print(
                styled(f"Error during scp operation (exit code {proc.returncode}):", "error")
            )
            if proc.stdout:
                console.print(styled("STDOUT:\n" + proc.stdout, "dim"))
            if proc.stderr:
                console.print(styled("STDERR:\n" + proc.stderr, "dim")) 