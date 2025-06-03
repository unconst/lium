"""List executors command for Lium CLI."""

import click
from typing import Optional

from ..config import get_or_set_api_key
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


@click.command(name="ls")
@click.option("--api-key", envvar="LIUM_API_KEY", help="API key for authentication")
@click.argument("gpu_type_filter", required=False, type=str)
def ls_command(api_key: Optional[str], gpu_type_filter: Optional[str]):
    """List all available executors.

    If GPU_TYPE_FILTER is provided, it directly shows details for that GPU type.
    Otherwise, it shows a summary and prompts for selection.
    """
    # Get API key from various sources
    if not api_key:
        api_key = get_or_set_api_key()
 
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