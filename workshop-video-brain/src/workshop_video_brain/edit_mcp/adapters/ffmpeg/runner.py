"""FFmpeg runner utility with structured result capture."""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Generous default wall-clock ceiling for a single FFmpeg invocation. Renders,
# vidstab pass-1 detection, and minterpolate-class motion filters can legitimately
# run for many minutes on large clips, so this is deliberately high (1 hour). It
# exists only to stop a wedged/hung process from hanging the server forever.
DEFAULT_TIMEOUT_SECONDS: float = 3600.0

# Install hint surfaced when the ffmpeg binary itself is missing from PATH.
_FFMPEG_INSTALL_HINT = (
    "Install FFmpeg and ensure it is on PATH "
    "(e.g. 'sudo pacman -S ffmpeg', 'apt install ffmpeg', or 'brew install ffmpeg')."
)


class FFmpegNotFound(RuntimeError):
    """Raised when the ``ffmpeg`` binary is not on PATH.

    Distinct from a command *failure* (nonzero exit, captured on
    :class:`FFmpegResult`): this is an environment problem the user must fix by
    installing FFmpeg. The message always carries an actionable install hint.
    """


class FFmpegTimeout(RuntimeError):
    """Raised when an FFmpeg invocation exceeds its wall-clock timeout.

    The message names the (truncated) command and the elapsed/limit seconds so
    the failure is diagnosable without digging through logs.
    """


class FFmpegCommandError(RuntimeError):
    """Raised by *raise-on-failure* adapters when ffmpeg/ffprobe exits nonzero.

    Carries the binary name, return code, and the stderr *tail* (last ~10
    lines) in the message -- not the full dump -- so the failure is actionable.
    Adapters that instead return an :class:`FFmpegResult` report failures via
    ``success=False`` and never raise this.
    """


def _stderr_tail(stderr: str, max_lines: int = 10) -> str:
    """Return the last *max_lines* non-empty lines of *stderr* (the useful part).

    Shared by the raise-on-failure adapters (probe, proxy, silence,
    extract_audio) so failure messages carry the diagnosable tail, not the full
    dump.
    """
    lines = [ln for ln in stderr.splitlines() if ln.strip()]
    return "\n".join(lines[-max_lines:])


class FFmpegResult(BaseModel):
    """Structured result from an FFmpeg operation."""

    success: bool
    input_path: str
    output_path: str
    command: list[str]
    stdout: str = ""
    stderr: str = ""
    duration_ms: float = 0.0

    @property
    def stderr_tail(self) -> str:
        """Last ~10 non-empty stderr lines -- the diagnosable part of a failure."""
        return _stderr_tail(self.stderr)


def run_ffmpeg(
    args: list[str],
    input_path: Path,
    output_path: Path,
    overwrite: bool = True,
    dry_run: bool = False,
    timeout: float | None = DEFAULT_TIMEOUT_SECONDS,
) -> FFmpegResult:
    """Execute an FFmpeg command with structured result capture.

    Args:
        args: FFmpeg arguments (filters, codecs, etc.) -- WITHOUT -i input or output
        input_path: Source file path
        output_path: Destination file path
        overwrite: If True, add -y flag
        dry_run: If True, return the command without executing
        timeout: Wall-clock ceiling in seconds (default 1 hour). ``None``
            disables the timeout entirely (use only for known-bounded work).

    Returns:
        FFmpegResult with success status, captured logs, and timing. A nonzero
        FFmpeg exit is reported as ``success=False`` (a *command* failure the
        caller can inspect), not raised.

    Raises:
        FFmpegNotFound: if the ffmpeg binary is not on PATH (environment error,
            carries an install hint).
        FFmpegTimeout: if the process exceeds *timeout* seconds; the message
            names the command and elapsed time.
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
            cmd, capture_output=True, text=True, check=False, timeout=timeout
        )
    except FileNotFoundError as exc:
        # The ffmpeg executable itself is missing -- an environment error, not a
        # per-command failure. Raise a typed, install-hinted exception so the
        # tool layer maps it to a 'missing_binary' error.
        raise FFmpegNotFound(
            f"ffmpeg binary not found on PATH (input: {input_path}). "
            f"{_FFMPEG_INSTALL_HINT}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        elapsed = time.monotonic() - start
        partial = exc.stderr or b""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", "replace")
        raise FFmpegTimeout(
            f"ffmpeg timed out after {elapsed:.0f}s (limit {timeout:.0f}s) on "
            f"{input_path.name}. Command: {' '.join(cmd[:6])} ... "
            + (f"Last output:\n{_stderr_tail(partial)}" if partial else "")
        ) from exc

    elapsed_ms = (time.monotonic() - start) * 1000.0

    success = result.returncode == 0
    if not success:
        logger.warning(
            "FFmpeg failed (rc=%d) on %s:\n%s",
            result.returncode,
            input_path.name,
            _stderr_tail(result.stderr),
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
