"""``media_thumbnail_sheet`` MCP tool -- keyframe + contact-sheet extraction.

Auto-imported by ``server/bundles/__init__.py``; registers one analysis tool.
Analysis-only: writes PNGs into ``reports/thumbnails/<clip>/`` so a vision
agent can tag them -- it never touches ``media/raw`` or project files, so no
snapshot is needed.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.pipelines.analysis_common import (
    resolve_under_workspace,
)
from workshop_video_brain.edit_mcp.pipelines.thumbnail_sheet import (
    generate_thumbnail_sheet,
    sheet_output_dir,
)
from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import (
    error_from_pipeline_result,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _err,
    _ok,
    _validate_workspace_path,
)
from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    invalid_input,
    bad_json_param,
    corrupt_project,
    operation_failed,
    media_unreadable,
    MISSING_FILE,
    MISSING_BINARY,
    INVALID_INDEX,
    INVALID_INPUT,
    CORRUPT_PROJECT,
    MISSING_DEPENDENCY,
    BAD_JSON_PARAM,
)


@mcp.tool()
@tool_guard
def media_thumbnail_sheet(
    workspace_path: str,
    source: str = "",
    frames: int = 6,
    grid: bool = True,
    width: int = 320,
    write_index_stub: bool = False,
) -> dict:
    """Extract representative keyframes (+ optional contact sheet) from a clip.

    Uses FFmpeg's ``thumbnail`` filter to pick the most representative frames
    across the clip and, when ``grid`` is set, tiles them into a single contact
    sheet. Frames land in ``reports/thumbnails/<clip>/`` and the returned frame
    paths can be handed to a vision agent for auto-tagging.

    Args:
        workspace_path: Path to workspace root.
        source: Path to the video file (absolute, or relative to the workspace).
        frames: Number of representative frames to extract (default 6).
        grid: Also render a tiled contact sheet ``sheet.png`` (default True).
        width: Scaled width in px for each thumbnail (height auto; default 320).
        write_index_stub: If True, record the contact-sheet path against the
            clip in the b-roll index via ``tag_clip`` (requires a configured
            vault; skipped gracefully otherwise).
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        if not source or not source.strip():
            return _err("source is required (path to a video file).")
        src = resolve_under_workspace(ws_path, source)
        if not src.exists():
            return err(f"File not found: {src}", error_type=MISSING_FILE, suggestion="Check the source path; it is resolved relative to the workspace root unless absolute.", path=str(src))

        out_dir = sheet_output_dir(ws_path, src)
        try:
            result = generate_thumbnail_sheet(
                src, out_dir, frames=frames, grid=grid, width=width
            )
        except FileNotFoundError as exc:
            # ffmpeg binary itself missing (the source was checked above).
            return missing_binary(
                "ffmpeg",
                "Install FFmpeg and ensure it is on PATH (apt install ffmpeg / "
                "brew install ffmpeg / pacman -S ffmpeg).",
            )
        if not result["success"]:
            return error_from_pipeline_result(
                result, "Thumbnail extraction failed", path=str(src),
            )

        data = {
            "input": str(src),
            "output_dir": result["output_dir"],
            "frame_paths": result["frame_paths"],
            "sheet_path": result["sheet_path"],
            "frame_count": len(result["frame_paths"]),
            "grid_dims": result["grid_dims"],
            "width": result["width"],
        }

        if write_index_stub:
            data["index_stub"] = _record_index_stub(src, result["sheet_path"])

        return _ok(data)
    except Exception as exc:  # noqa: BLE001
        return operation_failed(str(exc), cause=exc)


def _record_index_stub(src: Path, sheet_path: str | None) -> dict:
    """Record the sheet path against the clip in the b-roll index.

    Imports the existing index write functions; never modifies their module.
    Returns a small status dict rather than raising, so a missing vault does not
    fail the whole tool.
    """
    try:
        from workshop_video_brain.edit_mcp.pipelines.broll_library import (
            _resolve_vault_path,
            tag_clip,
        )

        vault = _resolve_vault_path()
        if vault is None:
            return {"recorded": False, "reason": "no vault configured"}

        desc = f"Contact sheet: {sheet_path}" if sheet_path else "Thumbnail frames extracted"
        entry = tag_clip(
            vault,
            str(src),
            tags=["thumbnail-sheet"],
            description=desc,
        )
        return {"recorded": True, "clip_ref": entry.clip_ref}
    except Exception as exc:  # noqa: BLE001
        return {"recorded": False, "reason": str(exc)}
