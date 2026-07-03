"""Shared mapping from typed pipeline result dicts to the MCP error contract.

Several file-processing pipelines (``stabilize``, ``denoise_video``,
``loudnorm_two_pass``, ``silence_segment``, ``thumbnail_sheet``, ``review_loop``,
``ai_mask``, ``audio_sync``) return a plain result ``dict`` carrying
``{"success": False, "error": <str>, "error_type": <stable machine key>}``.
Hardening pass 2 added the ``error_type`` field so the bundle layer can classify
those failures instead of re-wrapping them as an untyped ``_err(str)``.

This helper turns such a result into the structured error dict from
``server/errors.py``, choosing an actionable suggestion per error_type while
preserving the pipeline's own ``error`` text under ``message``.
"""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from workshop_video_brain.edit_mcp.server.errors import (
    VALID_ERROR_TYPES,
    OPERATION_FAILED,
    err,
)

logger = logging.getLogger("workshop_video_brain.edit_mcp.tools")


def has_video_stream(path: Path | str) -> bool | None:
    """Return True/False if *path* has a video stream, or None if undeterminable.

    Used by video-only tools (stabilize/denoise) to refuse an audio-only file
    up front rather than emit a bogus "stabilized" audio track. ``None`` (ffprobe
    missing / errored) means "cannot tell" -- callers should not block on it.
    """
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-select_streams", "v",
                "-show_entries", "stream=codec_type",
                "-of", "csv=p=0",
                str(path),
            ],
            capture_output=True, text=True, check=False, timeout=60,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    return "video" in proc.stdout


def cleanup_partial_output(*paths: Path | str | None) -> None:
    """Remove any partial/zero-byte output files left by a failed render.

    A failed ffmpeg/melt run can leave a truncated or zero-byte file in
    ``media/processed`` (or a report dir). On the failure path the bundle calls
    this so a later run does not mistake the stub for a finished output. Missing
    files are ignored; unlink errors are logged, never raised.
    """
    for p in paths:
        if p is None:
            continue
        path = Path(p)
        try:
            if path.exists() and path.is_file():
                path.unlink()
                logger.warning("removed partial output after failure: %s", path)
        except OSError as exc:  # pragma: no cover - defensive
            logger.warning("could not remove partial output %s: %s", path, exc)

# Per-type default suggestions used when the pipeline result does not carry one.
_SUGGESTIONS: dict[str, str] = {
    "missing_file": (
        "Check the source path; it is resolved relative to the workspace root "
        "unless absolute, and must exist before processing."
    ),
    "missing_binary": (
        "Install the required binary (ffmpeg/ffprobe/melt) and ensure it is on "
        "PATH, then retry."
    ),
    "missing_dependency": (
        "Install the missing Python package into the environment, then retry."
    ),
    "media_unreadable": (
        "Confirm the source is a valid, non-truncated media file of the expected "
        "type (video tools need a video stream, audio tools an audio stream)."
    ),
    "invalid_input": (
        "Check the arguments -- one is empty, the wrong type, or out of range."
    ),
    "operation_failed": (
        "The external tool ran but failed; inspect the 'cause' tail for the "
        "underlying ffmpeg/melt error and verify the input and parameters."
    ),
}


def error_from_pipeline_result(
    result: dict,
    default_message: str,
    **extra: Any,
) -> dict:
    """Map a ``{success:False, error, error_type}`` pipeline dict to an error dict.

    Args:
        result: The pipeline result dict (already known to be a failure).
        default_message: Fallback human message when ``result['error']`` is absent.
        **extra: Additional echo fields to attach (e.g. ``path=...``).

    Returns:
        A ``server/errors.err()`` payload with a stable ``error_type`` +
        actionable ``suggestion``, preserving the pipeline's ``error`` text.
    """
    error_type = result.get("error_type") or OPERATION_FAILED
    if error_type not in VALID_ERROR_TYPES:
        error_type = OPERATION_FAILED
    message = result.get("error") or default_message
    suggestion = _SUGGESTIONS.get(error_type, _SUGGESTIONS[OPERATION_FAILED])
    return err(
        message,
        error_type=error_type,
        suggestion=suggestion,
        **{k: v for k, v in extra.items() if v is not None},
    )
