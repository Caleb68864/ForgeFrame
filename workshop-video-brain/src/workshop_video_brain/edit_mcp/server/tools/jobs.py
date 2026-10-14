"""Detached jobs for expensive workspace operations."""
from __future__ import annotations

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import tool_guard
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok
from workshop_video_brain.workspace import jobs


@mcp.tool()
@tool_guard
def job_submit(workspace_path: str, operation: str, parameters: dict | None = None) -> dict:
    """Start render, proxy, transcribe, or workflow and return a persistent job ID.

    Only one detached operation may write a workspace at once. Render accepts
    profile/project_file/mode; workflow accepts through/project_file. Runs on
    Linux/macOS, independently of the MCP connection. Poll job_status for results.
    """
    return _ok(jobs.submit_job(workspace_path, operation, parameters))


@mcp.tool()
@tool_guard
def job_status(workspace_path: str, job_id: str) -> dict:
    """Read persistent status, stage progress, log path, and result; detect lost workers."""
    return _ok(jobs.get_job(workspace_path, job_id))


@mcp.tool()
@tool_guard
def job_list(workspace_path: str) -> dict:
    """List detached jobs, newest first, reconciling workers lost after restart."""
    return _ok({"jobs": jobs.list_jobs(workspace_path)})


@mcp.tool()
@tool_guard
def job_cancel(workspace_path: str, job_id: str) -> dict:
    """Request cancellation of the worker and its FFmpeg/MLT child processes."""
    return _ok(jobs.cancel_job(workspace_path, job_id))


@mcp.tool()
@tool_guard
def job_retry(workspace_path: str, job_id: str) -> dict:
    """Explicitly retry failed/cancelled/interrupted work with a new job ID."""
    return _ok(jobs.retry_job(workspace_path, job_id))
