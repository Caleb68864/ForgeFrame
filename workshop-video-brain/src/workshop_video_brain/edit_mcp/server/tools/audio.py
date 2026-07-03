"""Audio processing tools.

Carved from the former monolithic ``server/tools.py``. Each function
registers with the shared FastMCP singleton via ``@mcp.tool()``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.server import mcp
from workshop_video_brain.edit_mcp.server.errors import (  # noqa: F401
    tool_guard,
    err,
    missing_file,
    missing_binary,
    missing_dependency,
    invalid_index,
    bad_json_param,
    corrupt_project,
    media_unreadable,
    not_found,
    invalid_input,
    operation_failed,
    from_exception,
)
from workshop_video_brain.edit_mcp.server.tools_helpers import (
    _ok,
    _err,
    _validate_workspace_path,
)





# ---------------------------------------------------------------------------
# Audio processing tools
# ---------------------------------------------------------------------------
def _find_audio_file(workspace_path: Path, file_path: str) -> Path | None:
    """Locate an audio file: explicit path or first/latest in media/raw."""
    if file_path and file_path.strip():
        p = Path(file_path)
        if not p.is_absolute():
            p = workspace_path / file_path
        # Only accept a real file: a missing path or a directory must not be
        # handed to ffmpeg (which fails with a noisy banner). Returning None
        # routes to the loud "No audio file found" error instead.
        return p if p.is_file() else None

    raw_dir = workspace_path / "media" / "raw"
    if not raw_dir.exists():
        return None
    audio_exts = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".mp4", ".mov", ".mkv"}
    candidates = sorted(
        (f for f in raw_dir.iterdir() if f.is_file() and f.suffix.lower() in audio_exts),
        key=lambda f: f.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else None


def _ensure_processed_dir(workspace_path: Path) -> Path:
    """Ensure media/processed exists and return it."""
    processed = workspace_path / "media" / "processed"
    processed.mkdir(parents=True, exist_ok=True)
    return processed


@mcp.tool()
@tool_guard
def audio_normalize(
    workspace_path: str,
    file_path: str = "",
    target_lufs: float = -16.0,
) -> dict:
    """Normalize audio to YouTube-standard loudness (-16 LUFS).

    Args:
        workspace_path: Path to workspace root.
        file_path: Path to audio file. If empty, processes latest file in media/raw/.
        target_lufs: Target integrated loudness in LUFS (default -16.0).
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        source = _find_audio_file(ws_path, file_path)
        if source is None:
            return invalid_input("No audio file found. Provide file_path or add files to media/raw/.", "Pass file_path to an existing audio/video file, or add a media file to media/raw/.", param="file_path")
        if not source.exists():
            return err(f"File not found: {source}", error_type="missing_file", suggestion="Check the media path is correct and the file exists.", path=str(source))

        processed_dir = _ensure_processed_dir(ws_path)
        output = processed_dir / source.name

        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import normalize_audio
        result = normalize_audio(source, output, target_lufs=target_lufs)
        if not result.success:
            return operation_failed("FFmpeg normalize failed", cause=result.stderr[-300:], suggestion="Confirm the input is a valid audio/video file and ffmpeg is installed.")
        return _ok({
            "input": str(source),
            "output": str(output),
            "target_lufs": target_lufs,
            "duration_ms": result.duration_ms,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def audio_compress(workspace_path: str, file_path: str = "") -> dict:
    """Reduce dynamic range for consistent volume.

    Args:
        workspace_path: Path to workspace root.
        file_path: Path to audio file. If empty, processes latest file in media/raw/.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        source = _find_audio_file(ws_path, file_path)
        if source is None:
            return invalid_input("No audio file found. Provide file_path or add files to media/raw/.", "Pass file_path to an existing audio/video file, or add a media file to media/raw/.", param="file_path")
        if not source.exists():
            return err(f"File not found: {source}", error_type="missing_file", suggestion="Check the media path is correct and the file exists.", path=str(source))

        processed_dir = _ensure_processed_dir(ws_path)
        output = processed_dir / source.name

        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import compress_audio
        result = compress_audio(source, output)
        if not result.success:
            return operation_failed("FFmpeg compress failed", cause=result.stderr[-300:], suggestion="Confirm the input is a valid audio/video file and ffmpeg is installed.")
        return _ok({
            "input": str(source),
            "output": str(output),
            "duration_ms": result.duration_ms,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def audio_denoise(
    workspace_path: str,
    file_path: str = "",
    strength_db: float = -25.0,
) -> dict:
    """Remove background noise from audio.

    Args:
        workspace_path: Path to workspace root.
        file_path: Path to audio file. If empty, processes latest file in media/raw/.
        strength_db: Noise floor threshold in dB (default -25.0).
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        source = _find_audio_file(ws_path, file_path)
        if source is None:
            return invalid_input("No audio file found. Provide file_path or add files to media/raw/.", "Pass file_path to an existing audio/video file, or add a media file to media/raw/.", param="file_path")
        if not source.exists():
            return err(f"File not found: {source}", error_type="missing_file", suggestion="Check the media path is correct and the file exists.", path=str(source))

        processed_dir = _ensure_processed_dir(ws_path)
        output = processed_dir / source.name

        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import remove_background_noise
        result = remove_background_noise(source, output, noise_floor_db=strength_db)
        if not result.success:
            return operation_failed("FFmpeg denoise failed", cause=result.stderr[-300:], suggestion="Confirm the input is a valid audio/video file and ffmpeg is installed.")
        return _ok({
            "input": str(source),
            "output": str(output),
            "strength_db": strength_db,
            "duration_ms": result.duration_ms,
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def audio_enhance(
    workspace_path: str,
    file_path: str = "",
    preset: str = "youtube_voice",
) -> dict:
    """Apply full voice enhancement pipeline (highpass -> denoise -> compress -> normalize -> limit).

    Presets: youtube_voice, podcast, raw_cleanup.

    Args:
        workspace_path: Path to workspace root.
        file_path: Path to audio file. If empty, processes latest file in media/raw/.
        preset: Enhancement preset. One of: youtube_voice, podcast, raw_cleanup.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        source = _find_audio_file(ws_path, file_path)
        if source is None:
            return invalid_input("No audio file found. Provide file_path or add files to media/raw/.", "Pass file_path to an existing audio/video file, or add a media file to media/raw/.", param="file_path")
        if not source.exists():
            return err(f"File not found: {source}", error_type="missing_file", suggestion="Check the media path is correct and the file exists.", path=str(source))

        processed_dir = _ensure_processed_dir(ws_path)
        output = processed_dir / source.name

        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import voice_enhance_chain
        chain_result = voice_enhance_chain(source, output, preset=preset)
        if not chain_result["success"]:
            return _err(
                chain_result.get("error", "Enhancement pipeline failed")
            )
        return _ok({
            "input": str(source),
            "output": chain_result["final_output"],
            "preset": chain_result["preset_used"],
            "steps_count": len(chain_result["steps"]),
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def audio_enhance_all(
    workspace_path: str,
    preset: str = "youtube_voice",
) -> dict:
    """Enhance all audio in workspace media/raw/ folder.

    Args:
        workspace_path: Path to workspace root.
        preset: Enhancement preset. One of: youtube_voice, podcast, raw_cleanup.
    """
    try:
        ws_path = _validate_workspace_path(workspace_path)
        raw_dir = ws_path / "media" / "raw"
        if not raw_dir.exists():
            return _err("media/raw/ directory not found in workspace.")

        processed_dir = _ensure_processed_dir(ws_path)

        from workshop_video_brain.edit_mcp.adapters.ffmpeg.audio import batch_process
        batch_result = batch_process(raw_dir, processed_dir, preset=preset)
        return _ok({
            "processed": batch_result["processed"],
            "failed": batch_result["failed"],
            "output_dir": str(processed_dir),
            "preset": preset,
            "files": list(batch_result["results"].keys()),
        })
    except Exception as exc:
        return from_exception(exc)


@mcp.tool()
@tool_guard
def audio_analyze(workspace_path: str, file_path: str = "") -> dict:
    """Analyze audio levels (LUFS, peak, noise floor) without modifying.

    Args:
        workspace_path: Path to workspace root.
        file_path: Path to audio file. If empty, analyzes latest file in media/raw/.
    """
    import json as _json
    import re
    import subprocess

    try:
        ws_path = _validate_workspace_path(workspace_path)
        source = _find_audio_file(ws_path, file_path)
        if source is None:
            return invalid_input("No audio file found. Provide file_path or add files to media/raw/.", "Pass file_path to an existing audio/video file, or add a media file to media/raw/.", param="file_path")
        if not source.exists():
            return err(f"File not found: {source}", error_type="missing_file", suggestion="Check the media path is correct and the file exists.", path=str(source))

        result = subprocess.run(
            [
                "ffmpeg",
                "-i", str(source),
                "-af", "loudnorm=print_format=json",
                "-f", "null",
                "-",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        # ffmpeg writes loudnorm JSON to stderr
        stderr = result.stderr
        json_match = re.search(r"\{[^{}]*\}", stderr, re.DOTALL)
        if not json_match:
            return _err("Could not parse loudnorm output from FFmpeg.")

        loudnorm_data = _json.loads(json_match.group())
        return _ok({
            "input": str(source),
            "integrated_lufs": float(loudnorm_data.get("input_i", 0)),
            "true_peak_db": float(loudnorm_data.get("input_tp", 0)),
            "loudness_range": float(loudnorm_data.get("input_lra", 0)),
            "threshold": float(loudnorm_data.get("input_thresh", 0)),
            "raw": loudnorm_data,
        })
    except Exception as exc:
        return from_exception(exc)
