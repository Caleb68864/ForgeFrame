"""Project readiness and persistent guided first-cut jobs."""
from __future__ import annotations
from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import tool_guard, from_exception
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok


@mcp.tool()
@tool_guard
def project_status(workspace_path: str) -> dict:
    """Report readiness, missing inputs, selected version, jobs, and next action."""
    try:
        from workshop_video_brain.edit_mcp.pipelines.guided_workflow import project_status as status
        return _ok(status(workspace_path))
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def workflow_start(workspace_path: str, through: str = "review", project_file: str = "") -> dict:
    """Start/resume footage → selects → assembly → preview → review as a job.

    Review prepares a checklist awaiting human editorial acceptance.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines.guided_workflow import STAGES, _root
        from workshop_video_brain.workspace.jobs import submit_job
        root = _root(workspace_path)
        if through not in STAGES:
            raise ValueError(f"through must be one of {STAGES}")
        return _ok(submit_job(root, "workflow", {"through": through, "project_file": project_file}))
    except Exception as exc:
        return from_exception(exc)
