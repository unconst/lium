"""Style toolkit for Lium CLI with minimalist monochrome themes."""

from typing import Dict, Any, Optional
from rich.style import Style
from rich.theme import Theme
from enum import Enum


class ColorScheme(Enum):
    """Available color schemes for the CLI."""
    MONOCHROME_DARK = "monochrome_dark"
    MONOCHROME_LIGHT = "monochrome_light"
    SOLARIZED_DARK = "solarized_dark"
    SOLARIZED_LIGHT = "solarized_light"


class MonochromeColors:
    """Monochrome grayscale palette."""
    # Dark theme grays (light to dark)
    WHITE = "#ffffff"
    GRAY_95 = "#f2f2f2"
    GRAY_90 = "#e6e6e6"
    GRAY_80 = "#cccccc"
    GRAY_70 = "#b3b3b3"
    GRAY_60 = "#999999"
    GRAY_50 = "#808080"
    GRAY_40 = "#666666"
    GRAY_30 = "#4d4d4d"
    GRAY_20 = "#333333"
    GRAY_15 = "#262626"
    GRAY_10 = "#1a1a1a"
    GRAY_05 = "#0d0d0d"
    BLACK = "#000000"


class SolarizedColors:
    """Solarized color palette constants."""
    # Base colors
    BASE03 = "#002b36"  # Darkest background (dark bg)
    BASE02 = "#073642"  # Background highlight
    BASE01 = "#586e75"  # Comments / secondary text
    BASE00 = "#657b83"  # Main text on dark bg
    BASE0 = "#839496"   # Alt text on dark bg
    BASE1 = "#93a1a1"   # UI elements (light bg)
    BASE2 = "#eee8d5"   # Main background (light bg)
    BASE3 = "#fdf6e3"   # Lightest background
    
    # Accent colors
    YELLOW = "#b58900"  # Warnings, keywords
    ORANGE = "#cb4b16"  # Errors, highlights
    RED = "#dc322f"     # Critical errors, delete
    MAGENTA = "#d33682" # Strings, identifiers
    VIOLET = "#6c71c4"  # Types, tags
    BLUE = "#268bd2"    # Constants, functions
    CYAN = "#2aa198"    # Special keywords, classes
    GREEN = "#859900"   # Success, booleans


