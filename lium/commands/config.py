"""Configuration management commands for Lium CLI."""

import click
from typing import Optional

from ..config import get_or_set_api_key, get_config_value, set_config_value, unset_config_value, load_config_parser, get_config_path
from ..api import LiumAPIClient
from ..styles import styled
from ..helpers import *


def _config_show():
    config = load_config_parser() # This loads the INI and triggers migration
    
    if not config.sections() and not config.defaults():
        console.print(styled(f"Configuration file '{get_config_path()}' is empty or does not exist.", "info"))
        return

    # Use a Text object for more control over layout and styling
    output_text = Text()
    first_section = True

    for section_name in config.sections():
        if not first_section:
            output_text.append("\n") # Add a blank line between sections
        output_text.append(f"[{section_name}]\n", style="title") # Style for section header
        
        items = config.items(section_name)
        if not items:
            output_text.append(styled("  (empty section)\n", "dim"))
        else:
            for key, value in items:
                output_text.append(f"  {key} = ", style="key") # Style for key
                output_text.append(f"{value}\n", style="value") # Style for value
        first_section = False
    
    # If only DEFAULT items exist and we chose not to print [DEFAULT] explicitly
    if first_section and config.defaults(): 
        for key, value in config.defaults().items():
            output_text.append(f"{key} = ", style="key") # Print at top level without section
            output_text.append(f"{value}\n", style="value")

    if output_text.plain:
        console.print(output_text)
    else:
         console.print(styled(f"Configuration file '{get_config_path()}' appears to be empty (after parsing).", "info"))


@click.group(help="Manage Lium CLI configuration.")
def config_command():
    pass


@config_command.command(name="get", help="Get a configuration value.")
@click.argument("key")
def config_get(key: str):
    value = get_config_value(key)
    if value is not None:
        console.print(styled(value, "primary"))
    else:
        console.print(styled(f"Key '{key}' not found.", "error"))


@config_command.command(name="set", help="Set a configuration value. Run `lium config set template.default_id` for interactive template selection.")
@click.argument("key")
@click.argument("value", required=False)
def config_set(key: str, value: Optional[str]):
    if key == "template.default_id" and value is None:
        console.print(styled("Interactive template selection for default:" , "info"))
        # Need LiumAPIClient for select_template_interactively
        api_key_for_template_selection = get_or_set_api_key()
        if not api_key_for_template_selection:
            console.print(styled("API key required to fetch templates. Please configure api.api_key first.", "error"))
            return
        client = LiumAPIClient(api_key_for_template_selection)
        # Import select_template_interactively from up command
        from .up import select_template_interactively
        selected_template_id = select_template_interactively(client, skip_prompts=False)
        if selected_template_id:
            set_config_value(key, selected_template_id)
            # Fetch name for confirmation message
            try:
                templates = client.get_templates()
                tpl_name = next((tpl.get("name") for tpl in templates if tpl.get("id") == selected_template_id), selected_template_id)
            except:
                tpl_name = selected_template_id
            console.print(styled(f"Set '{key}' to: '{tpl_name}' (ID: {selected_template_id})", "success"))
        else:
            console.print(styled("No template selected. Configuration not changed.", "info"))
    elif value is not None: # Standard key-value set
        set_config_value(key, value)
        console.print(styled(f"Set '{key}' to: ", "success") + styled(value, "primary"))
    else:
        console.print(styled(f"Error: Value required for setting key '{key}'.", "error"))
        console.print(styled("To set a default template interactively, run: lium config set template.default_id", "info"))


@config_command.command(name="unset", help="Remove a configuration value.")
@click.argument("key")
def config_unset(key: str):
    if unset_config_value(key):
        console.print(styled(f"Key '{key}' unset successfully.", "success"))
    else:
        console.print(styled(f"Key '{key}' not found.", "error"))


@config_command.command(name="show", help="Show the entire configuration.")
def config_show():
    _config_show()
    

@config_command.command(name="path", help="Show the path to the configuration file.")
def config_path():
    console.print(styled(str(get_config_path()), "primary")) 