"""``audio_normalize_two_pass`` MCP tool -- measured two-pass loudnorm.

Auto-imported by ``server/bundles/__init__.py``; registers one tool on the
shared FastMCP singleton. Follows the shape of ``media_stabilize`` and the
audio file-processing tools: resolve a source under the workspace, never touch
``media/raw``, write the result into ``media/processed/``, and return an
``_ok`` / ``_err`` result dict.

Supersedes the single-pass ``audio_normalize`` path with the accurate measured
two-pass form. Works on audio files and video files alike (video stream-copied,
only audio re-normalized).
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegNotFound,
    FFmpegTimeout,
)
from workshop_video_brain.edit_mcp.pipelines.loudnorm_two_pass import (
    normalize_two_pass_file,
    normalized_output_path,
)
from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import (
    cleanup_partial_output as _cleanup_partial,
    error_from_pipeline_result,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _validate_workspace_path,
    find_source_or_latest,
)
from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # hardening pass 1
    tool_guard,
    err,
    missing_binary,
    operation_failed,
    MISSING_FILE,
)

# Audio + video containers this tool accepts (mirrors server.tools audio exts).
_MEDIA_EXTS = {
    ".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".opus",
    ".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".mts", ".m2ts",
}


def _find_media_file(workspace_path: Path, source: str) -> Path | None:
    """Locate a media file: explicit path or latest in ``media/raw``."""
    return find_source_or_latest(workspace_path, source, _MEDIA_EXTS)


@mcp.tool()
@tool_guard
def audio_normalize_two_pass(
    workspace_path: str,
    source: str = "",
    target_i: float = -16.0,
    target_tp: float = -1.5,
    target_lra: float = 11.0,
    output_name: str = "",
) -> dict:
    """Normalize loudness accurately with measured two-pass FFmpeg ``loudnorm``.

    Pass 1 measures integrated loudness / true-peak / loudness-range / threshold;
    pass 2 applies ``loudnorm`` with those measured values fed back and
    ``linear=true``, which is far more accurate than the single-pass
    ``audio_normalize``. If linear normalization is not achievable for the
    material, ``loudnorm`` falls back to dynamic mode and a ``warning`` is
    returned. Works on audio files and on video files (video is stream-copied;
    only the audio is re-normalized). Writes to ``media/processed/``; the source
    in ``media/raw`` is never modified.

    Args:
        workspace_path: Path to workspace root.
        source: Path to the audio/video file. If empty, uses the latest file in
            ``media/raw/``.
        target_i: Target integrated loudness in LUFS (default -16.0, YouTube).
        target_tp: Target maximum true peak in dBTP (default -1.5).
        target_lra: Target loudness range in LU (default 11.0).
        output_name: Optional output filename. Defaults to
            ``{stem}_normalized{ext}``.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        src = _find_media_file(ws_path, source)
        if src is None:
            return err(
                "No media file found. Provide source or add files to media/raw/.",
                suggestion="Pass source pointing at a media file, or drop a clip into media/raw/ so the tool can pick it up automatically.",
            )
        if not src.exists():
            return err(f"File not found: {src}", error_type=MISSING_FILE, suggestion="Check the source path; it is resolved relative to the workspace root unless absolute.", path=str(src))

        # Safety: never overwrite files in media/raw/.
        raw_dir = (ws_path / "media" / "raw").resolve()
        try:
            src.resolve().relative_to(raw_dir)
            src_in_raw = True
        except ValueError:
            src_in_raw = False

        processed_dir = ws_path / "media" / "processed"
        processed_dir.mkdir(parents=True, exist_ok=True)

        output = normalized_output_path(src, processed_dir, output_name or None)
        if src_in_raw and output.resolve() == src.resolve():
            return err(
                "Refusing to overwrite your original source in media/raw/; media/raw/ is read-only by design.",
                suggestion="Pass a different output_name so the result is written to media/processed/ instead.",
            )

        try:
            result = normalize_two_pass_file(
                src,
                output,
                target_i=target_i,
                target_tp=target_tp,
                target_lra=target_lra,
            )
        except FFmpegNotFound as exc:
            return missing_binary("ffmpeg", str(exc))
        except FFmpegTimeout as exc:
            return operation_failed(
                "Two-pass normalization timed out.", cause=exc,
                suggestion="The file may be very large or ffmpeg wedged; try a shorter clip.",
            )
        if not result["success"]:
            _cleanup_partial(output)
            return error_from_pipeline_result(
                result, "Two-pass normalization failed", path=str(src),
            )

        data = {
            "input": str(src),
            "output": result["final_output"],
            "has_video": result["has_video"],
            "measured": result["measured"],
            "target": result["target"],
            "achieved_i": result["achieved_i"],
            "normalization_type": result["normalization_type"],
            "linear_requested": result["linear_requested"],
            "linear_applied": result["linear_applied"],
            "steps_count": len(result["steps"]),
        }
        if result.get("warning"):
            data["warning"] = result["warning"]
        return _ok(data)
    except Exception as exc:  # noqa: BLE001 -- surface any failure as an error dict
        return operation_failed(str(exc), cause=exc)
