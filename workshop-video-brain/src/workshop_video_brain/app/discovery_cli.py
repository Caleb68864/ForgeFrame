"""Lightweight CLI diagnostics and capability discovery."""
import json

import click


def register_commands(main: click.Group) -> None:
    @main.command('doctor')
    @click.option('--json', 'as_json', is_flag=True, help='Emit the full diagnostic report.')
    def doctor(as_json: bool) -> None:
        """Check local binaries, engines, effects, encoders, and cached models."""
        from .doctor import environment_report
        report = environment_report()
        if as_json:
            click.echo(json.dumps(report, indent=2))
            return
        for name, result in report['binaries'].items():
            click.echo(f"{name}: {'ready' if result['available'] else 'unavailable'}")
        for name, ready in report['features'].items():
            click.echo(f"{name}: {'ready' if ready else 'unavailable'}")
        click.echo('Use --json for encoder/effect listings and model cache details.')

    @main.command('capabilities')
    @click.option('--markdown', is_flag=True, help='Generate the capability documentation.')
    def capabilities(markdown: bool) -> None:
        """List tools and skills from registration metadata."""
        from .capabilities import capability_catalog, catalog_markdown
        click.echo(catalog_markdown() if markdown else json.dumps(capability_catalog(), indent=2))
