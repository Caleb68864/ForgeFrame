"""FFmpeg runner utility with structured result capture."""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class FFmpegResult(BaseModel):
    """Structured result from an FFmpeg operation."""

    success: bool
    input_path: str
    output_path: str
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0


def run_ffmpeg(
    args: list[str],
    input_path: Path,
    output_path: Path,
    overwrite: bool = True,
    dry_run: bool = False,
) -> FFmpegResult:
    """Execute an FFmpeg command with structured result capture.

    Args:
        args: FFmpeg arguments (filters, codecs, etc.) -- WITHOUT -i input or output
        input_path: Source file path
        output_path: Destination file path
        overwrite: If True, add -y flag
        dry_run: If True, return the command without executing

    Returns:
        FFmpegResult with success status, captured logs, and timing
    """
    cmd: list[str] = ["ffmpeg"]
    if overwrite:
        cmd.append("-y")
    cmd += ["-i", str(input_path)]
    cmd += args
    cmd.append(str(output_path))

    if dry_run:
        return FFmpegResult(
            success=True,
            input_path=str(input_path),
            output_path=str(output_path),
            command=cmd,
        )

    logger.debug("Running: %s", " ".join(cmd))
    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=600
        )
    except subprocess.TimeoutExpired as exc:
        elapsed_ms = (time.monotonic() - start) * 1000.0
        logger.warning("FFmpeg timed out after %.1fs: %s", elapsed_ms / 1000.0, cmd)
        return FFmpegResult(
            success=False,
            input_path=str(input_path),
            output_path=str(output_path),
            command=cmd,
            stdout=(exc.stdout.decode(errors="replace") if exc.stdout else ""),
            stderr=(exc.stderr.decode(errors="replace") if exc.stderr else "TIMEOUT"),
            duration_ms=elapsed_ms,
        )
    elapsed_ms = (time.monotonic() - start) * 1000.0

    success = result.returncode == 0
    if not success:
        logger.warning(
            "FFmpeg failed (rc=%d): %s", result.returncode, result.stderr[-500:]
        )

    return FFmpegResult(
        success=success,
        input_path=str(input_path),
        output_path=str(output_path),
        command=cmd,
        stdout=result.stdout,
        stderr=result.stderr,
        duration_ms=elapsed_ms,
    )
