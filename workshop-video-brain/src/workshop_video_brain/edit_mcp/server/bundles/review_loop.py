"""Agent review-loop + publish-thumbnail MCP tools (gap items 5a / 5b).

Auto-imported by ``server/bundles/__init__.py``; registers two tools that let an
agent watch its own cut and produce a publish thumbnail:

- :func:`render_review_frames` -- render the project to a throwaway low-res
  preview, extract frames every N seconds and/or at marker timestamps, tile a
  contact sheet, and optionally run QC. The returned frame paths get Read as
  images by the caller.
- :func:`thumbnail_generate` -- extract one frame (media file or melt-rendered
  project frame) and overlay bold title text into ``reports/thumbnails/``.

Analysis-only: writes into ``reports/`` and never mutates project files or
``media/raw``, so no snapshot is taken.
"""
from __future__ import annotations

from workshop_video_brain.edit_mcp.pipelines import review_loop
from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import (
    error_from_pipeline_result,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    operation_failed,
)


@mcp.tool()
@tool_guard
def render_review_frames(
    workspace_path: str,
    project_file: str,
    every_seconds: float = 10.0,
    at_markers: bool = False,
    width: int = 640,
    run_qc: bool = True,
    keep_render: bool = False,
) -> dict:
    """Render a cut, extract review frames, tile a contact sheet, and QC it.

    Melt-renders *project_file* to a throwaway ``preview``-profile file under
    ``reports/review/<timestamp>/``, extracts a frame every ``every_seconds``
    (and, when ``at_markers``, at each ``markers/*.json`` timestamp), tiles them
    into ``sheet.png`` and optionally runs the post-render QC pass. The returned
    ``frame_paths`` can be Read as images so an agent can look at its own edit.

    Args:
        workspace_path: Path to workspace root.
        project_file: ``.kdenlive`` project (absolute or workspace-relative).
        every_seconds: Interval between extracted frames (default 10s). Set 0 to
            rely solely on markers.
        at_markers: Also extract a frame at each marker start time.
        width: Scaled width in px for each frame (height auto; default 640).
        run_qc: Run black-frame / silence / loudness / clipping QC on the render.
        keep_render: Keep the preview render file (default deletes it).
    """
    try:
        ws = _validate_workspace_path(workspace_path)
        if not project_file or not project_file.strip():
            return err("project_file is required.", suggestion="Pass project_file as the path to a .kdenlive project; it resolves under the workspace root unless absolute.")
        result = review_loop.render_review_frames(
            ws,
            project_file,
            every_seconds=every_seconds,
            at_markers=at_markers,
            width=width,
            run_qc=run_qc,
            keep_render=keep_render,
        )
        if not result.get("success"):
            return error_from_pipeline_result(result, "review render failed")
        result.pop("success", None)
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)


@mcp.tool()
@tool_guard
def thumbnail_generate(
    workspace_path: str,
    source_or_project: str,
    at_seconds: float,
    text: str = "",
    subtitle: str = "",
    style: str = "thumbnail",
    output_name: str = "",
    width: int = 1280,
) -> dict:
    """Make a publish thumbnail: extract a frame and overlay bold title text.

    *source_or_project* may be a media file (frame pulled via ffmpeg) or a
    ``.kdenlive`` project (single frame melt-rendered through the composite
    path). Title/subtitle are drawn with PIL using the
    ``templates/titles/<style>.yaml`` vocabulary (font / scale / colours /
    outline). Output PNG lands in ``reports/thumbnails/``.

    Args:
        workspace_path: Path to workspace root.
        source_or_project: Media file or ``.kdenlive`` (absolute or relative).
        at_seconds: Timestamp of the frame to grab.
        text: Bold title text to overlay (empty = frame only, no text).
        subtitle: Optional accent line under the title.
        style: Template name in ``templates/titles/`` (default ``thumbnail``).
        output_name: Output PNG filename (``.png`` appended if missing).
        width: Output width in px (default 1280).
    """
    try:
        ws = _validate_workspace_path(workspace_path)
        if not source_or_project or not source_or_project.strip():
            return err("source_or_project is required.", suggestion="Pass a media file or a .kdenlive project path; it resolves under the workspace root unless absolute.")
        result = review_loop.thumbnail_generate(
            ws,
            source_or_project,
            at_seconds,
            text=text,
            subtitle=subtitle,
            style=style,
            output_name=output_name,
            width=width,
        )
        if not result.get("success"):
            return error_from_pipeline_result(result, "thumbnail generation failed")
        result.pop("success", None)
        return _ok(result)
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)
