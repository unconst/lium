"""Terminate pods command for Lium CLI."""

import click
import json
import requests
from typing import Optional, Dict, List, Any, Tuple

from ..config import get_or_set_api_key
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


@click.command(name="down", help="Unrent/terminate one or more pods. Use Name (HUID) or --all.")
@click.argument("pod_names", type=str, nargs=-1, required=False) # Now nargs=-1
@click.option("--all", "terminate_all", is_flag=True, help="Terminate all active pods.")
@click.option("--yes", "-y", "skip_confirmation", is_flag=True, help="Skip confirmation prompts.") # Added -y alias
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def down_command(pod_names: Optional[Tuple[str, ...]], terminate_all: bool, skip_confirmation: bool, api_key: Optional[str]):
    """Unrents/terminates pod(s) identified by Name(s) (HUID) or all active pods.
    
    POD_NAMES: Space-separated or comma-separated list of pod Names (HUIDs).
    Example: lium down name1 name2,name3
    """
    if not api_key: api_key = get_or_set_api_key()
    if not api_key: console.print(styled("Error: No API key found.", "error")); return
    target_huids_flat = []
    if pod_names:
        for item in pod_names: target_huids_flat.extend(name.strip().lower() for name in item.split(',') if name.strip())
    if not target_huids_flat and not terminate_all: console.print(styled("Error: Must specify pod Name(s) or --all.", "error")); return

    client = LiumAPIClient(api_key)
    pods_to_terminate_info: List[Dict[str, Any]] = [] # Stores {huid, pod_id, executor_id, original_ref (which is huid)}
    
    try:
        active_pods = client.get_pods()
        if not active_pods: console.print(styled("No active pods found.", "info")); return

        if terminate_all:
            for pod in active_pods:
                pod_id = pod.get("id"); huid = generate_human_id(pod_id)
                executor_id = pod.get("Pod", {}).get("id") or pod_id 
                pods_to_terminate_info.append({"huid": huid, "pod_id": pod_id, "executor_id": executor_id, "original_ref": huid})
            if not pods_to_terminate_info: console.print(styled("No active pods to terminate with --all.", "info")); return
        else: 
            target_huids_set = set(target_huids_flat)
            found_pods_map = {generate_human_id(p.get("id")): p for p in active_pods if p.get("id")}
            unresolved_huids = list(target_huids_set)
            
            for target_huid in target_huids_set:
                pod_data = found_pods_map.get(target_huid)
                if pod_data:
                    pod_id = pod_data.get("id")
                    executor_id = pod_data.get("Pod", {}).get("id") or pod_id
                    pods_to_terminate_info.append({"huid": target_huid, "pod_id": pod_id, "executor_id": executor_id, "original_ref": target_huid})
                    if target_huid in unresolved_huids: unresolved_huids.remove(target_huid)
            
            if unresolved_huids:
                console.print(styled(f"Warning: Unresolved/not found: {', '.join(unresolved_huids)}. These will be skipped.", "warning"))
            if not pods_to_terminate_info: console.print(styled("No specified pods found to terminate.", "info")); return

    except Exception as e: console.print(styled(f"Error fetching active pods: {str(e)}", "error")); return

    if not pods_to_terminate_info: console.print(styled("No pods selected for termination.", "info")); return

    console.print("\n" + styled("Pods to release", "header"))
    for pod_info in pods_to_terminate_info:
        console.print(f"  - {pod_info['original_ref']}") # Only the original HUID reference
    console.print("")

    if not skip_confirmation:
        if not Prompt.ask(styled(f"Continue? ({len(pods_to_terminate_info)} pod(s))", "key"), default="n", console=console).lower().startswith("y"):
            console.print(styled("Operation cancelled.", "info")); return
    
    success_count = 0; failure_count = 0; failed_details_list = []
    for pod_info in pods_to_terminate_info:
        huid, executor_id, original_ref = pod_info['huid'], pod_info['executor_id'], pod_info['original_ref']
        # Removed: console.print(styled(f"Attempting to terminate pod '{huid}' ...", "info"))
        try:
            client.unrent_pod(executor_id=executor_id) # Assuming this targets the correct pod via executor_id based on previous behavior
            success_count += 1
        except requests.exceptions.HTTPError as e:
            error_message = f"API Error {e.response.status_code}"; failure_count += 1
            try: error_details = e.response.json(); detail_msg = error_details.get('detail'); error_message += f" - {detail_msg if isinstance(detail_msg, str) else json.dumps(detail_msg)}" 
            except json.JSONDecodeError: error_message += f" - {e.response.text[:70]}"
            failed_details_list.append(f"'{original_ref}': {error_message}")
        except Exception as e: 
            failed_details_list.append(f"'{original_ref}': Unexpected error: {str(e)[:70]}"); failure_count += 1

    if success_count > 0: console.print(styled(f"Successfully requested release for {success_count} pod(s).", "success"))
    if failure_count > 0: 
        console.print(styled(f"Failed to request release for {failure_count} pod(s):", "error"))
        for detail in failed_details_list:
            console.print(styled(f"  - {detail}", "error"))
    if success_count > 0 or failure_count > 0 : console.print(styled("Use 'lium ps' to verify status.", "info"))
    elif not pods_to_terminate_info and not unresolved_huids : console.print(styled("No action taken.", "info")) # Check unresolved_huids 