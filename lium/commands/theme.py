"""Theme management command for Lium CLI."""

import click

from ..styles import styled


@click.command(name="theme")
@click.argument("theme_name", type=click.Choice(["mono", "mono-light", "solarized", "solarized-light"], case_sensitive=False))
def theme_command(theme_name: str):
    """Change the CLI color theme."""
    from ..styles import switch_theme, ColorScheme, style_manager, get_theme
    from rich.console import Console
    
    theme_map = {
        "mono": (ColorScheme.MONOCHROME_DARK, "Monochrome Dark"),
        "mono-light": (ColorScheme.MONOCHROME_LIGHT, "Monochrome Light"),
        "solarized": (ColorScheme.SOLARIZED_DARK, "Solarized Dark"),
        "solarized-light": (ColorScheme.SOLARIZED_LIGHT, "Solarized Light"),
    }
    
    scheme, name = theme_map[theme_name.lower()]
    switch_theme(scheme) # This updates style_manager.scheme
    # Re-initialize console to pick up new theme if styles are deeply bound
    from ..helpers import console as global_console
    global_console = Console(theme=get_theme())
    global_console.print(styled("✓", "success") + styled(f" Switched to {name} theme.", "primary")) 