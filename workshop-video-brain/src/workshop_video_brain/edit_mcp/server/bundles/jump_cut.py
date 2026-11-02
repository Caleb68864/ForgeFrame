"""``timeline_build_jump_cut`` MCP tool -- keep-ranges to a ``.kdenlive`` timeline.

Auto-imported by ``server/bundles/__init__.py``. It always creates a new versioned
working copy and never overwrites one, so no pre-write snapshot is needed.
"""
from __future__ import annotations

import json
import math

from workshop_video_brain.edit_mcp.adapters.autoeditor.cli import AutoEditorError
from workshop_video_brain.edit_mcp.pipelines import silence_cut
from workshop_video_brain.edit_mcp.pipelines.analysis_common import resolve_under_workspace
from workshop_video_brain.edit_mcp.pipelines.jump_cut import build_jump_cut
from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import error_from_pipeline_result
from workshop_video_brain.edit_mcp.server.errors import (
    bad_json_param,
    invalid_input,
    media_unreadable,
    missing_dependency,
    missing_file,
    nonfinite_guard,
    operation_failed,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok, _validate_workspace_path
from workshop_video_brain.server import mcp

_RANGES_EXAMPLE = "[[0.0, 1.7], [3.3, 5.0]]"


def _parse_ranges(given: str) -> list[tuple[float, float]] | dict:
    """Return validated ranges, or the error dict to send back."""
    try:
        parsed = json.loads(given)
        ranges = [(float(start), float(end)) for start, end in parsed]
    except (ValueError, TypeError):
        return bad_json_param("keep_ranges_json", _RANGES_EXAMPLE, given)
    previous_end = 0.0
    for start, end in ranges:
        if not (math.isfinite(start) and math.isfinite(end)):
            return invalid_input("keep_ranges_json holds a non-finite number.", suggestion=f"Use finite seconds, as in {_RANGES_EXAMPLE}.")
        if start < 0 or start >= end:
            return invalid_input(f"Bad range [{start}, {end}]: it needs 0 <= start < end.", suggestion=f"Use ranges like {_RANGES_EXAMPLE}.")
        if start < previous_end:
            return invalid_input("keep_ranges_json must be sorted and must not overlap.", suggestion=f"Use ranges like {_RANGES_EXAMPLE}.")
        previous_end = end
    if not ranges:
        return invalid_input("keep_ranges_json is empty.", suggestion=f"Use ranges like {_RANGES_EXAMPLE}.")
    return ranges


@mcp.tool()
@tool_guard
def timeline_build_jump_cut(
    workspace_path: str,
    source: str,
    engine: str = "auto",
    threshold_db: float = -30.0,
    min_silence: float = 0.5,
    margin: float = 0.2,
    keep_ranges_json: str = "",
    add_cut_guides: bool = False,
) -> dict:
    """Build a new Kdenlive timeline with the silence of a recording cut out.

    The kept parts sit back to back on a video track, with matching audio on an
    audio track, in a project that takes its size and frame rate from the source.

    Args:
        workspace_path: Path to workspace root.
        source: Path to the video file (absolute or workspace-relative).
        engine: "auto" (default) prefers auto-editor when its extra and binary are
            present, and otherwise uses ffmpeg; or "ffmpeg", "auto-editor".
        threshold_db: Anything quieter counts as silence, in dBFS.
        min_silence: Shortest gap to cut, in seconds. Ignored by auto-editor.
        margin: Seconds of padding kept around each kept range.
        keep_ranges_json: Source seconds to keep, as "[[0.0, 1.7], [3.3, 5.0]]".
            Skips silence detection.
        add_cut_guides: Add a guide at each cut on the timeline.
    """
    try:
        workspace = _validate_workspace_path(workspace_path)
    except (ValueError, FileNotFoundError) as exc:
        return invalid_input(str(exc), suggestion="Check workspace_path exists and is a directory.")
    if not source or not source.strip():
        return invalid_input("source is required.", suggestion="Pass the path to a video file.")
    path = resolve_under_workspace(workspace, source)
    if not path.is_file():
        return missing_file(str(path), "source")

    ranges = None
    if keep_ranges_json:
        ranges = _parse_ranges(keep_ranges_json)
        if isinstance(ranges, dict):
            return ranges
    else:
        try:
            silence_cut.resolve_engine(engine)
        except silence_cut.EngineUnavailable:
            return missing_dependency("auto-editor", silence_cut.ENGINES["auto-editor"]["pip"])
        except ValueError as exc:
            return invalid_input(str(exc), suggestion="Pass engine as auto, ffmpeg or auto-editor.")
        bad_number = nonfinite_guard(threshold_db=threshold_db, min_silence=min_silence, margin=margin)
        if bad_number:
            return bad_number
        if threshold_db >= 0 or min_silence <= 0 or margin < 0:
            return invalid_input(
                "Need threshold_db < 0, min_silence > 0 and margin >= 0.",
                suggestion="Try the defaults: threshold_db=-30, min_silence=0.5, margin=0.2.",
            )

    try:
        result = build_jump_cut(
            workspace, path,
            engine=engine,
            threshold_db=threshold_db,
            min_silence=min_silence,
            margin=margin,
            ranges=ranges,
            add_cut_guides=add_cut_guides,
        )
    except silence_cut.SourceUnreadable as exc:
        return media_unreadable(str(path), str(exc))
    except AutoEditorError as exc:
        return operation_failed(str(exc), cause=exc)
    if not result.get("success"):
        return error_from_pipeline_result(result, "Could not build the jump cut", path=str(path))
    return _ok(result)
