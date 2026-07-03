"""``media_stabilize`` MCP tool -- file-level video stabilization.

Auto-imported by ``server/bundles/__init__.py``; registers one tool on the
shared FastMCP singleton. Follows the exact shape of the audio file-processing
tools (``audio_enhance`` / ``audio_denoise`` in ``server/tools.py``): resolve
a source under the workspace, never touch ``media/raw``, write the result into
``media/processed/``, and return an ``_ok`` / ``_err`` result dict.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegNotFound,
    FFmpegTimeout,
)
from workshop_video_brain.edit_mcp.pipelines.stabilize import (
    stabilize_file,
    stabilized_output_path,
)
from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import (
    cleanup_partial_output as _cleanup_partial,
    error_from_pipeline_result,
    has_video_stream as _has_video_stream,
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

_VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts"}


def _find_video_file(workspace_path: Path, source: str) -> Path | None:
    """Locate a video file: explicit path or latest in ``media/raw``.

    Mirrors ``server.tools._find_audio_file`` but for video extensions.
    """
    if source and source.strip():
        p = Path(source)
        if not p.is_absolute():
            p = workspace_path / source
        return p

    raw_dir = workspace_path / "media" / "raw"
    if not raw_dir.exists():
        return None
    candidates = sorted(
        (f for f in raw_dir.iterdir() if f.is_file() and f.suffix.lower() in _VIDEO_EXTS),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


@mcp.tool()
@tool_guard
def media_stabilize(
    workspace_path: str,
    source: str = "",
    shakiness: int = 5,
    smoothing: int = 15,
    accuracy: int = 15,
    zoom: int = 0,
    output_name: str = "",
) -> dict:
    """Stabilize shaky footage with two-pass FFmpeg vidstab.

    Runs ``vidstabdetect`` (analyse motion into a temporary ``.trf``) then
    ``vidstabtransform`` (apply the smoothed transform), writing a new file to
    ``media/processed/``. The source in ``media/raw`` is never modified. If the
    local FFmpeg build lacks ``libvidstab`` the tool falls back to the
    single-pass ``deshake`` filter and reports ``method="deshake"``.

    Args:
        workspace_path: Path to workspace root.
        source: Path to the video file. If empty, uses the latest file in
            ``media/raw/``.
        shakiness: Detection shakiness, 1..10 (default 5). Higher = footage is
            treated as shakier.
        smoothing: Smoothing window in frames, 0..100 (default 15). Higher =
            steadier but more cropping/warp.
        accuracy: Detection accuracy, 1..15 (default 15).
        zoom: Zoom percentage applied on the transform pass, -100..100
            (default 0). Positive hides warped borders.
        output_name: Optional output filename. Defaults to
            ``{stem}_stabilized{ext}``.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        src = _find_video_file(ws_path, source)
        if src is None:
            return _err("No video file found. Provide source or add files to media/raw/.")
        if not src.exists():
            return err(f"File not found: {src}", error_type=MISSING_FILE, suggestion="Check the source path; it is resolved relative to the workspace root unless absolute.", path=str(src))

        # Refuse an audio-only file up front: vidstab/deshake would otherwise
        # "succeed" and emit a bogus stabilized track with no video.
        if _has_video_stream(src) is False:
            return media_unreadable(
                str(src),
                cause="no video stream (audio-only or non-video file)",
            )

        # Safety: never overwrite files in media/raw/.
        raw_dir = (ws_path / "media" / "raw").resolve()
        try:
            src.resolve().relative_to(raw_dir)
            src_in_raw = True
        except ValueError:
            src_in_raw = False

        processed_dir = ws_path / "media" / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)

        output = stabilized_output_path(src, processed_dir, output_name or None)
        if src_in_raw and output.resolve() == src.resolve():
            return _err("Refusing to overwrite media/raw source; choose an output_name.")

        try:
            result = stabilize_file(
                src,
                output,
                shakiness=shakiness,
                smoothing=smoothing,
                accuracy=accuracy,
                zoom=zoom,
            )
        except FFmpegNotFound as exc:
            return missing_binary("ffmpeg", str(exc))
        except FFmpegTimeout as exc:
            return operation_failed(
                "Stabilization timed out.", cause=exc,
                suggestion="The clip may be very large or ffmpeg wedged; try a shorter clip.",
            )
        if not result["success"]:
            # Failed render: remove any partial/zero-byte output so nothing is
            # left half-written in media/processed.
            _cleanup_partial(output)
            return error_from_pipeline_result(
                result, "Stabilization failed", path=str(src),
            )

        data = {
            "input": str(src),
            "output": result["final_output"],
            "method": result["method"],
            "params": result["params"],
            "steps_count": len(result["steps"]),
        }
        if result["method"] == "deshake":
            data["note"] = (
                "libvidstab not available in this FFmpeg build; used single-pass "
                "deshake fallback."
            )
        return _ok(data)
    except Exception as exc:  # noqa: BLE001 -- surface any failure as an error dict
        return operation_failed(str(exc), cause=exc)
