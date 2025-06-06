import os
import re
import docker
import hashlib
import sys
import json
from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.console import Group
from rich.prompt import Prompt
from rich.console import Console
from rich import print as rprint
from rich.box import ROUNDED, MINIMAL
from datetime import datetime, timezone
from collections import defaultdict, OrderedDict
from pathlib import Path
from .styles import get_theme, styled
from .config import get_or_set_docker_credentials, get_config_value, set_config_value
from typing import Any, Dict, List, Optional, Tuple

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
    """Extract all metrics, keeping them in consistent base units where possible for later formatting."""
    specs = executor.get("specs", {})
    gpu_details_list = specs.get("gpu", {}).get("details", [])
    # Handle cases where there might be multiple GPUs, average or take first for some singular GPU specs
    # For simplicity, taking the first GPU's details if multiple are listed for pcie, mem, graphics speed.
    # Capacity should ideally be summed if representing total VRAM for multi-GPU, but API gives per-GPU capacity.
    # For now, if multiple GPUs, we'll use the first GPU's singular specs for simplicity of display.
    gpu_details = gpu_details_list[0] if gpu_details_list else {}

    hard_disk = specs.get("hard_disk", {})
    ram_data = specs.get("ram", {})
    network = specs.get("network", {})
    gpu_spec_data = specs.get("gpu", {})
    gpu_count = gpu_spec_data.get("count", 1) # Default to 1 if count is missing
    
    price_per_gpu = executor.get("price_per_hour", 0) / gpu_count if gpu_count > 0 else float('inf')
    
    # GPU metrics - ensure consistent units from API or convert to a base
    # API gives gpu_details.capacity in MiB (for NVIDIA H100 80GB, it's 81559 MiB)
    total_gpu_capacity_mib = sum(g.get("capacity", 0) for g in gpu_details_list) if gpu_details_list else 0
    # If we want per-GPU VRAM in table, then use gpu_details.get("capacity",0)
    # For the Pareto and table, let's use per-GPU VRAM for now if multi-GPU means identical cards
    per_gpu_capacity_mib = gpu_details.get("capacity", 0) 

    pcie_speed_mbs = gpu_details.get("pcie_speed", 0)  # Assuming API gives MB/s
    memory_speed_gbs = gpu_details.get("memory_speed", 0) # Assuming API gives GB/s (e.g. HBM speed)
    graphics_speed_tflops = gpu_details.get("graphics_speed", 0) # Assuming API gives TFLOPs
    gpu_utilization = gpu_details.get("gpu_utilization", 0) # Percentage
    
    # System metrics
    ram_total_kb = ram_data.get("total", 0)  # API gives ram.total in KB
    disk_free_kb = hard_disk.get("free", 0) # API gives hard_disk.free in KB
    
    # Network metrics - assuming API gives Mbps
    upload_speed_mbps = network.get("upload_speed", 0) or 0
    download_speed_mbps = network.get("download_speed", 0) or 0
    
    return {
        'price_per_gpu_hour': price_per_gpu, # Renamed for clarity in format_metric
        'vram_per_gpu_mib': per_gpu_capacity_mib, # VRAM per GPU in MiB
        'ram_total_kb': ram_total_kb, # Total system RAM in KB
        'disk_free_kb': disk_free_kb, # Free disk space in KB
        'pcie_speed_mbs': pcie_speed_mbs,
        'gpu_memory_speed_gbs': memory_speed_gbs,
        'graphics_speed_tflops': graphics_speed_tflops,
        'gpu_utilization_percent': gpu_utilization,
        'net_upload_mbps': upload_speed_mbps,
        'net_download_mbps': download_speed_mbps,
    }


def dominates(metrics_a: Dict[str, float], metrics_b: Dict[str, float]) -> bool:
    """Check if executor A dominates executor B in Pareto sense."""
    # Define which metrics should be minimized (lower is better)
    minimize_metrics = {'price_per_gpu_hour', 'gpu_utilization_percent'}
    
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


