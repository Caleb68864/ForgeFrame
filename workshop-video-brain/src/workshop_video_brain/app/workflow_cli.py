"""CLI registration for project readiness and resumable first cuts."""
from __future__ import annotations
import json
import click


def register_commands(main: click.Group) -> None:
    @main.command("project-status")
    @click.argument("workspace_path", type=click.Path(exists=True, file_okay=False))
    def project_status(workspace_path: str) -> None:
        """Show readiness, missing inputs, selected version, and next action."""
        from workshop_video_brain.edit_mcp.pipelines.guided_workflow import project_status as status
        try:
            click.echo(json.dumps(status(workspace_path), indent=2, default=str))
        except Exception as exc:
            raise click.ClickException(str(exc)) from exc

    @main.command("workflow")
    @click.argument("workspace_path", type=click.Path(exists=True, file_okay=False))
    @click.option("--through", type=click.Choice(["footage", "selects", "assembly", "preview", "review"]), default="review")
    @click.option("--project-file", default="", help="Pin an existing working copy instead of generating an assembly.")
    def workflow(workspace_path: str, through: str, project_file: str) -> None:
        """Start or resume a persistent first-cut job."""
        from workshop_video_brain.workspace.jobs import submit_job
        try:
            click.echo(json.dumps(submit_job(workspace_path, "workflow", {"through": through, "project_file": project_file}), indent=2, default=str))
        except Exception as exc:
            raise click.ClickException(str(exc)) from exc
