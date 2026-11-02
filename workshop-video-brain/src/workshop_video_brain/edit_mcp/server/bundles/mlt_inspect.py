"""``project_mlt_inspect`` MCP tool -- what MLT actually built from a project.

Auto-imported by ``server/bundles/__init__.py``. Read-only, for debugging the
parser against the real engine.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.adapters.mlt import engine
from workshop_video_brain.edit_mcp.pipelines.timeline_thumbnails import resolve_project
from workshop_video_brain.edit_mcp.server.errors import (
    invalid_input,
    missing_dependency,
    missing_file,
    operation_failed,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _validate_workspace_path
from workshop_video_brain.server import mcp

_HINT = "install your distro's python3-mlt / mlt python bindings, or set WVB_MLT_PYTHON"


@mcp.tool()
@tool_guard
def project_mlt_inspect(workspace_path: str, project_file: str = "") -> dict:
    """Return the profile, tracks, playlists and clips MLT builds from a project.

    Args:
        workspace_path: Path to workspace root.
        project_file: Project to inspect; defaults to the latest working copy.
    """
    try:
        workspace = _validate_workspace_path(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory.")
    try:
        path = resolve_project(workspace, project_file)
    except FileNotFoundError as exc:
        return missing_file(project_file or str(workspace), str(exc))
    try:
        inspection = engine.run_worker("inspect", {"path": str(path)}, timeout=engine._LOAD_TIMEOUT_SECONDS)
    except engine.MltUnavailable:
        return missing_dependency("mlt", _HINT)
    except engine.MltWorkerError as exc:
        return operation_failed(str(exc), cause=exc)
    return _ok({"project_file": str(path), **inspection})