def format_metric(value: Optional[float], metric_key: str) -> str:
    """Format metric values for display with appropriate units."""
    if value is None or value == float('inf') or (isinstance(value, (int,float)) and value < 0): # Treat negative as N/A for most metrics
        return "N/A"
    if value == 0 and metric_key not in ['gpu_utilization_percent']: # Allow 0% utilization
         # For speeds/capacities, 0 often means N/A or not present
         if metric_key not in ['price_per_gpu_hour']: # Allow $0.00 price
            return "N/A" if metric_key != 'graphics_speed_tflops' else "0" # TFLOPs can be 0

    if metric_key == 'price_per_gpu_hour': return f"${value:.2f}"
    if metric_key == 'vram_per_gpu_mib': return f"{value / 1024:.0f}"  # MiB to GB
    if metric_key == 'ram_total_kb': return f"{value / 1024 / 1024:.0f}" # KB to GB
    if metric_key == 'disk_free_kb': return f"{value / 1024 / 1024:.0f}" # KB to GB
    if metric_key == 'pcie_speed_mbs': return f"{int(value)}" # MB/s
    if metric_key == 'gpu_memory_speed_gbs': return f"{value:.0f}" # GB/s
    if metric_key == 'graphics_speed_tflops': return f"{value:.0f}" # TFLOPs
    if metric_key == 'gpu_utilization_percent': return f"{value:.0f}%"
    if metric_key in ['net_upload_mbps', 'net_download_mbps']: return f"{int(value)}" # Mbps
    
    return str(value) # Fallback


