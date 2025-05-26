"""Main CLI entry point for Lium."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED, MINIMAL
from rich.prompt import Prompt
from rich.syntax import Syntax
from typing import Optional, Dict, List, Any, Tuple
from collections import defaultdict
import re
import hashlib
import json
from datetime import datetime, timezone # Updated import
import requests # Added for HTTPError handling
import paramiko
import sys # For stdout/stderr flushing
import shlex # For parsing ssh command string
import socket # For socket errors
from pathlib import Path

from .api import LiumAPIClient
from .config import (
    get_api_key, 
    set_config_value, 
    get_config_value, 
    unset_config_value, 
    get_config_path,
    get_ssh_public_keys
)
from .styles import get_theme, styled, SolarizedColors, MonochromeColors, style_manager, ColorScheme


# Create console with our custom theme
console = Console(theme=get_theme())

# Word lists for HUID generation - these should be expanded for a larger namespace
ADJECTIVES = [
    "swift", "silent", "brave", "bright", "calm", "clever", "eager", "fierce", "gentle", "grand",
    "happy", "jolly", "kind", "lively", "merry", "noble", "proud", "silly", "witty", "zesty",
    "cosmic", "digital", "electric", "frozen", "golden", "hydro", "iron", "laser", "lunar", "solar"
] # 30 adjectives

NOUNS = [
    "hawk", "lion", "tiger", "eagle", "fox", "wolf", "shark", "viper", "cobra", "falcon",
    "jaguar", "leopard", "lynx", "panther", "puma", "cougar", "condor", "raven", "photon", "quasar",
    "vector", "matrix", "cipher", "pixel", "comet", "nebula", "nova", "orbit", "axiom", "sphinx"
] # 30 nouns
# Current combination space: 30 * 30 * 256 (from 2 hex digits) = 230,400

def generate_human_id(executor_id: str) -> str:
    """Generates a deterministic human-readable ID from the executor_id."""
    if not executor_id or not isinstance(executor_id, str):
        return "invalid-id-huid"
    
    # Use MD5 hash of the executor_id for deterministic choices
    hasher = hashlib.md5(executor_id.encode('utf-8'))
    digest = hasher.hexdigest()
    
    # Use parts of the hash to select words and suffix
    # Ensure indices are within bounds of the word lists
    adj_idx = int(digest[0:4], 16) % len(ADJECTIVES)
    noun_idx = int(digest[4:8], 16) % len(NOUNS)
    
    # Use last 2 characters of the hash for the numeric suffix for consistency
    suffix_chars = digest[-2:]
        
    adjective = ADJECTIVES[adj_idx]
    noun = NOUNS[noun_idx]
    
    return f"{adjective}-{noun}-{suffix_chars}"


def extract_gpu_model(machine_name: str) -> str:
    """Extract just the model number from GPU name."""
    # Pattern to match various GPU models - ORDER MATTERS!
    patterns = [
        (r'RTX\s*(\d{4}[A-Z]?)', 'RTX'),  # RTX 4090, RTX 3090, RTX 4090 D
        (r'RTX\s*A(\d{4})', 'A'),         # RTX A5000, RTX A6000
        (r'H(\d{2,3})', 'H'),              # H100, H200 - BEFORE A pattern
        (r'B(\d{2,3})', 'B'),              # B200
        (r'L(\d{2}[S]?)', 'L'),            # L40, L40S
        (r'A(\d{2,3})', 'A'),              # A100, A40 - AFTER H pattern
    ]
    
    for pattern, prefix in patterns:
        match = re.search(pattern, machine_name, re.IGNORECASE)
        if match:
            # Get the matched number/model
            model = match.group(1)
            # Add the letter prefix back for non-RTX cards
            if prefix == 'RTX':
                return model
            else:
                return f"{prefix}{model}"
    
    # If no pattern matches, return a shortened version
    return machine_name.split()[-1] if machine_name else "Unknown"


def extract_metrics(executor: Dict[str, Any]) -> Dict[str, float]:
    """Extract all metrics needed for Pareto frontier calculation."""
    specs = executor.get("specs", {})
    gpu_details = specs.get("gpu", {}).get("details", [{}])[0]
    hard_disk = specs.get("hard_disk", {})
    ram = specs.get("ram", {})
    network = specs.get("network", {})
    gpu_count = specs.get("gpu", {}).get("count", 1)
    
    # Price per GPU
    price_per_gpu = executor.get("price_per_hour", 0) / gpu_count if gpu_count > 0 else float('inf')
    
    # GPU metrics
    gpu_capacity = gpu_details.get("capacity", 0)  # MiB
    pcie_speed = gpu_details.get("pcie_speed", 0)  # MB/s
    memory_speed = gpu_details.get("memory_speed", 0)  # GB/s
    graphics_speed = gpu_details.get("graphics_speed", 0)  # TFLOPS
    gpu_utilization = gpu_details.get("gpu_utilization", 0)
    
    # System metrics
    ram_total = ram.get("total", 0)  # total is in KB
    disk_free = hard_disk.get("free", 0)  # free is in KB
    
    # Network metrics
    upload_speed = network.get("upload_speed", 0) or 0
    download_speed = network.get("download_speed", 0) or 0
    
    return {
        'price_per_hour': price_per_gpu,
        'gpu_capacity': gpu_capacity,
        'ram_total': ram_total / 1024,  # Convert KB to MiB
        'disk_free': disk_free, # Keep in KB for formatting function
        'pcie_speed': pcie_speed,
        'memory_speed': memory_speed,
        'graphics_speed': graphics_speed,
        'gpu_utilization': gpu_utilization,
        'upload_speed': upload_speed,
        'download_speed': download_speed,
    }


def dominates(metrics_a: Dict[str, float], metrics_b: Dict[str, float]) -> bool:
    """Check if executor A dominates executor B in Pareto sense."""
    # Define which metrics should be minimized (lower is better)
    minimize_metrics = {'price_per_hour', 'gpu_utilization'}
    
    at_least_one_better = False
    
    for metric in metrics_a:
        if metric in minimize_metrics:
            # For minimize metrics, A is better if it's lower
            if metrics_a[metric] < metrics_b[metric]:
                at_least_one_better = True
            elif metrics_a[metric] > metrics_b[metric]:
                return False  # B is better in this metric
        else:
            # For maximize metrics, A is better if it's higher
            if metrics_a[metric] > metrics_b[metric]:
                at_least_one_better = True
            elif metrics_a[metric] < metrics_b[metric]:
                return False  # B is better in this metric
    
    return at_least_one_better


def calculate_pareto_frontier(executors: List[Dict[str, Any]]) -> List[Tuple[Dict[str, Any], bool]]:
    """Calculate Pareto frontier and return executors with frontier status."""
    # Extract metrics for all executors
    executor_metrics = [(e, extract_metrics(e)) for e in executors]
    
    # Mark each executor as dominated or not
    results = []
    for i, (executor_i, metrics_i) in enumerate(executor_metrics):
        is_dominated = False
        for j, (executor_j, metrics_j) in enumerate(executor_metrics):
            if i != j and dominates(metrics_j, metrics_i):
                is_dominated = True
                break
        results.append((executor_i, not is_dominated))
    
    # Sort: Pareto frontier first, then by price
    results.sort(key=lambda x: (not x[1], x[0].get("price_per_hour", float('inf'))))
    
    return results


def format_metric(value: float, metric_type: str) -> str:
    """Format metric values for display."""
    if value == 0 or value == float('inf'):
        return "N/A"
    
    if metric_type in ['price_per_hour']:
        return f"${value:.2f}"
    elif metric_type in ['gpu_capacity', 'ram_total']:
        # Convert MiB to GB
        return f"{value/1024:.0f}"
    elif metric_type == 'disk_free':
        # Assuming input is in KB, convert to GB (KB -> MB -> GB)
        return f"{value / 1024 / 1024:.0f}"
    elif metric_type in ['upload_speed', 'download_speed']:
        return f"{int(value)}"
    elif metric_type in ['gpu_utilization']:
        return f"{value:.0f}%"
    elif metric_type in ['pcie_speed']:
        return f"{int(value)}"
    elif metric_type in ['memory_speed']:
        return f"{value:.0f}"
    elif metric_type in ['graphics_speed']:
        return f"{value:.0f}"
    else:
        return f"{value:.1f}"


def group_executors_by_gpu(executors: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group executors by GPU model."""
    grouped = defaultdict(list)
    
    for executor in executors:
        machine_name = executor.get("machine_name", "Unknown")
        gpu_model = extract_gpu_model(machine_name)
        grouped[gpu_model].append(executor)
    
    return dict(grouped)


