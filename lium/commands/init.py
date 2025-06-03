"""Initialize Lium setup command for Lium CLI."""

import click

from ..config import get_or_set_api_key, get_or_set_ssh_key
from ..styles import styled
from ..helpers import *


@click.command(name="init")
def init_command():
    get_or_set_api_key()
    get_or_set_ssh_key()
    console.print(styled('\nShowing config in ~/.lium/config.ini', 'info'))
    # Import _config_show from config module when it gets created
    from ..commands.config import _config_show
    _config_show() 