"""Shared bits for the plain-file media tool shells (skipped by discovery)."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.server.bundles._pipeline_errors import cleanup_partial_output
from workshop_video_brain.edit_mcp.server.errors import invalid_input, missing_file, operation_failed


def source_path(source: str, param: str = "source") -> Path | dict:
    if not source or not str(source).strip():
        return invalid_input(f"{param} must be a file path", f"Pass the media file as {param}.", param=param)
    path = Path(source).expanduser()
    if not path.is_file():
        return missing_file(str(path), param)
    return path.resolve()


def ffmpeg_ok_or_error(result, output: Path, what: str) -> dict | None:
    if result.success:
        return None
    cleanup_partial_output(output)
    return operation_failed(
        f"{what} failed", cause=result.stderr_tail or "ffmpeg exited non-zero",
        suggestion="ffmpeg's own message is in 'cause'; check the input file plays and the options are valid.",
    )