def show_gpu_summary(executors: List[Dict[str, Any]]) -> Optional[str]:
    """Show summary of GPUs grouped by type and return selected type."""
    grouped = group_executors_by_gpu(executors)
    
    # Create summary table
    table = Table(
        title=styled(f"GPU Types Summary ({len(executors)} total executors)", "title"),
        box=None, show_header=True, show_lines=False, show_edge=False,
        padding=(0, 1),
        header_style="table.header", title_style="title",
        expand=True)
    
    # Add columns
    table.add_column("Pod Type", style="executor.gpu", no_wrap=True)
    table.add_column("Min $/GPU", style="executor.price", justify="right")
    table.add_column("Max $/GPU", style="executor.price", justify="right")
    table.add_column("Available", style="number", justify="right")
    
    # Calculate prices for each GPU type
    gpu_price_data = []
    
    for gpu_type, executors_of_type in grouped.items():
        # Calculate min and max price per GPU for this type
        prices_per_gpu = []
        total_gpus = 0
        
        for executor in executors_of_type:
            gpu_count = executor.get("specs", {}).get("gpu", {}).get("count", 1)
            price_per_gpu = executor.get("price_per_hour", 0) / gpu_count if gpu_count > 0 else 0
            prices_per_gpu.append(price_per_gpu)
            total_gpus += gpu_count
        
        min_price = min(prices_per_gpu) if prices_per_gpu else 0
        max_price = max(prices_per_gpu) if prices_per_gpu else 0
        
        gpu_price_data.append({
            'gpu_type': gpu_type,
            'min_price': min_price,
            'max_price': max_price,
            'total_gpus': total_gpus,
            'sort_price': max_price  # Sort by max price
        })
    
    # Sort by price descending (most expensive first)
    gpu_price_data.sort(key=lambda x: x['sort_price'], reverse=True)
    
    # Add rows to table
    for idx, data in enumerate(gpu_price_data):
        # Format prices - always show both min and max
        min_price_str = f"${data['min_price']:.2f}"
        max_price_str = f"${data['max_price']:.2f}"
        
        # Add row with alternating background
        style = "table.row.odd" if idx % 2 == 0 else "table.row.even"
        table.add_row(
            data['gpu_type'],
            min_price_str,
            max_price_str,
            str(data['total_gpus']),
            style=style
        )
    
    console.print(table)
    
    # Prompt for GPU type selection
    console.print("\n" + styled("Enter a GPU type from the list above (i.e. '4090'): ", "key"))
    
    # Create a prompt with the themed console
    selected_type = Prompt.ask("", default="", console=console, show_default=False)
    
    if selected_type and selected_type.upper() in grouped:
        return selected_type.upper()
    elif selected_type:
        console.print(styled(f"GPU type '{selected_type}' not found.", "error"))
        return None
    else:
        return None


