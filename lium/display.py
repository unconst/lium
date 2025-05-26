"""Display utilities using the Lium style toolkit."""

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.prompt import Prompt, Confirm
from rich.syntax import Syntax
from rich.panel import Panel
from rich.box import ROUNDED, HEAVY, DOUBLE
from typing import Optional, List, Dict, Any

from .styles import get_theme, styled, SolarizedColors


class StyledConsole:
    """A console wrapper that applies consistent styling."""
    
    def __init__(self):
        self.console = Console(theme=get_theme())
    
    def print_header(self, text: str) -> None:
        """Print a styled header."""
        self.console.print(styled(f"\n{text}\n", "header"))
    
    def print_subheader(self, text: str) -> None:
        """Print a styled subheader."""
        self.console.print(styled(text, "subtitle"))
    
    def print_success(self, message: str) -> None:
        """Print a success message."""
        self.console.print(styled("✓ ", "success") + styled(message, "primary"))
    
    def print_error(self, message: str) -> None:
        """Print an error message."""
        self.console.print(styled("✗ ", "error") + styled(message, "primary"))
    
    def print_warning(self, message: str) -> None:
        """Print a warning message."""
        self.console.print(styled("⚠ ", "warning") + styled(message, "primary"))
    
    def print_info(self, message: str) -> None:
        """Print an info message."""
        self.console.print(styled("ℹ ", "info") + styled(message, "primary"))
    
    def print_key_value(self, key: str, value: Any) -> None:
        """Print a key-value pair with consistent styling."""
        self.console.print(styled(f"{key}: ", "key") + styled(str(value), "value"))
    
    def print_code(self, code: str, language: str = "python") -> None:
        """Print syntax-highlighted code."""
        syntax = Syntax(
            code, 
            language, 
            theme="solarized-dark",
            background_color=SolarizedColors.BASE03,
            line_numbers=True
        )
        self.console.print(syntax)
    
    def create_panel(self, content: str, title: Optional[str] = None, box_style: str = "rounded") -> Panel:
        """Create a styled panel."""
        box_types = {
            "rounded": ROUNDED,
            "heavy": HEAVY,
            "double": DOUBLE
        }
        
        return Panel(
            content,
            title=styled(title, "panel.title") if title else None,
            border_style="panel.border",
            box=box_types.get(box_style, ROUNDED),
            padding=(1, 2)
        )
    
    def create_progress(self) -> Progress:
        """Create a styled progress bar."""
        return Progress(
            SpinnerColumn(style="spinner"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style="progress.bar"),
            TaskProgressColumn(),
            console=self.console
        )
    
    def prompt(self, question: str, default: Optional[str] = None) -> str:
        """Styled prompt for user input."""
        prompt_text = styled(question, "key")
        return Prompt.ask(prompt_text, default=default, console=self.console)
    
    def confirm(self, question: str, default: bool = False) -> bool:
        """Styled confirmation prompt."""
        prompt_text = styled(question, "key")
        return Confirm.ask(prompt_text, default=default, console=self.console)


class ExecutorDisplay:
    """Display utilities specifically for executor data."""
    
    def __init__(self):
        self.console = StyledConsole()
    
    def format_gpu_info(self, gpu_details: List[Dict[str, Any]]) -> str:
        """Format GPU information with proper styling."""
        if not gpu_details:
            return styled("No GPU", "muted")
        
        gpu = gpu_details[0]
        name = gpu.get('name', 'Unknown')
        memory_mb = gpu.get('capacity', 0)
        memory_gb = memory_mb / 1024
        
        return f"{styled(name, 'executor.gpu')} ({styled(f'{memory_gb:.1f} GB', 'number')})"
    
    def format_price(self, price: float) -> str:
        """Format price with currency styling."""
        return styled(f"${price:.2f}/hour", "executor.price")
    
    def format_location(self, location: Dict[str, Any]) -> str:
        """Format location information."""
        city = location.get('city', 'Unknown')
        country = location.get('country_code', 'Unknown')
        return styled(f"{city}, {country}", "executor.location")
    
    def format_status(self, active: Optional[bool]) -> str:
        """Format executor status with appropriate styling."""
        if active is None:
            return styled("Available", "executor.available")
        elif active:
            return styled("Active", "executor.active")
        else:
            return styled("Inactive", "executor.inactive")
    
    def display_executor_details(self, executor: Dict[str, Any]) -> None:
        """Display detailed information about a single executor."""
        self.console.print_header(f"Executor: {executor.get('machine_name', 'Unknown')}")
        
        # Basic info
        self.console.print_key_value("ID", executor.get('id', 'N/A'))
        self.console.print_key_value("Status", self.format_status(executor.get('active')))
        self.console.print_key_value("Price", self.format_price(executor.get('price_per_hour', 0)))
        self.console.print_key_value("Location", self.format_location(executor.get('location', {})))
        
        # Specs
        specs = executor.get('specs', {})
        if specs:
            self.console.print_subheader("\nSpecifications:")
            
            # GPU
            gpu_details = specs.get('gpu', {}).get('details', [])
            self.console.print_key_value("GPU", self.format_gpu_info(gpu_details))
            
            # RAM
            ram_total = specs.get('ram', {}).get('total', 0)
            ram_gb = ram_total / 1024 / 1024
            self.console.print_key_value("RAM", styled(f"{ram_gb:.1f} GB", "number"))
            
            # CPU
            cpu_info = specs.get('cpu', {})
            if cpu_info:
                cpu_model = cpu_info.get('model', 'Unknown')
                cpu_count = cpu_info.get('count', 0)
                self.console.print_key_value("CPU", f"{cpu_model} ({cpu_count} cores)")


# Example usage functions
def example_usage():
    """Example of how to use the styled console."""
    console = StyledConsole()
    
    # Headers and messages
    console.print_header("Lium Executor Management")
    console.print_success("Connected to API successfully")
    console.print_info("Fetching executor list...")
    
    # Progress bar example
    with console.create_progress() as progress:
        task = progress.add_task("Loading executors...", total=100)
        for i in range(100):
            progress.update(task, advance=1)
    
    # Panel example
    panel = console.create_panel(
        "Welcome to Lium CLI!\nManage your compute executors with style.",
        title="Welcome",
        box_style="double"
    )
    console.console.print(panel)
    
    # Code example
    console.print_subheader("\nExample API Usage:")
    console.print_code("""
from lium.api import LiumAPIClient

client = LiumAPIClient(api_key)
executors = client.get_executors()
""")


if __name__ == "__main__":
    example_usage() 