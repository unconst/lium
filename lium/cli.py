"""Main CLI entry point for Lium."""

import click
from .commands.ls import ls_command
from .commands.ps import ps_command
from .commands.up import up_command
from .commands.rm import rm_command
from .commands.image import image_command
from .commands.fund import fund_command
from .commands.init import init_command
from .commands.config import config_command
from .commands.theme import theme_command
from .commands.exec import exec_command
from .commands.ssh import ssh_command
from .commands.scp import scp_command
from .commands.rsync import rsync_command

@click.group()
def cli():
    """Lium CLI - Manage compute executors."""
    pass

# Register commands
cli.add_command(ls_command)
cli.add_command(ps_command)
cli.add_command(up_command)
cli.add_command(rm_command)
cli.add_command(image_command)
cli.add_command(fund_command)
cli.add_command(init_command)
cli.add_command(config_command)
cli.add_command(theme_command)
cli.add_command(exec_command)
cli.add_command(ssh_command)
cli.add_command(scp_command)
cli.add_command(rsync_command)


def main():
    """Main entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main() 