"""List active pods command for Lium CLI."""

import click
import requests
from typing import Optional
from datetime import datetime, timezone

from ..config import get_or_set_api_key
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


def get_status_style(status: str) -> str:
    """Return a Rich style string based on pod status."""
    status_upper = status.upper()
    if status_upper in ["RUNNING", "ACTIVE", "READY", "COMPLETED", "VERIFY_SUCCESS"]:
        return "success" # Uses theme's success style (maps to green/white)
    elif status_upper in ["FAILED", "ERROR", "STOPPED", "TERMINATED"]:
        return "error"   # Uses theme's error style (maps to red/white)
    elif status_upper in ["PENDING", "STARTING", "CREATING", "PROVISIONING", "INITIALIZING"]:
        return "warning" # Uses theme's warning style (maps to yellow/gray)
    return "primary" # Default style


@click.command(name="ps", help="List your active pods.")
@click.argument("pod_targets", type=str, nargs=-1, required=False)
@click.option("-k", "--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def ps_command(pod_targets: Optional[tuple], api_key: Optional[str]):
    """List all active pods for the user."""
    if not api_key: api_key = get_or_set_api_key()
    if not api_key:
        console.print(styled("Error:", "error") + styled(" No API key found. Please set LIUM_API_KEY or use 'lium config set api_key <YOUR_KEY>'", "primary"))
        return
    
    # Resolve client.
    client = LiumAPIClient(api_key)
    
    # Resolve selected pods and print them
    if pod_targets != None:
        select_pods, error_msg = resolve_pod_targets(client, pod_targets)
        for pod in select_pods:
            print( pod )     
        return   
    
    # Otherwise print all of them all.
    try:
        pods = client.get_pods()

        if not pods:
            console.print(styled("No active pods found.", "info"))
            return

        table = Table(
            # title=styled(f"Active Pods ({len(pods)} total)", "title"),
            box=None,
            show_header=True,
            show_lines=False,
            show_edge=False,
            padding=(0, 1, 0, 1),
            header_style="table.header",
            title_style="title",
            expand=True)

        table.add_column("#", style="dim", justify="right", width=3)  # Index column
        table.add_column("Pod", style="dim", no_wrap=False, min_width=16, max_width=18)  # HUID from pod.id
        table.add_column("Status", style="primary", width=10)
        table.add_column("GPU Config", style="executor.gpu", width=11, no_wrap=True)
        table.add_column("RAM", style="number", justify="right", width=6) 
        table.add_column("$/GPU", style="executor.price", justify="right", width=7) 
        table.add_column("Spent", style="executor.price", justify="right", width=8)
        table.add_column("Uptime", style="secondary", justify="right", width=8) 
        table.add_column("SSH Command", style="info", overflow="fold", min_width=25, max_width=40)

        for idx, pod in enumerate(pods):
            instance_name_huid = generate_human_id(pod.get("id", "")) # Name of the pod instance
            # pod_label = pod.get("pod_name", "N/A") # This was the executor HUID or UUID, no longer displayed here
            
            status_str = pod.get("status", "N/A")
            status_display = styled(status_str, get_status_style(status_str))
            gpu_api_name = pod.get("gpu_name", "N/A")
            raw_gpu_count_str = pod.get("gpu_count", "0")
            try: gpu_count_val = int(raw_gpu_count_str)
            except ValueError: gpu_count_val = 0
            gpu_model_display = extract_gpu_model(gpu_api_name)
            gpu_config_display = f"{gpu_count_val}x {gpu_model_display}" if gpu_count_val > 0 and gpu_api_name != "N/A" else gpu_model_display
            price_per_gpu_hour_display = "N/A"
            
            # Get pricing information from the executor object within the pod
            executor_data = pod.get("executor", {})
            total_price_per_hour = executor_data.get("price_per_hour")
            if total_price_per_hour is not None and gpu_count_val > 0:
                price_per_gpu = float(total_price_per_hour) / gpu_count_val
                price_per_gpu_hour_display = f"${price_per_gpu:.2f}"
            elif total_price_per_hour is not None:
                price_per_gpu_hour_display = f"${float(total_price_per_hour):.2f}"
            ram_total_kb = pod.get("ram_total", 0)
            ram_gb_display = f"{ram_total_kb / 1024 / 1024:.0f}" if ram_total_kb else "N/A"
            cost_so_far_display = "N/A"
            uptime_hours_display = "N/A"
            created_at_str = pod.get("created_at", "")
            if created_at_str:
                try:
                    if created_at_str.endswith('Z'): dt_created = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
                    elif '+' not in created_at_str and '-' not in created_at_str[10:]: dt_created = datetime.fromisoformat(created_at_str).replace(tzinfo=timezone.utc)
                    else: dt_created = datetime.fromisoformat(created_at_str)
                    now_utc = datetime.now(timezone.utc)
                    duration = now_utc - dt_created
                    duration_hours = duration.total_seconds() / 3600
                    if duration_hours > 0:
                        uptime_hours_display = f"{duration_hours:.2f}"
                        if total_price_per_hour is not None:
                            cost_so_far_display = f"${(duration_hours * float(total_price_per_hour)):.2f}"
                        else: cost_so_far_display = "No Price"
                    else:
                        uptime_hours_display = "<0.1"
                        cost_so_far_display = "$0.00"
                except ValueError: 
                    uptime_hours_display = "Date Error"
                    cost_so_far_display = "Date Error"

            row_style = "table.row.odd" if idx % 2 == 0 else "table.row.even"
            table.add_row(
                str(idx + 1),  # Index number starting from 1
                instance_name_huid, 
                # pod_label, # Removed
                status_display, 
                gpu_config_display, 
                ram_gb_display, 
                price_per_gpu_hour_display, 
                cost_so_far_display,
                uptime_hours_display,
                pod.get("ssh_connect_cmd", "N/A"),
                style=row_style
            )
        console.print(table)

    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 401:
            console.print(styled("Error: Authentication failed. Invalid API Key.", "error"))
        elif e.response.status_code == 403:
            console.print(styled("Error: Forbidden. You might not have permission to access pods.", "error"))
        else:
            console.print(styled(f"Error fetching pods: {e.response.status_code} - {e.response.text}", "error"))
    except Exception as e:
        console.print(styled(f"An unexpected error occurred: {str(e)}", "error")) 