def group_executors_by_gpu(executors: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """Group executors by GPU model."""
    grouped = defaultdict(list)
    
    for executor in executors:
        machine_name = executor.get("machine_name", "Unknown")
        gpu_model = extract_gpu_model(machine_name)
        grouped[gpu_model].append(executor)
    
    return dict(grouped)

def show_pod(pod: Dict):
    general = Table(
        box=None,
        show_header=False,
        show_lines=False,
        show_edge=False,
        padding=(0, 1),
        header_style="table.header",
        title_style="title",
        expand=True
    )
    general.add_column(justify="right", style="bold")
    general.add_column(style="dim")
    general.add_row("Pod Name", pod['pod_name'])
    general.add_row("Status", pod['status'])
    general.add_row("SSH", pod['ssh_connect_cmd'])
    general.add_row("Created", pod['created_at'])
    general.add_row("Updated", pod['updated_at'])
    general.add_row("ID", pod['id'])

    # Template
    template = Table(
        box=None,
        show_header=False,
        show_lines=False,
        show_edge=False,
        padding=(0, 1),
        header_style="table.header",
        title_style="title",
        expand=True
    )
    template.add_column(justify="right", style="bold")
    template.add_column(style="dim")
    template.add_row("Template", pod['template']['name'])
    template.add_row("Image", pod['template']['docker_image'])
    template.add_row("Tag", pod['template']['docker_image_tag'])

    # Resources
    resources = Table(
        title="Hardware Specs",
        box=None,
        show_header=True,
        show_lines=True,
        show_edge=False,
        padding=(0, 1),
        header_style="table.header",
        title_style="title",
        expand=True
    )
    resources.add_column("Component", style="bold")
    resources.add_column("Details", style="dim")

    resources.add_row("CPU", f"{pod['cpu_name']} ({pod['executor']['specs']['cpu']['count']} cores)")
    resources.add_row("GPU", f"{pod['gpu_name']} ({pod['gpu_count']} total)")
    resources.add_row("GPU Driver", pod['executor']['specs']['gpu']['driver'])
    resources.add_row("GPU Utilization", f"{pod['executor']['specs']['gpu']['details'][0]['gpu_utilization']}%")
    resources.add_row("RAM", f"{pod['ram_total'] / 1e6:.2f} GB total")
    resources.add_row("RAM Utilization", f"{pod['executor']['specs']['ram']['utilization']}%")
    resources.add_row("OS", pod['executor']['specs']['os'])
    resources.add_row("Network", f"{pod['executor']['specs']['network']['upload_speed']}↑ / {pod['executor']['specs']['network']['download_speed']}↓ Mbps")
    resources.add_row("Price", f"${pod['executor']['price_per_hour']:.4f} / hour")

    # Additional Information: Cost and Uptime
    cost_so_far_display = "N/A"
    uptime_hours_display = "N/A"
    created_at_str = pod.get("created_at", "")
    total_price_per_hour = pod['executor'].get('price_per_hour', 0)
    if created_at_str:
        try:
            if created_at_str.endswith('Z'):
                dt_created = datetime.fromisoformat(created_at_str.replace('Z', '+00:00'))
            elif '+' not in created_at_str and '-' not in created_at_str[10:]:
                dt_created = datetime.fromisoformat(created_at_str).replace(tzinfo=timezone.utc)
            else:
                dt_created = datetime.fromisoformat(created_at_str)
            now_utc = datetime.now(timezone.utc)
            duration = now_utc - dt_created
            duration_hours = duration.total_seconds() / 3600
            if duration_hours > 0:
                uptime_hours_display = f"{duration_hours:.2f} hours"
                cost_so_far_display = f"${(duration_hours * float(total_price_per_hour)):.2f}"
            else:
                uptime_hours_display = "<0.1 hours"
                cost_so_far_display = "$0.00"
        except ValueError:
            uptime_hours_display = "Date Error"
            cost_so_far_display = "Date Error"

    resources.add_row("Uptime", uptime_hours_display)
    resources.add_row("Cost So Far", cost_so_far_display)

    # Ports
    ports = Table(
        title="Port Mapping",
        box=None,
        show_header=True,
        show_lines=False,
        show_edge=False,
        padding=(0, 1),
        header_style="table.header",
        title_style="title",
        expand=True
    )
    ports.add_column("Internal Port", justify="right", style="bold")
    ports.add_column("External Port", justify="left", style="dim")
    for k, v in pod['ports_mapping'].items():
        ports.add_row(str(k), str(v))

    # Final layout
    console.print(
        Panel(
            Group(
                Panel(general, title=styled("[b]General Info", 'info')),
                Panel(template, title=styled("[b]Template Info", 'info')),
                Panel(resources, title=styled("[b]System Resources", 'info')),
                Panel(ports, title=styled("[b]Ports Mapping", 'info')),
            ),
            title=styled(f"[bold]POD: {pod['pod_name']}", 'info'),
            border_style="dim",
        )
    )


def show_gpu_summary(executors: List[Dict[str, Any]]) -> Optional[str]:
    """Show summary of GPUs grouped by type and return selected type."""
    grouped = group_executors_by_gpu(executors)
    
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
    
    # Create summary table with rotated layout
    table = Table(
        title=styled(f"GPU Types Summary ({len(executors)} total executors)", "title"),
        box=None, show_header=True, show_lines=False, show_edge=False,
        padding=(0, 1),
        header_style="table.header", title_style="title",
        expand=True)
    
    # Add columns for each GPU type
    table.add_column("Metric", style="executor.gpu", no_wrap=True)
    for data in gpu_price_data:
        table.add_column(data['gpu_type'], style="executor.gpu", justify="right")
    
    # Add rows for each metric
    min_prices = ["Min $/GPU"] + [f"${data['min_price']:.2f}" for data in gpu_price_data]
    max_prices = ["Max $/GPU"] + [f"${data['max_price']:.2f}" for data in gpu_price_data]
    availabilities = ["Available"] + [str(data['total_gpus']) for data in gpu_price_data]
    
    table.add_row(*min_prices)
    table.add_row(*max_prices)
    table.add_row(*availabilities)
    
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


def store_executor_selection(gpu_type: str, executors: List[Dict[str, Any]]) -> None:
    """Store the last executor selection for a GPU type."""
    selection_data = {
        'gpu_type': gpu_type,
        'timestamp': datetime.now().isoformat(),
        'executors': []
    }
    
    for executor in executors:
        selection_data['executors'].append({
            'id': executor.get('id'),
            'huid': generate_human_id(executor.get('id', '')),
            'price_per_hour': executor.get('price_per_hour'),
            'gpu_count': executor.get('specs', {}).get('gpu', {}).get('count', 1),
            'location': executor.get('location', {}).get('country', 'Unknown')
        })
    
    set_config_value('last_selection.data', json.dumps(selection_data))


def get_last_executor_selection() -> Optional[Dict[str, Any]]:
    """Retrieve the last executor selection."""
    selection_json = get_config_value('last_selection.data')
    if selection_json:
        try:
            return json.loads(selection_json)
        except json.JSONDecodeError:
            return None
    return None


def resolve_executor_indices(indices: List[str]) -> Tuple[List[str], Optional[str]]:
    """
    Resolve executor indices from the last selection.
    Returns (resolved_executor_ids, error_message)
    """
    last_selection = get_last_executor_selection()
    if not last_selection:
        return [], "No previous executor selection found. Please run 'lium ls <GPU_TYPE>' first."
    
    executors = last_selection.get('executors', [])
    if not executors:
        return [], "No executors in last selection."
    
    resolved_ids = []
    failed_resolutions = []
    
    for index_str in indices:
        try:
            index = int(index_str)
            if 1 <= index <= len(executors):
                executor_data = executors[index - 1]
                resolved_ids.append(executor_data['id'])
            else:
                failed_resolutions.append(f"{index_str} (index out of range 1-{len(executors)})")
        except ValueError:
            failed_resolutions.append(f"{index_str} (not a valid index)")
    
    error_msg = None
    if failed_resolutions:
        error_msg = f"Could not resolve indices: {', '.join(failed_resolutions)}"
    
    return resolved_ids, error_msg


def show_gpu_type_details(gpu_type: str, executors: List[Dict[str, Any]]):
    """Show detailed information for Pareto optimal executors of a specific GPU type."""
    # Store the selection for later use with indices
    store_executor_selection(gpu_type, executors)
    
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
        # title=styled(title_message, "title"), # Title removed as per user's last implicit edit
        box=None,
        show_header=True,
        show_lines=False,
        show_edge=False,
        padding=(0, 1),
        header_style="table.header",
        # title_style="title", # No longer needed if title is removed
        expand=True
    )
    
    # Add columns - reorganized for better readability, added index column
    table.add_column("#", style="dim", justify="right", width=3)  # Index column
    table.add_column("Pod", style="dim", no_wrap=False, min_width=15, max_width=20)
    table.add_column("Config", style="executor.gpu", no_wrap=True)
    table.add_column("$/GPU/hr", style="executor.price", justify="right")
    table.add_column("VRAM (GB)", style="number", justify="right")
    table.add_column("RAM (GB)", style="number", justify="right")
    table.add_column("Disk (GB)", style="number", justify="right")
    table.add_column("PCIe (MB/s)", style="number", justify="right")
    table.add_column("Mem (GB/s)", style="number", justify="right")
    table.add_column("TFLOPs", style="number", justify="right")
    table.add_column("Net ↑ (Mbps)", style="info", justify="right")
    table.add_column("Net ↓ (Mbps)", style="info", justify="right")
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
            str(idx + 1),  # Index number starting from 1
            executor_name_huid, # This is for the "Pod" column
            config,
            format_metric(metrics.get('price_per_gpu_hour'), 'price_per_gpu_hour'),
            format_metric(metrics.get('vram_per_gpu_mib'), 'vram_per_gpu_mib'),
            format_metric(metrics.get('ram_total_kb'), 'ram_total_kb'),
            format_metric(metrics.get('disk_free_kb'), 'disk_free_kb'),
            format_metric(metrics.get('pcie_speed_mbs'), 'pcie_speed_mbs'),
            format_metric(metrics.get('gpu_memory_speed_gbs'), 'gpu_memory_speed_gbs'),
            format_metric(metrics.get('graphics_speed_tflops'), 'graphics_speed_tflops'),
            format_metric(metrics.get('net_upload_mbps'), 'net_upload_mbps'),
            format_metric(metrics.get('net_download_mbps'), 'net_download_mbps'),
            country,
            style=style
        )
    
    console.print(table)
    console.print(styled('Use: `lium up #`', 'info'))


