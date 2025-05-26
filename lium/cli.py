"""Main CLI entry point for Lium."""

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.box import ROUNDED
from rich.prompt import Prompt
from typing import Optional, Dict, List, Any, Tuple
from collections import defaultdict
import re

from .api import LiumAPIClient
from .config import get_api_key, save_api_key
from .styles import get_theme, styled, SolarizedColors


# Create console with our custom theme
console = Console(theme=get_theme())


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
    ram_total = ram.get("total", 0)  # Already in KB, convert to MiB
    disk_free = hard_disk.get("free", 0)  # Already in MB
    
    # Network metrics
    upload_speed = network.get("upload_speed", 0) or 0
    download_speed = network.get("download_speed", 0) or 0
    
    return {
        'price_per_hour': price_per_gpu,
        'gpu_capacity': gpu_capacity,
        'ram_total': ram_total / 1024,  # Convert to MiB
        'disk_free': disk_free,
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
        box=ROUNDED,
        border_style="table.border",
        header_style="table.header",
        title_style="title",
        show_lines=True,
        padding=(0, 1),
    )
    
    # Add columns
    table.add_column("GPU Type", style="executor.gpu", no_wrap=True)
    table.add_column("Min $/GPU/Hour", style="executor.price", justify="right")
    table.add_column("Max $/GPU/Hour", style="executor.price", justify="right")
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
    console.print("\n" + styled("Enter GPU type to see detailed instances (e.g., '4090', 'H100') or press Enter to exit: ", "key"))
    
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
    pareto_results = calculate_pareto_frontier(executors)
    
    # Filter for Pareto optimal executors
    pareto_optimal_executors = [executor for executor, is_pareto in pareto_results if is_pareto]
    
    total_for_type = len(executors)
    shown_count = len(pareto_optimal_executors)
    
    title_message = f"Available {gpu_type} Executors (Showing {shown_count}/{total_for_type} Pareto optimal)"
    
    # Create detailed table with many columns
    table = Table(
        title=styled(title_message, "title"),
        box=ROUNDED,
        border_style="table.border",
        header_style="table.header",
        title_style="title",
        show_lines=True,
        padding=(0, 1),
    )
    
    # Add columns - reorganized for better readability, removed Pareto marker and GPU%
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
    table.add_column("Location", style="executor.location")
    
    # Add rows for Pareto optimal executors only
    for idx, executor in enumerate(pareto_optimal_executors):
        # Extract all metrics
        metrics = extract_metrics(executor)
        gpu_count = executor.get("specs", {}).get("gpu", {}).get("count", 1)
        config = f"{gpu_count}x{gpu_type}"
        
        # Location
        location_data = executor.get("location", {})
        country = location_data.get('country', location_data.get('country_code', 'Unknown'))
        
        # Add row with alternating background
        style = "table.row.odd" if idx % 2 == 0 else "table.row.even"
        table.add_row(
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
    
    # Show summary with Pareto statistics
    total_gpus_in_type = sum(e.get("specs", {}).get("gpu", {}).get("count", 0) for e in executors)
    avg_price_per_gpu = sum(e.get("price_per_hour", 0) / e.get("specs", {}).get("gpu", {}).get("count", 1) 
                           for e in executors) / len(executors) if executors else 0
    
    summary_content = Text()
    summary_content.append(f"\n{gpu_type} Summary:\n", style="header")
    summary_content.append(f"Showing {shown_count} Pareto optimal executors out of {total_for_type} total for this type.\n", style="secondary")
    summary_content.append("Total GPUs in type: ", style="secondary")
    summary_content.append(f"{total_gpus_in_type}\n", style="number")
    summary_content.append("Average $/GPU/hour (all instances): ", style="secondary")
    summary_content.append(f"${avg_price_per_gpu:.2f}", style="executor.price")
    
    summary = Panel(
        summary_content,
        title=styled("Summary", "panel.title"),
        border_style="panel.border",
        box=ROUNDED,
        expand=False,
        padding=(1, 2),
    )
    console.print(summary)
    
    # Add legend
    legend = Panel(
        "VRAM/RAM/Disk in GB | PCIe in MB/s | Mem in GB/s | Net in Mbps",
        title=styled("Legend", "panel.title"),
        border_style="panel.border",
        box=ROUNDED,
        expand=False,
        padding=(1, 2),
    )
    console.print(legend)


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
            # This else should not be reached if filter logic is correct
            # else: 
            #    console.print(styled(f"GPU type '{selected_gpu}' not found in grouped data.", "error"))
        
    except Exception as e:
        console.print(styled("Error:", "error") + styled(f" Failed to fetch executors: {str(e)}", "primary"))


@cli.group()
def config():
    """Manage Lium configuration."""
    pass


@config.command(name="set-api-key")
@click.argument("api_key")
def set_api_key(api_key: str):
    """Set the API key for Lium."""
    save_api_key(api_key)
    console.print(styled("✓", "success") + styled(" API key saved successfully.", "primary"))


@cli.command(name="theme")
@click.argument("theme_name", type=click.Choice(["mono", "mono-light", "solarized", "solarized-light"], case_sensitive=False))
def set_theme(theme_name: str):
    """Change the CLI color theme."""
    from .styles import switch_theme, ColorScheme
    
    theme_map = {
        "mono": (ColorScheme.MONOCHROME_DARK, "Monochrome Dark"),
        "mono-light": (ColorScheme.MONOCHROME_LIGHT, "Monochrome Light"),
        "solarized": (ColorScheme.SOLARIZED_DARK, "Solarized Dark"),
        "solarized-light": (ColorScheme.SOLARIZED_LIGHT, "Solarized Light"),
    }
    
    scheme, name = theme_map[theme_name.lower()]
    switch_theme(scheme)
    console.print(styled("✓", "success") + styled(f" Switched to {name} theme.", "primary"))


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main() 