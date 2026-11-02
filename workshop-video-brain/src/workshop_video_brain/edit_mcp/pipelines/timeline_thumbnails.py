"""Grab frames of a project's composited timeline (``timeline_thumbnails``).

A project with missing media raises rather than producing a black thumbnail: a
caller cannot tell a deliberately dark frame from a failed one.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.kdenlive.parser import parse_project
from workshop_video_brain.edit_mcp.adapters.mlt.engine import timeline_frames
from workshop_video_brain.edit_mcp.adapters.render.media_check import missing_media, missing_media_message
from workshop_video_brain.edit_mcp.pipelines._common import seconds_to_frames


def resolve_project(workspace_root: Path, project_file: str = "") -> Path:
    """Return the explicit project, else the latest working copy."""
    from workshop_video_brain.edit_mcp.server.tools_helpers import latest_project

    if project_file:
        path = Path(project_file)
        path = path if path.is_absolute() else Path(workspace_root) / path
        if not path.is_file():
            raise FileNotFoundError(f"Project file not found: {path}")
        return path
    working = Path(workspace_root) / "projects" / "working_copies"
    latest = latest_project(working.glob("*.kdenlive")) if working.is_dir() else None
    if latest is None:
        raise FileNotFoundError("No .kdenlive files found in projects/working_copies/")
    return latest


def grab_thumbnails(
    workspace_root: Path,
    *,
    times: list[float] | None = None,
    frames: list[int] | None = None,
    width: int = 640,
    project_file: str = "",
) -> dict:
    """Grab frames into ``reports/timeline_frames/<project-stem>/``."""
    project_path = resolve_project(workspace_root, project_file)
    project = parse_project(project_path)
    absent = missing_media(project_path)
    if absent:
        raise FileNotFoundError(missing_media_message(project_path, absent))
    targets = list(frames or [])
    if times is not None:
        targets = [seconds_to_frames(time, project.profile.fps or 25.0) for time in times]
    output_dir = Path(workspace_root) / "reports" / "timeline_frames" / project_path.stem
    result = timeline_frames(
        project_path, targets, width, output_dir,
        profile_size=(project.profile.width, project.profile.height),
    )
    return {"engine": result["engine"], "project_file": str(project_path),
            "frames": result["frames"], "output_dir": str(output_dir)}