class StyleManager:
    """Manages styles and themes for the CLI."""
    
    def __init__(self, scheme: ColorScheme = ColorScheme.MONOCHROME_DARK):
        self.scheme = scheme
        self._current_theme = self._create_theme(scheme)
    
    def _create_theme(self, scheme: ColorScheme) -> Theme:
        """Create a Rich theme based on the color scheme."""
        if scheme == ColorScheme.MONOCHROME_DARK:
            return self._create_monochrome_dark_theme()
        elif scheme == ColorScheme.MONOCHROME_LIGHT:
            return self._create_monochrome_light_theme()
        elif scheme == ColorScheme.SOLARIZED_DARK:
            return self._create_solarized_dark_theme()
        elif scheme == ColorScheme.SOLARIZED_LIGHT:
            return self._create_solarized_light_theme()
        else:
            raise ValueError(f"Unknown color scheme: {scheme}")
    
    def _create_monochrome_dark_theme(self) -> Theme:
        """Create Monochrome Dark theme - minimalist grayscale."""
        return Theme({
            # Text styles
            "default": Style(color=MonochromeColors.GRAY_80),
            "primary": Style(color=MonochromeColors.GRAY_80),
            "secondary": Style(color=MonochromeColors.GRAY_60),
            "dim": Style(color=MonochromeColors.GRAY_40),
            "bright": Style(color=MonochromeColors.WHITE, bold=True),
            
            # Headers and titles
            "title": Style(color=MonochromeColors.WHITE, bold=True),
            "subtitle": Style(color=MonochromeColors.GRAY_90),
            "header": Style(color=MonochromeColors.WHITE, bold=True),
            
            # Status and feedback
            "success": Style(color=MonochromeColors.WHITE),
            "warning": Style(color=MonochromeColors.GRAY_90),
            "error": Style(color=MonochromeColors.WHITE, bold=True),
            "info": Style(color=MonochromeColors.GRAY_70),
            
            # Data display
            "key": Style(color=MonochromeColors.GRAY_90),
            "value": Style(color=MonochromeColors.GRAY_70),
            "number": Style(color=MonochromeColors.WHITE),
            "string": Style(color=MonochromeColors.GRAY_80),
            "boolean": Style(color=MonochromeColors.GRAY_80),
            
            # Table specific
            "table.header": Style(color=MonochromeColors.WHITE),
            "table.border": Style(color=MonochromeColors.GRAY_30),
            "table.row.odd": Style(bgcolor=MonochromeColors.GRAY_10),
            "table.row.even": Style(bgcolor=MonochromeColors.BLACK),
            
            # Special elements
            "highlight": Style(color=MonochromeColors.WHITE, bold=True),
            "accent": Style(color=MonochromeColors.GRAY_90),
            "muted": Style(color=MonochromeColors.GRAY_40),
            
            # Specific to executor display
            "executor.id": Style(color=MonochromeColors.GRAY_70),
            "executor.name": Style(color=MonochromeColors.WHITE),
            "executor.gpu": Style(color=MonochromeColors.WHITE),
            "executor.price": Style(color=MonochromeColors.GRAY_90),
            "executor.location": Style(color=MonochromeColors.GRAY_70),
            "executor.available": Style(color=MonochromeColors.GRAY_50),
            "executor.active": Style(color=MonochromeColors.WHITE),
            "executor.inactive": Style(color=MonochromeColors.GRAY_40),
            
            # Panels and boxes
            "panel.border": Style(color=MonochromeColors.GRAY_30),
            "panel.title": Style(color=MonochromeColors.WHITE),
            
            # Progress and spinners
            "progress.description": Style(color=MonochromeColors.GRAY_70),
            "progress.percentage": Style(color=MonochromeColors.WHITE),
            "progress.bar": Style(color=MonochromeColors.GRAY_60),
            "spinner": Style(color=MonochromeColors.GRAY_60),
        })
    
    def _create_monochrome_light_theme(self) -> Theme:
        """Create Monochrome Light theme - minimalist grayscale inverted."""
        return Theme({
            # Text styles
            "default": Style(color=MonochromeColors.GRAY_20),
            "primary": Style(color=MonochromeColors.GRAY_20),
            "secondary": Style(color=MonochromeColors.GRAY_40),
            "dim": Style(color=MonochromeColors.GRAY_60),
            "bright": Style(color=MonochromeColors.BLACK, bold=True),
            
            # Headers and titles
            "title": Style(color=MonochromeColors.BLACK, bold=True),
            "subtitle": Style(color=MonochromeColors.GRAY_10),
            "header": Style(color=MonochromeColors.BLACK, bold=True),
            
            # Status and feedback
            "success": Style(color=MonochromeColors.BLACK),
            "warning": Style(color=MonochromeColors.GRAY_10),
            "error": Style(color=MonochromeColors.BLACK, bold=True),
            "info": Style(color=MonochromeColors.GRAY_30),
            
            # Data display
            "key": Style(color=MonochromeColors.GRAY_10),
            "value": Style(color=MonochromeColors.GRAY_30),
            "number": Style(color=MonochromeColors.BLACK),
            "string": Style(color=MonochromeColors.GRAY_20),
            "boolean": Style(color=MonochromeColors.GRAY_20),
            
            # Table specific
            "table.header": Style(color=MonochromeColors.BLACK),
            "table.border": Style(color=MonochromeColors.GRAY_70),
            "table.row.odd": Style(bgcolor=MonochromeColors.GRAY_95),
            "table.row.even": Style(bgcolor=MonochromeColors.WHITE),
            
            # Special elements
            "highlight": Style(color=MonochromeColors.BLACK, bold=True),
            "accent": Style(color=MonochromeColors.GRAY_10),
            "muted": Style(color=MonochromeColors.GRAY_60),
            
            # Specific to executor display
            "executor.id": Style(color=MonochromeColors.GRAY_30),
            "executor.name": Style(color=MonochromeColors.BLACK),
            "executor.gpu": Style(color=MonochromeColors.BLACK),
            "executor.price": Style(color=MonochromeColors.GRAY_10),
            "executor.location": Style(color=MonochromeColors.GRAY_30),
            "executor.available": Style(color=MonochromeColors.GRAY_50),
            "executor.active": Style(color=MonochromeColors.BLACK),
            "executor.inactive": Style(color=MonochromeColors.GRAY_60),
            
            # Panels and boxes
            "panel.border": Style(color=MonochromeColors.GRAY_70),
            "panel.title": Style(color=MonochromeColors.BLACK),
            
            # Progress and spinners
            "progress.description": Style(color=MonochromeColors.GRAY_30),
            "progress.percentage": Style(color=MonochromeColors.BLACK),
            "progress.bar": Style(color=MonochromeColors.GRAY_40),
            "spinner": Style(color=MonochromeColors.GRAY_40),
        })
    
    def _create_solarized_dark_theme(self) -> Theme:
        """Create Solarized Dark theme."""
        return Theme({
            # Text styles
            "default": Style(color=SolarizedColors.BASE0),
            "primary": Style(color=SolarizedColors.BASE0),
            "secondary": Style(color=SolarizedColors.BASE01),
            "dim": Style(color=SolarizedColors.BASE01, dim=True),
            "bright": Style(color=SolarizedColors.BASE1),
            
            # Headers and titles
            "title": Style(color=SolarizedColors.CYAN, bold=True),
            "subtitle": Style(color=SolarizedColors.BLUE),
            "header": Style(color=SolarizedColors.VIOLET, bold=True),
            
            # Status and feedback
            "success": Style(color=SolarizedColors.GREEN, bold=True),
            "warning": Style(color=SolarizedColors.YELLOW, bold=True),
            "error": Style(color=SolarizedColors.RED, bold=True),
            "info": Style(color=SolarizedColors.BLUE),
            
            # Data display
            "key": Style(color=SolarizedColors.CYAN),
            "value": Style(color=SolarizedColors.BASE0),
            "number": Style(color=SolarizedColors.MAGENTA),
            "string": Style(color=SolarizedColors.GREEN),
            "boolean": Style(color=SolarizedColors.ORANGE),
            
            # Table specific
            "table.header": Style(color=SolarizedColors.CYAN, bold=True),
            "table.border": Style(color=SolarizedColors.BASE01),
            "table.row.odd": Style(bgcolor=SolarizedColors.BASE02),
            "table.row.even": Style(bgcolor=SolarizedColors.BASE03),
            
            # Special elements
            "highlight": Style(color=SolarizedColors.ORANGE, bold=True),
            "accent": Style(color=SolarizedColors.VIOLET),
            "muted": Style(color=SolarizedColors.BASE01),
            
            # Specific to executor display
            "executor.id": Style(color=SolarizedColors.CYAN),
            "executor.name": Style(color=SolarizedColors.GREEN),
            "executor.gpu": Style(color=SolarizedColors.YELLOW),
            "executor.price": Style(color=SolarizedColors.MAGENTA),
            "executor.location": Style(color=SolarizedColors.BLUE),
            "executor.available": Style(color=SolarizedColors.BASE01),
            "executor.active": Style(color=SolarizedColors.GREEN),
            "executor.inactive": Style(color=SolarizedColors.RED),
            
            # Panels and boxes
            "panel.border": Style(color=SolarizedColors.BASE01),
            "panel.title": Style(color=SolarizedColors.CYAN),
            
            # Progress and spinners
            "progress.description": Style(color=SolarizedColors.BLUE),
            "progress.percentage": Style(color=SolarizedColors.MAGENTA),
            "progress.bar": Style(color=SolarizedColors.CYAN),
            "spinner": Style(color=SolarizedColors.CYAN),
        })
    
    def _create_solarized_light_theme(self) -> Theme:
        """Create Solarized Light theme."""
        return Theme({
            # Text styles (inverted for light theme)
            "default": Style(color=SolarizedColors.BASE00),
            "primary": Style(color=SolarizedColors.BASE00),
            "secondary": Style(color=SolarizedColors.BASE1),
            "dim": Style(color=SolarizedColors.BASE1, dim=True),
            "bright": Style(color=SolarizedColors.BASE01),
            
            # Headers and titles
            "title": Style(color=SolarizedColors.CYAN, bold=True),
            "subtitle": Style(color=SolarizedColors.BLUE),
            "header": Style(color=SolarizedColors.VIOLET, bold=True),
            
            # Status and feedback (same accent colors)
            "success": Style(color=SolarizedColors.GREEN, bold=True),
            "warning": Style(color=SolarizedColors.YELLOW, bold=True),
            "error": Style(color=SolarizedColors.RED, bold=True),
            "info": Style(color=SolarizedColors.BLUE),
            
            # Data display
            "key": Style(color=SolarizedColors.CYAN),
            "value": Style(color=SolarizedColors.BASE00),
            "number": Style(color=SolarizedColors.MAGENTA),
            "string": Style(color=SolarizedColors.GREEN),
            "boolean": Style(color=SolarizedColors.ORANGE),
            
            # Table specific
            "table.header": Style(color=SolarizedColors.CYAN, bold=True),
            "table.border": Style(color=SolarizedColors.BASE1),
            "table.row.odd": Style(bgcolor=SolarizedColors.BASE2),
            "table.row.even": Style(bgcolor=SolarizedColors.BASE3),
            
            # Special elements
            "highlight": Style(color=SolarizedColors.ORANGE, bold=True),
            "accent": Style(color=SolarizedColors.VIOLET),
            "muted": Style(color=SolarizedColors.BASE1),
            
            # Specific to executor display
            "executor.id": Style(color=SolarizedColors.CYAN),
            "executor.name": Style(color=SolarizedColors.GREEN),
            "executor.gpu": Style(color=SolarizedColors.YELLOW),
            "executor.price": Style(color=SolarizedColors.MAGENTA),
            "executor.location": Style(color=SolarizedColors.BLUE),
            "executor.available": Style(color=SolarizedColors.BASE1),
            "executor.active": Style(color=SolarizedColors.GREEN),
            "executor.inactive": Style(color=SolarizedColors.RED),
            
            # Panels and boxes
            "panel.border": Style(color=SolarizedColors.BASE1),
            "panel.title": Style(color=SolarizedColors.CYAN),
            
            # Progress and spinners
            "progress.description": Style(color=SolarizedColors.BLUE),
            "progress.percentage": Style(color=SolarizedColors.MAGENTA),
            "progress.bar": Style(color=SolarizedColors.CYAN),
            "spinner": Style(color=SolarizedColors.CYAN),
        })
    
    @property
    def theme(self) -> Theme:
        """Get the current theme."""
        return self._current_theme
    
    def switch_theme(self, scheme: ColorScheme) -> None:
        """Switch to a different color scheme."""
        self.scheme = scheme
        self._current_theme = self._create_theme(scheme)
    
    def get_style(self, name: str) -> str:
        """Get a style name for use in Rich markup.
        
        Args:
            name: The style name
            
        Returns:
            The style name wrapped in brackets for Rich markup
        """
        return f"[{name}]"
    
    def styled(self, text: str, style: str) -> str:
        """Apply a style to text.
        
        Args:
            text: The text to style
            style: The style name
            
        Returns:
            Styled text with Rich markup
        """
        return f"[{style}]{text}[/{style}]"


# Global style manager instance - now defaults to monochrome dark
style_manager = StyleManager(ColorScheme.MONOCHROME_DARK)


def get_theme() -> Theme:
    """Get the current theme."""
    return style_manager.theme


def switch_theme(scheme: ColorScheme) -> None:
    """Switch to a different color scheme."""
    style_manager.switch_theme(scheme)


def styled(text: str, style: str) -> str:
    """Apply a style to text."""
    return style_manager.styled(text, style) 