def build_docker_image(image_name:str, dockerfilepath:str):
    
    user, password = get_or_set_docker_credentials()    
    image_tag = f"{user}/{image_name}:latest"

    # --- Docker Client Initialization ---
    try:
        client = docker.from_env()
    except docker.errors.DockerException:
        print("Error: Could not connect to Docker daemon. Is Docker running? Try starting Docker with 'systemctl start docker' or ensure the Docker Desktop is running.")
        exit(1)
        
    try:
        client.login(username=user, password=password)
        print("Login successful.")
    except docker.errors.APIError as e:
        print(f"Docker Hub login failed: {e}")
        print("Please ensure your DOCKER_USERNAME and DOCKER_PASSWORD (or Access Token) are correct.")
        exit(1)

    # --- Build Docker Image ---
    print(f"Building Docker image from Dockerfile: {os.getcwd()}/{dockerfilepath}Dockerfile")
    try:
        print ('As:', dockerfilepath, image_tag)
        image, build_log = client.images.build(
            path=dockerfilepath, 
            tag=image_tag, 
            rm=True, # Remove intermediate containers
            forcerm=True # Always remove intermediate containers, even if the build fails
        )
        print ('build donw')
        for log_line in build_log:
            print (log_line)

        print(f"Pushing image {image_tag} to Docker Hub...")
        push_log_gen = client.images.push(image_tag, stream=True, decode=True)
        digest = None
        for log_line in push_log_gen:
            if "status" in log_line:
                print(f"Push status: {log_line['status']}", end="")
                if "progress" in log_line:
                    print(f" - {log_line['progress']}", end="")
                if "id" in log_line:
                    print(f" (ID: {log_line['id']})", end="")
                print() # Newline after each status update
            if "status" in log_line and "digest" in log_line["status"]:
                digest = log_line["status"].split("digest: ")[1].split(" ")[0]
            elif "error" in log_line:
                print(f"Error during push: {log_line['errorDetail']['message']}")
            elif "aux" in log_line and "Digest" in log_line["aux"]:
                digest = log_line["aux"]["Digest"]
        
        if digest:
            print(f"Image digest: {digest}")
        print(f"Image {image_tag} pushed successfully to Docker Hub.")

    except docker.errors.BuildError as e:
        print(f"Error building Docker image: {e}")
        exit(1)
    except docker.errors.APIError as e:
        print(f"Error communicating with Docker API during build: {e}")
        exit(1)
    return digest