def show_gpu_type_details(gpu_type: str, executors: List[Dict[str, Any]]):
    """Show detailed information for Pareto optimal executors of a specific GPU type."""
    # Calculate Pareto frontier
    pareto_results = calculate_pareto_frontier(executors) # This already sorts Pareto optimal first, then by price
    
    # Limit to showing a maximum of 10 entries
    MAX_ENTRIES_TO_SHOW = 10
    executors_to_display = pareto_results[:MAX_ENTRIES_TO_SHOW]
    
    pareto_optimal_in_displayed = [executor for executor, is_pareto in executors_to_display if is_pareto]
    
    total_for_type = len(executors)
    shown_count = len(executors_to_display)
    pareto_in_shown_count = len(pareto_optimal_in_displayed)

    if total_for_type <= shown_count: # If we are showing all available (because total is <= MAX_ENTRIES_TO_SHOW)
        title_message = f"Top {shown_count}/{total_for_type} Executors of type: {gpu_type}"
    else:
        title_message = f"Top {shown_count}/{total_for_type} Executors of type: {gpu_type}"

    table = Table(
        # title=styled(title_message, "title"),
        box=None,
        show_header=True,
        show_lines=False,
        show_edge=False,
        padding=(0, 1), # Simpler padding (vertical, horizontal)
        header_style="table.header",
        title_style="title",
        expand=True
    )
    
    # Add columns - reorganized for better readability, removed Pareto marker and GPU%
    table.add_column("Pod", style="dim", no_wrap=False, min_width=15, max_width=20)
    table.add_column("Config", style="executor.gpu", no_wrap=True)
    table.add_column("$/GPU/hr", style="executor.price", justify="right")
    table.add_column("VRAM", style="number", justify="right")
    table.add_column("RAM", style="number", justify="right")
    table.add_column("Disk", style="number", justify="right")
    table.add_column("PCIe", style="number", justify="right")
    table.add_column("Mem", style="number", justify="right")
    table.add_column("TFLOPs", style="number", justify="right")
    table.add_column("Net ↑", style="info", justify="right")
    table.add_column("Net ↓", style="info", justify="right")
    table.add_column("Location", style="executor.location", width=10, no_wrap=True, overflow="ellipsis") # Truncate if needed
    
    # Add rows - iterate over executors_to_display instead of all pareto_results
    for idx, (executor, is_pareto) in enumerate(executors_to_display):
        # Extract all metrics
        metrics = extract_metrics(executor)
        gpu_count = executor.get("specs", {}).get("gpu", {}).get("count", 1)
        config = f"{gpu_count}x{gpu_type}"
        # The HUID/Name is generated from executor.get("id")
        executor_name_huid = generate_human_id(executor.get("id", ""))
        
        location_data = executor.get("location", {})
        country = location_data.get('country', location_data.get('country_code', 'Unknown'))
        
        style = "table.row.odd" if idx % 2 == 0 else "table.row.even"
        table.add_row(
            executor_name_huid, # This is for the "Pod" column
            config,
            format_metric(metrics['price_per_hour'], 'price_per_hour'),
            format_metric(metrics['gpu_capacity'], 'gpu_capacity'),
            format_metric(metrics['ram_total'], 'ram_total'),
            format_metric(metrics['disk_free'], 'disk_free'),
            format_metric(metrics['pcie_speed'], 'pcie_speed'),
            format_metric(metrics['memory_speed'], 'memory_speed'),
            format_metric(metrics['graphics_speed'], 'graphics_speed'),
            format_metric(metrics['upload_speed'], 'upload_speed'),
            format_metric(metrics['download_speed'], 'download_speed'),
            country,
            style=style
        )
    
    console.print(table)


