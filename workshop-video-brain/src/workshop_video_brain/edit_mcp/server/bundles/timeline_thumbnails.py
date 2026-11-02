"""``timeline_thumbnails`` MCP tool -- frames of the composited timeline.

Auto-imported by ``server/bundles/__init__.py``. Read-only, so no snapshot; the
PNGs go to ``reports/timeline_frames/<project-stem>/``.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import ProjectParseError
from workshop_video_brain.edit_mcp.adapters.mlt.engine import MltUnavailable, MltWorkerError
from workshop_video_brain.edit_mcp.pipelines.timeline_thumbnails import grab_thumbnails
from workshop_video_brain.edit_mcp.server.errors import (
    corrupt_project,
    invalid_input,
    missing_binary,
    missing_file,
    nonfinite_guard,
    nonneg_index,
    operation_failed,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _validate_workspace_path
from workshop_video_brain.server import mcp


@mcp.tool()
@tool_guard
def timeline_thumbnails(
    workspace_path: str,
    times: str = "",
    frames: str = "",
    width: int = 640,
    project_file: str = "",
) -> dict:
    """Write PNGs of chosen moments of the timeline, with all tracks composited.

    Args:
        workspace_path: Path to workspace root.
        times: Comma-separated timeline seconds, such as "1.5,10". Pass this or frames.
        frames: Comma-separated timeline frames, such as "0,250". Pass this or times.
        width: Image width in pixels, 16..3840; the height keeps the project's aspect.
        project_file: Project to read; defaults to the latest working copy.
    """
    try:
        workspace = _validate_workspace_path(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory.")
    if bool(times.strip()) == bool(frames.strip()):
        return invalid_input("Pass exactly one of times or frames.", suggestion='For example frames="0,250" or times="1.5,10".')
    if not 16 <= width <= 3840:
        return invalid_input(f"width must be 16..3840, got {width}.", suggestion="Try the default, 640.")

    time_list = None
    frame_list = None
    try:
        if times.strip():
            time_list = [float(part) for part in times.split(",")]
        else:
            frame_list = [int(part) for part in frames.split(",")]
    except ValueError as exc:
        return invalid_input(f"Could not read that list: {exc}", suggestion='Use numbers separated by commas, such as "0,250".')
    for index, value in enumerate(time_list or []):
        bad_number = nonfinite_guard(**{f"times[{index}]": value})
        if bad_number:
            return bad_number
        if value < 0:
            return invalid_input(f"times[{index}] is negative.", suggestion="Timeline seconds start at 0.")
    for index, value in enumerate(frame_list or []):
        bad_index = nonneg_index("frame", **{f"frames[{index}]": value})
        if bad_index:
            return bad_index

    try:
        return _ok(grab_thumbnails(workspace, times=time_list, frames=frame_list, width=width, project_file=project_file))
    except ProjectParseError as exc:
        return corrupt_project(project_file or str(workspace), exc)
    except FileNotFoundError as exc:
        return missing_file(project_file or str(workspace), str(exc))
    except MltUnavailable as exc:
        return missing_binary("melt", str(exc))
    except MltWorkerError as exc:
        return operation_failed(str(exc), cause=exc)
