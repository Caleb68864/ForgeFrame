"""CLI entry point for workshop-video-brain."""
from __future__ import annotations

import click

from workshop_video_brain import __version__


@click.group()
def main() -> None:
    """Workshop Video Brain -- local-first video production assistant."""


@main.command()
def version() -> None:
    """Print the current version."""
    click.echo(f"workshop-video-brain {__version__}")


if __name__ == "__main__":
    main()