@click.group()
def cli():
    """Lium CLI - Manage compute executors."""
    pass


@cli.command(name="ls")
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
@click.argument("gpu_type_filter", required=False, type=str)
def list_executors(api_key: Optional[str], gpu_type_filter: Optional[str]):
    """List all available executors.

    If GPU_TYPE_FILTER is provided, it directly shows details for that GPU type.
    Otherwise, it shows a summary and prompts for selection.
    """
    # Get API key from various sources
    if not api_key:
        api_key = get_api_key()
    
    if not api_key:
        console.print(styled("Error:", "error") + styled(" No API key found. Please set LIUM_API_KEY environment variable or run 'lium config set-api-key'", "primary"))
        return
    
    try:
        # Create API client and fetch executors
        client = LiumAPIClient(api_key)
        executors = client.get_executors()
        
        if not executors:
            console.print(styled("No executors available.", "warning"))
            return
        
        grouped_by_gpu = group_executors_by_gpu(executors)
        
        selected_gpu = None
        if gpu_type_filter:
            # Normalize input for direct filter
            normalized_filter = gpu_type_filter.upper()
            if normalized_filter in grouped_by_gpu:
                selected_gpu = normalized_filter
            else:
                console.print(styled(f"GPU type '{gpu_type_filter}' not found.", "error"))
                console.print(styled(f"Available types: {', '.join(sorted(grouped_by_gpu.keys()))}", "info"))
                return
        else:
            # Show GPU summary and get selection if no filter provided
            selected_gpu = show_gpu_summary(executors)
        
        # If a GPU type was selected (either by filter or prompt), show details
        if selected_gpu:
            if selected_gpu in grouped_by_gpu:
                console.print("\n")  # Add spacing
                show_gpu_type_details(selected_gpu, grouped_by_gpu[selected_gpu])
            # This else case was correctly commented out as it should not be reached if selected_gpu is valid
            # elif selected_gpu: # If selected_gpu is not None but not in grouped_by_gpu (e.g. invalid manual entry after prompt)
            #    console.print(styled(f"Details for GPU type '{selected_gpu}' could not be found in grouped data.", "error"))
        
    except Exception as e:
        console.print(styled("Error:", "error") + styled(f" Failed to fetch executors: {str(e)}", "primary"))


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