def resolve_pod_targets(client, target_inputs):
    """
    Resolve pod targets that can be:
    - Pod HUIDs (like 'zesty-orbit-08')
    - Index numbers (like '1', '2', '3')  
    - Comma-separated combinations (like '1,2,zesty-orbit-08')
    - 'all' for all pods
    
    Returns a list of (pod_info, original_ref) tuples
    """
    try:
        active_pods = client.get_pods()
        if not active_pods:
            return [], "No active pods found."
    except Exception as e:
        return [], f"Error fetching active pods: {str(e)}"
    
    if not target_inputs:
        return [], "No pod targets specified."
    
    resolved_pods = []
    failed_resolutions = []
    
    # Handle the special case of -1 (all pods)
    if len(target_inputs) == 1 and target_inputs[0].strip() == 'all':
        for pod in active_pods:
            pod_huid = generate_human_id(pod.get("id", ""))
            resolved_pods.append((pod, "all"))
        return resolved_pods, None
    
    # Parse all target inputs (can be comma-separated)
    all_targets = []
    for target_input in target_inputs:
        all_targets.extend([t.strip() for t in target_input.split(',') if t.strip()])
    
    for target in all_targets:
        resolved = False
        
        # Try to resolve as index number
        try:
            index = int(target)
            if 1 <= index <= len(active_pods):
                pod = active_pods[index - 1]  # Convert to 0-based index
                resolved_pods.append((pod, f"#{index}"))
                resolved = True
            else:
                failed_resolutions.append(f"{target} (index out of range 1-{len(active_pods)})")
        except ValueError:
            # Not a number, try to resolve as HUID
            target_lower = target.lower()
            for pod in active_pods:
                current_huid = generate_human_id(pod.get("id", ""))
                if current_huid == target_lower:
                    resolved_pods.append((pod, target))
                    resolved = True
                    break
            
            if not resolved:
                failed_resolutions.append(target)
    
    error_msg = None
    if failed_resolutions:
        error_msg = f"Could not resolve: {', '.join(failed_resolutions)}"
    
    return resolved_pods, error_msg
