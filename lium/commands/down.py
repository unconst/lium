"""Terminate pods command for Lium CLI."""

import json
import click
import requests
from typing import Optional, Dict, List, Any, Tuple

from ..config import get_or_set_api_key
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *

@click.command(name="down", help="Unrent/terminate one or more pods. Use Name (HUID) or --all.")
@click.argument("pod_targets", type=str, nargs=-1, required=False)
@click.option("--all", '-a', "terminate_all", is_flag=True, help="Terminate all active pods.")
@click.option("--yes", "-y", "skip_confirmation", is_flag=True, help="Skip confirmation prompts.") # Added -y alias
@click.option("-k", "--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def down_command(pod_targets: Optional[Tuple[str, ...]], terminate_all: bool, skip_confirmation: bool, api_key: Optional[str]):
    """Unrents/terminates pod(s) identified by POD_TARGETS or all active pods.
    
    POD_TARGETS can be:
    - Pod names/HUIDs: zesty-orbit-08
    - Index numbers from 'lium ps': 1, 2, 3
    - Comma-separated: 1,2,3 or 1,zesty-orbit-08
    - Special: all (all pods, same as --all)
    
    Examples:
    - lium down 1,2,3
    - lium down all
    - lium down zesty-orbit-08
    """
    if not api_key: api_key = get_or_set_api_key()
    if not api_key: console.print(styled("Error: No API key found.", "error")); return

    client = LiumAPIClient(api_key)
    
    # Handle the --all flag or -1 target
    if terminate_all or (pod_targets and len(pod_targets) == 1 and pod_targets[0] == '-1'):
        try:
            active_pods = client.get_pods()
            if not active_pods: 
                console.print(styled("No active pods found.", "info"))
                return
            
            resolved_pods = [(pod, "-1 (all)" if pod_targets and pod_targets[0] == '-1' else "--all") for pod in active_pods]
            error_msg = None
        except Exception as e:
            console.print(styled(f"Error fetching active pods: {str(e)}", "error"))
            return
    else:
        if not pod_targets:
            console.print(styled("Error: Must specify pod targets or use --all.", "error"))
            return
        
        # Use the resolver for other targets
        resolved_pods, error_msg = resolve_pod_targets(client, pod_targets)
        
        if error_msg:
            console.print(styled(f"Warning: {error_msg}", "warning"))
            if not resolved_pods:
                return

    if not resolved_pods:
        console.print(styled("No pods selected for termination.", "info"))
        return

    console.print("\n" + styled("Pods to release:", "header"))
    for pod, original_ref in resolved_pods:
        pod_huid = generate_human_id(pod.get("id", ""))
        console.print(f"  - {pod_huid} ({original_ref})")
    console.print("")

    if not skip_confirmation:
        if not Prompt.ask(styled(f"Continue? ({len(resolved_pods)} pod(s))", "key"), default="n", console=console).lower().startswith("y"):
            console.print(styled("Operation cancelled.", "info"))
            return
    
    success_count = 0
    failure_count = 0
    failed_details_list = []
    
    for pod, original_ref in resolved_pods:
        pod_huid = generate_human_id(pod.get("id", ""))
        executor_id = pod.get("executor", {}).get("id") or pod.get("id")
        
        try:
            client.unrent_pod(executor_id=executor_id)
            console.print(styled(f"✅ Successfully requested release for '{pod_huid}' ({original_ref})", "success"))
            success_count += 1
        except requests.exceptions.HTTPError as e:
            error_message = f"API Error {e.response.status_code}"
            try: 
                error_details = e.response.json()
                detail_msg = error_details.get('detail')
                error_message += f" - {detail_msg if isinstance(detail_msg, str) else json.dumps(detail_msg)}" 
            except json.JSONDecodeError: 
                error_message += f" - {e.response.text[:70]}"
            failed_details_list.append(f"'{pod_huid}' ({original_ref}): {error_message}")
            failure_count += 1
        except Exception as e: 
            failed_details_list.append(f"'{pod_huid}' ({original_ref}): Unexpected error: {str(e)[:70]}")
            failure_count += 1

    # Summary
    console.print(f"\n📊 Termination Summary:")
    if success_count > 0: 
        console.print(styled(f"✅ Successfully requested release for {success_count} pod(s).", "success"))
    if failure_count > 0: 
        console.print(styled(f"❌ Failed to request release for {failure_count} pod(s):", "error"))
        for detail in failed_details_list:
            console.print(styled(f"  - {detail}", "error"))
    if success_count > 0:
        console.print(styled("Use 'lium ps' to verify status.", "info")) 