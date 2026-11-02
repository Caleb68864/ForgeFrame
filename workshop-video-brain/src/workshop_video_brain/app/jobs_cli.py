"""CLI access to persistent jobs without loading the MCP server."""
import json

import click

from workshop_video_brain.workspace import jobs


def _emit(action, *args):
    try:
        click.echo(json.dumps(action(*args), indent=2, default=str))
    except (ValueError, OSError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc


@click.group("jobs")
def jobs_group():
    """Start, inspect, cancel, and retry persistent operations."""


@jobs_group.command("submit")
@click.argument("workspace", type=click.Path(exists=True, file_okay=False))
@click.argument("operation", type=click.Choice(list(jobs.OPERATIONS)))
@click.option("--parameters", default="{}", help="Operation parameters as a JSON object.")
def submit(workspace, operation, parameters):
    try:
        params = json.loads(parameters)
    except ValueError as exc:
        raise click.BadParameter("Expected a JSON object", param_hint="--parameters") from exc
    if not isinstance(params, dict):
        raise click.BadParameter("Expected a JSON object", param_hint="--parameters")
    _emit(jobs.submit_job, workspace, operation, params)


@jobs_group.command("list")
@click.argument("workspace", type=click.Path(exists=True, file_okay=False))
def list_command(workspace):
    _emit(jobs.list_jobs, workspace)


@jobs_group.command("status")
@click.argument("workspace", type=click.Path(exists=True, file_okay=False))
@click.argument("job_id")
def status(workspace, job_id):
    _emit(jobs.get_job, workspace, job_id)


@jobs_group.command("cancel")
@click.argument("workspace", type=click.Path(exists=True, file_okay=False))
@click.argument("job_id")
def cancel(workspace, job_id):
    _emit(jobs.cancel_job, workspace, job_id)


@jobs_group.command("retry")
@click.argument("workspace", type=click.Path(exists=True, file_okay=False))
@click.argument("job_id")
def retry(workspace, job_id):
    _emit(jobs.retry_job, workspace, job_id)


def register_commands(main):
    main.add_command(jobs_group)