@cli.command(name="ps", help="List your active pods.")
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def list_pods(api_key: Optional[str]):
    """List all active pods for the user."""
    if not api_key: api_key = get_api_key()
    if not api_key:
        console.print(styled("Error:", "error") + styled(" No API key found. Please set LIUM_API_KEY or use 'lium config set api_key <YOUR_KEY>'", "primary"))
        return

    try:
        client = LiumAPIClient(api_key)
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
            executor_data = pod.get("Pod", {})
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


@click.group(help="Manage Lium CLI configuration.")
def config():
    pass

@config.command(name="get", help="Get a configuration value.")
@click.argument("key")
def config_get(key: str):
    value = get_config_value(key)
    if value is not None:
        console.print(styled(value, "primary"))
    else:
        console.print(styled(f"Key '{key}' not found.", "error"))

@config.command(name="set", help="Set a configuration value.")
@click.argument("key")
@click.argument("value")
def config_set(key: str, value: str):
    set_config_value(key, value)
    console.print(styled(f"Set '{key}' to: ", "success") + styled(value, "primary"))

@config.command(name="unset", help="Remove a configuration value.")
@click.argument("key")
def config_unset(key: str):
    if unset_config_value(key):
        console.print(styled(f"Key '{key}' unset successfully.", "success"))
    else:
        console.print(styled(f"Key '{key}' not found.", "error"))

@config.command(name="show", help="Show the entire configuration.")
def config_show():
    # Perform a benign read to ensure migration logic in config.py is triggered.
    # This is a bit of a workaround for not directly calling load_config_parser().
    _ = get_config_value("api.api_key") # This call will trigger migration if needed.
    
    config_file_path = get_config_path()
    if config_file_path.exists():
        try:
            with open(config_file_path, "r") as f:
                ini_content = f.read()
            
            current_scheme_value = style_manager.scheme.value
            if current_scheme_value == ColorScheme.MONOCHROME_DARK.value:
                bg_color = MonochromeColors.BLACK; syntax_theme_name = "monokai"
            elif current_scheme_value == ColorScheme.MONOCHROME_LIGHT.value:
                bg_color = MonochromeColors.WHITE; syntax_theme_name = "default"
            elif current_scheme_value == ColorScheme.SOLARIZED_DARK.value:
                bg_color = SolarizedColors.BASE03; syntax_theme_name = "solarized-dark"
            else: 
                bg_color = SolarizedColors.BASE3; syntax_theme_name = "solarized-light"
            syntax = Syntax(ini_content, "ini", theme=syntax_theme_name, background_color=bg_color, line_numbers=False, word_wrap=True)
            console.print(syntax)
        except Exception as e:
            console.print(styled(f"Error reading config file: {str(e)}", "error"))
    else:
        console.print(styled(f"Configuration file '{config_file_path}' does not exist (or migration failed).", "info"))

@config.command(name="path", help="Show the path to the configuration file.")
def config_path():
    console.print(styled(str(get_config_path()), "primary"))


@cli.command(name="theme")
@click.argument("theme_name", type=click.Choice(["mono", "mono-light", "solarized", "solarized-light"], case_sensitive=False))
def set_theme(theme_name: str):
    """Change the CLI color theme."""
    from .styles import switch_theme, ColorScheme, style_manager
    
    theme_map = {
        "mono": (ColorScheme.MONOCHROME_DARK, "Monochrome Dark"),
        "mono-light": (ColorScheme.MONOCHROME_LIGHT, "Monochrome Light"),
        "solarized": (ColorScheme.SOLARIZED_DARK, "Solarized Dark"),
        "solarized-light": (ColorScheme.SOLARIZED_LIGHT, "Solarized Light"),
    }
    
    scheme, name = theme_map[theme_name.lower()]
    switch_theme(scheme) # This updates style_manager.scheme
    # Re-initialize console to pick up new theme if styles are deeply bound
    global console
    console = Console(theme=get_theme())
    console.print(styled("✓", "success") + styled(f" Switched to {name} theme.", "primary"))


