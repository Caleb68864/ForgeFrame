"""``media_remove_silence`` and ``media_silence_keep_ranges`` MCP tools.

Auto-imported by ``server/bundles/__init__.py``. Bare-file tools: they lead with
``source``, take no workspace and touch no project, so there is no snapshot.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.autoeditor.cli import AutoEditorError
from workshop_video_brain.edit_mcp.pipelines import silence_cut
from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import (
    error_from_pipeline_result,
)
from workshop_video_brain.edit_mcp.server.errors import (
    invalid_input,
    media_unreadable,
    missing_dependency,
    missing_file,
    nonfinite_guard,
    operation_failed,
    tool_guard,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import _ok
from workshop_video_brain.server import mcp


def _validate(source: str, engine: str, threshold_db: float, min_silence: float, margin: float) -> dict | None:
    if not source or not Path(source).is_file():
        return missing_file(source, "source")
    try:
        silence_cut.resolve_engine(engine)
    except silence_cut.EngineUnavailable:
        return missing_dependency("auto-editor", silence_cut.ENGINES["auto-editor"]["pip"])
    except ValueError as exc:
        return invalid_input(str(exc), suggestion="Pass engine as auto, ffmpeg or auto-editor.")
    bad_number = nonfinite_guard(threshold_db=threshold_db, min_silence=min_silence, margin=margin)
    if bad_number:
        return bad_number
    if threshold_db >= 0:
        return invalid_input("threshold_db must be negative.", suggestion="Pass a level below 0 dBFS, such as -30.")
    if min_silence <= 0:
        return invalid_input("min_silence must be > 0.", suggestion="Pass a positive number of seconds, such as 0.5.")
    if margin < 0:
        return invalid_input("margin must be >= 0.", suggestion="Pass 0 or more seconds, such as 0.2.")
    return None


@mcp.tool()
@tool_guard
def media_remove_silence(
    source: str,
    output_path: str,
    engine: str = "auto",
    threshold_db: float = -30.0,
    min_silence: float = 0.5,
    margin: float = 0.2,
) -> dict:
    """Write a tightened copy of an audio or video file with its silence cut out.

    Args:
        source: Path to the media file.
        output_path: File to write. Required, and refused inside media/raw or
            projects/source.
        engine: "auto" (default) prefers auto-editor when its extra and binary are
            present, and otherwise uses ffmpeg; or "ffmpeg", "auto-editor".
        threshold_db: Anything quieter counts as silence, in dBFS.
        min_silence: Shortest gap to cut, in seconds. Ignored by auto-editor.
        margin: Seconds of padding kept around each kept range.
    """
    if not output_path or not output_path.strip():
        return invalid_input("output_path is required.", suggestion="Give a path outside media/raw.")
    problem = _validate(source, engine, threshold_db, min_silence, margin)
    if problem:
        return problem
    try:
        result = silence_cut.remove_silence_file(
            Path(source), Path(output_path), engine=engine,
            threshold_db=threshold_db, min_silence=min_silence, margin=margin,
        )
    except AutoEditorError as exc:
        return operation_failed(str(exc), cause=exc)
    if not result.get("success"):
        return error_from_pipeline_result(result, "Silence removal failed", path=source)
    return _ok(result)


@mcp.tool()
@tool_guard
def media_silence_keep_ranges(
    source: str,
    engine: str = "auto",
    threshold_db: float = -30.0,
    min_silence: float = 0.5,
    margin: float = 0.2,
) -> dict:
    """Report which source seconds silence removal would keep, without rendering.

    Args:
        source: Path to the media file.
        engine: "auto" (default) prefers auto-editor when its extra and binary are
            present, and otherwise uses ffmpeg; or "ffmpeg", "auto-editor".
        threshold_db: Anything quieter counts as silence, in dBFS.
        min_silence: Shortest gap to cut, in seconds. Ignored by auto-editor.
        margin: Seconds of padding kept around each kept range.
    """
    problem = _validate(source, engine, threshold_db, min_silence, margin)
    if problem:
        return problem
    try:
        engine_used, ranges, duration = silence_cut.keep_ranges(
            Path(source), engine=engine,
            threshold_db=threshold_db, min_silence=min_silence, margin=margin,
        )
    except silence_cut.SourceUnreadable as exc:
        return media_unreadable(source, str(exc))
    except AutoEditorError as exc:
        return operation_failed(str(exc), cause=exc)
    return _ok({"engine": engine_used, "keep_ranges": [list(item) for item in ranges], "source_duration": duration})