def select_template_interactively(client: LiumAPIClient, skip_prompts: bool = False) -> Optional[str]:
    """Fetches templates. If skip_prompts, uses first. Else, asks to use first, then lists all if user says no."""
    try:
        templates = client.get_templates()
        if not templates: console.print(styled("No templates found.", "warning")); return None

        first_template = templates[0]
        first_template_id = first_template.get("id")
        tpl_name = first_template.get("name", "Unnamed Template")
        tpl_image = first_template.get("docker_image", "N/A")
        tpl_tag = first_template.get("docker_image_tag", "latest")
        # Full description for default prompt
        default_desc_full = f"'{tpl_name}' ({tpl_image}:{tpl_tag}, ID: ...{first_template_id[-8:] if first_template_id else 'N/A'})"
        default_desc_for_confirmation = f"'{tpl_name}' ({tpl_image}:{tpl_tag}) ID: {first_template_id}" # For --yes message

        if skip_prompts:
            if first_template_id:
                console.print(styled(f"Using default template: {default_desc_for_confirmation}", "info"))
                return first_template_id
            else:
                console.print(styled("Error: Default first template has no ID. Cannot proceed with --yes.", "error"))
                return None
        else: 
            console.print("\n" + styled(f"Default template: {default_desc_full}", "info"))
            if Prompt.ask(styled("Use this template?", "key"), default="y", console=console).lower().startswith("y"):
                if first_template_id: 
                    # console.print(styled(f"Selected default template: {default_desc_for_confirmation}", "info")) # Optional: confirm selection
                    return first_template_id
                else: console.print(styled("Error: Default template invalid. Select from list.", "error"))
            
            console.print(styled("Fetching all available templates...", "info"))
            table = Table(title=styled("Available Templates", "title"), box=None, show_header=True, show_lines=False, show_edge=False, padding=(0, 1), header_style="table.header", title_style="title", expand=True)
            table.add_column("#", style="dim", justify="right")
            table.add_column("Name", style="primary", min_width=20, max_width=30, overflow="ellipsis")
            table.add_column("Docker Image", style="info", min_width=30, max_width=45, overflow="ellipsis")
            table.add_column("Category", style="secondary", width=10)
            table.add_column("ID", style="muted", width=15, overflow="ellipsis")
            template_map = {}
            for idx, tpl in enumerate(templates, 1):
                template_map[str(idx)] = tpl.get("id")
                docker_image_full = f"{tpl.get('docker_image', 'N/A')}:{tpl.get('docker_image_tag', 'latest')}"
                table.add_row(str(idx), tpl.get("name", "N/A"), docker_image_full, tpl.get("category", "N/A"), tpl.get("id", "N/A")[:13] + "..." if tpl.get("id") else "N/A")
            console.print(table)
            console.print(styled("Enter # or full ID of template to use:", "key"))
            choice = Prompt.ask("", console=console, show_default=False).strip()
            if choice in template_map: 
                # selected_tpl_name = next((t['name'] for t in templates if t['id'] == template_map[choice]), "Selected Template")
                # console.print(styled(f"Selected template: '{selected_tpl_name}' (ID: {template_map[choice]})", "info")) # Optional
                return template_map[choice]
            elif any(tpl['id'] == choice for tpl in templates): 
                # selected_tpl_name = next((t['name'] for t in templates if t['id'] == choice), "Selected Template")
                # console.print(styled(f"Selected template: '{selected_tpl_name}' (ID: {choice})", "info")) # Optional
                return choice
            else: console.print(styled("Invalid selection.", "error")); return None
    except requests.exceptions.RequestException as e: console.print(styled(f"API Error fetching templates: {str(e)}", "error")); return None
    except Exception as e: console.print(styled(f"Error processing templates: {str(e)}", "error")); return None

@cli.command(name="up", help="Rent pod(s) on executor(s) specified by Name (Executor HUID/UUID).")
@click.argument("executor_names_or_ids", type=str, nargs=-1)
@click.option("--prefix", "pod_name_prefix_opt", type=str, required=False, help="Prefix for pod names if multiple executors are targeted. If single executor, this is the exact pod name.")
@click.option("--template-id", "template_id_option", type=str, required=False, help="The UUID of the template to use (optional).")
@click.option("-y", "--yes", "skip_all_prompts", is_flag=True, help="Skip all confirmations and use default first template if --template-id is not set.")
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def rent_machine(
    executor_names_or_ids: Tuple[str, ...], 
    template_id_option: Optional[str], 
    skip_all_prompts: bool,
    api_key: Optional[str],
    pod_name_prefix_opt: Optional[str] 
):
    """Rents pod(s) on specified executor(s).

    EXECUTOR_NAMES_OR_IDS: Space-separated or comma-separated list of executor Names (HUIDs from `lium ls`)
    or full executor UUIDs.
    Example: lium up huid1 huid2,huid3 --prefix my-pods --template-id ...
    """
    if not api_key: api_key = get_api_key()
    if not api_key: console.print(styled("Error: No API key found.", "error")); return
    ssh_public_keys = get_ssh_public_keys()
    if not ssh_public_keys: console.print(styled("Error: No SSH public keys found.", "error")); return
    client = LiumAPIClient(api_key)

    template_id_to_use = template_id_option
    if not template_id_to_use:
        template_id_to_use = select_template_interactively(client, skip_prompts=skip_all_prompts)
        if not template_id_to_use:
            return 
        # If interactive and successful, select_template_interactively doesn't print "Using..."
        # Only print if it was explicitly provided, or skip_prompts (default) was used.
        # This is now handled inside select_template_interactively for the --yes case.
        # For interactive choice, no extra message is needed here.
    elif template_id_option: # Only if --template-id was directly passed
        console.print(styled(f"Using provided template: ...{template_id_to_use[-12:]}", "info"))

    raw_identifiers = []
    for item in executor_names_or_ids: raw_identifiers.extend(item.strip() for item in item.split(',') if item.strip())
    target_identifiers = [ident for ident in raw_identifiers if ident]
    if not target_identifiers: console.print(styled("Error: No executor Names (HUIDs) or UUIDs provided.", "error")); return

    executors_to_process: List[Dict[str, Any]] = []
    all_executors_data = None # Fetched on demand
    failed_resolutions = []

    for i, identifier in enumerate(target_identifiers):
        executor_id_to_rent = None
        # pod_name_for_api will be the HUID of the executor machine
        pod_name_for_api = identifier # Placeholder, will be replaced by HUID or kept as UUID if HUID fails
        
        is_likely_huid = bool(re.match(r"^[a-z]+-[a-z]+-[0-9a-f]{2}$", identifier.lower()))

        if all_executors_data is None: # Fetch only once, if needed
            try: all_executors_data = client.get_executors()
            except Exception as e: console.print(styled(f"Critical Error: Could not fetch executor list: {str(e)}", "error")); return

        found_executor_for_id = False
        if is_likely_huid:
            for executor in all_executors_data:
                ex_id = executor.get("id", "")
                current_huid = generate_human_id(ex_id)
                if current_huid == identifier.lower():
                    executor_id_to_rent = ex_id
                    pod_name_for_api = current_huid # Use actual HUID for API
                    found_executor_for_id = True; break
        else: # Assume it's a UUID, try to find it and its HUID
            for executor in all_executors_data:
                ex_id = executor.get("id", "")
                if ex_id == identifier:
                    executor_id_to_rent = ex_id
                    pod_name_for_api = generate_human_id(ex_id) # Get HUID for API name
                    found_executor_for_id = True; break
        
        if not found_executor_for_id:
            failed_resolutions.append(identifier)
            continue
        
        # Final pod name for this specific instance (if multiple from same prefix)
        final_instance_name = pod_name_prefix_opt
        if len(target_identifiers) > 1:
            # Use the API pod name (executor HUID/UUID) as base for indexed name if no prefix
            base_for_indexing = pod_name_prefix_opt or pod_name_for_api 
            final_instance_name = f"{base_for_indexing}-{i+1}"
        elif pod_name_prefix_opt: # Single target, and prefix_opt is given
             final_instance_name = pod_name_prefix_opt
        else: # Single target, no prefix_opt given, use the executor HUID/UUID for the instance name
             final_instance_name = pod_name_for_api

        executors_to_process.append({
            "executor_id": executor_id_to_rent, 
            "pod_name_for_api": final_instance_name, # This is the unique name for THIS pod instance
            "original_ref": identifier
        })
    if failed_resolutions: console.print(styled(f"Warning: Unresolved: {', '.join(failed_resolutions)}", "warning"))
    if not executors_to_process: console.print(styled("No valid executors to process.", "info")); return
    
    console.print("\n" + styled("Executors to be acquired:", "header"))
    for proc_info in executors_to_process:
        console.print(f"  - {proc_info['original_ref']}") # Simplified: only original ref
    # Removed: console.print(styled(f"(Using Template ID: ...)", "dim"))
    console.print("") # Keep one spacer for readability before prompt

    if not skip_all_prompts:
        if not Prompt.ask(styled(f"Continue? ({len(executors_to_process)} pod(s))", "key"), default="n", console=console).lower().startswith("y"):
            console.print(styled("Operation cancelled.", "info")); return

    success_count = 0; failure_count = 0; failed_details = []
    for proc_info in executors_to_process:
        executor_id, pod_name_for_api, original_ref = proc_info['executor_id'], proc_info['pod_name_for_api'], proc_info['original_ref']
        try:
            client.rent_pod(executor_id=executor_id, pod_name=pod_name_for_api, template_id=template_id_to_use, user_public_keys=ssh_public_keys)
            success_count += 1
        except requests.exceptions.HTTPError as e:
            error_message = f"API Error {e.response.status_code}"; failure_count += 1
            try: error_details = e.response.json(); detail_msg = error_details.get('detail'); error_message += f" - {detail_msg if isinstance(detail_msg, str) else json.dumps(detail_msg)}" 
            except json.JSONDecodeError: error_message += f" - {e.response.text[:70]}"
            failed_details.append(f"'{original_ref}' (as '{pod_name_for_api}'): {error_message}")
        except Exception as e: 
            failed_details.append(f"'{original_ref}' (as '{pod_name_for_api}'): Unexpected error: {str(e)[:70]}"); failure_count += 1
  
    if success_count > 0: console.print(styled(f"Successfully acquired {success_count} pod(s).", "success"))
    if failure_count > 0: 
        console.print(styled(f"Failed to acquire {failure_count} pod(s):", "error"))
        for detail in failed_details:
            console.print(styled(f"  - {detail}", "error"))
    if success_count > 0: console.print(styled("Use 'lium ps' to check status.", "info"))
    elif not executors_to_process and not failed_resolutions : console.print(styled("No action taken.", "info"))


@cli.command(name="down", help="Unrent/terminate one or more pods. Use Name (HUID) or --all.")
@click.argument("pod_names", type=str, nargs=-1, required=False) # Now nargs=-1
@click.option("--all", "terminate_all", is_flag=True, help="Terminate all active pods.")
@click.option("--yes", "-y", "skip_confirmation", is_flag=True, help="Skip confirmation prompts.") # Added -y alias
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def down_pod(pod_names: Optional[Tuple[str, ...]], terminate_all: bool, skip_confirmation: bool, api_key: Optional[str]):
    """Unrents/terminates pod(s) identified by Name(s) (HUID) or all active pods.
    
    POD_NAMES: Space-separated or comma-separated list of pod Names (HUIDs).
    Example: lium down name1 name2,name3
    """
    if not api_key: api_key = get_api_key()
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

    console.print("\n" + styled("Executors to release", "header"))
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


@cli.command(name="exec", help="Execute a command on a running pod via SSH.")
@click.argument("pod_name_huid", type=str)
@click.argument("command_to_run", type=str)
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
def execute_command_on_pod(pod_name_huid: str, command_to_run: str, api_key: Optional[str]):
    """Executes COMMAND_TO_RUN on the pod identified by POD_NAME_HUID."""
    if not api_key: api_key = get_api_key()
    if not api_key: console.print(styled("Error:", "error") + styled(" No API key found.", "primary")); return

    ssh_key_path_str = get_config_value("ssh.key_path")
    if not ssh_key_path_str:
        console.print(styled("Error: SSH key path not configured. Use 'lium config set ssh.key_path /path/to/your/private_key'", "error"))
        return
    
    # Note: paramiko needs the *private* key. get_ssh_public_keys() was for API.
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

    console.print(styled(f"Connecting to '{pod_name_huid}' ({host}:{port} as {user}) to run: {command_to_run}", "info"))

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
        
        stdin, stdout, stderr = ssh_client.exec_command(command_to_run, get_pty=True)
        
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


# Add the config command group to the main cli group
cli.add_command(config)

def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main() 