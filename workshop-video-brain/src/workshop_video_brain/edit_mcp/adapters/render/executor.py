"""Render executor.

Executes a render job using melt (MLT) or ffmpeg, captures logs, and
returns an updated RenderJob with final status.
"""
from __future__ import annotations

import logging
import subprocess
from datetime import datetime
from pathlib import Path

from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.edit_mcp.adapters.render.profiles import RenderProfile
from workshop_video_brain.edit_mcp.adapters.render.jobs import update_job_status

logger = logging.getLogger(__name__)

# Default render timeout in seconds (30 minutes)
DEFAULT_TIMEOUT_SECONDS = 1800


def execute_render(
    job: RenderJob,
    profile: RenderProfile,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    _command_override: list[str] | None = None,
) -> RenderJob:
    """Execute a render job.

    Attempts to render using melt first, falls back to ffmpeg if melt is not
    available. Captures stdout/stderr to the job's log file.

    Args:
        job: RenderJob with project_path, output_path, and log_path set.
        profile: RenderProfile with codec settings.
        timeout_seconds: Maximum time to allow for the render process.
        _command_override: Internal test hook — provide a custom command list
                           to avoid spawning real processes in tests.

    Returns:
        Updated RenderJob with final status (succeeded or failed).
    """
    # Mark as running
    running_job = update_job_status(job, JobStatus.running)

    log_path = Path(running_job.log_path) if running_job.log_path else None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = _command_override or _build_command(running_job, profile)

    logger.info("Render command: %s", " ".join(cmd))

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

        # Write log file
        if log_path:
            log_path.write_text(
                f"Command: {' '.join(cmd)}\n"
                f"Return code: {result.returncode}\n"
                f"--- stdout ---\n{result.stdout}\n"
                f"--- stderr ---\n{result.stderr}\n",
                encoding="utf-8",
            )

        if result.returncode == 0:
            logger.info("Render succeeded: %s", running_job.output_path)
            return update_job_status(running_job, JobStatus.succeeded)
        else:
            logger.error(
                "Render failed (exit %d): %s",
                result.returncode,
                result.stderr[:500],
            )
            return update_job_status(running_job, JobStatus.failed)

    except subprocess.TimeoutExpired:
        msg = f"Render timed out after {timeout_seconds}s."
        logger.error(msg)
        if log_path:
            log_path.write_text(
                f"Command: {' '.join(cmd)}\n"
                f"TIMEOUT after {timeout_seconds}s\n",
                encoding="utf-8",
            )
        return update_job_status(running_job, JobStatus.failed)

    except FileNotFoundError as exc:
        msg = f"Render command not found: {exc}"
        logger.error(msg)
        if log_path:
            log_path.write_text(
                f"Command: {' '.join(cmd)}\n"
                f"ERROR: {msg}\n",
                encoding="utf-8",
            )
        return update_job_status(running_job, JobStatus.failed)

    except Exception as exc:
        logger.exception("Unexpected render error: %s", exc)
        if log_path:
            log_path.write_text(
                f"Command: {' '.join(cmd)}\n"
                f"UNEXPECTED ERROR: {exc}\n",
                encoding="utf-8",
            )
        return update_job_status(running_job, JobStatus.failed)


def _build_command(job: RenderJob, profile: RenderProfile) -> list[str]:
    """Build an ffmpeg command for the render job.

    Prefers melt if the project file is a .kdenlive file.
    Falls back to ffmpeg for other project types.
    """
    project_path = Path(job.project_path)
    output_path = job.output_path

    if project_path.suffix.lower() == ".kdenlive":
        return _build_melt_command(project_path, output_path, profile)
    else:
        return _build_ffmpeg_command(project_path, output_path, profile)


def _build_melt_command(
    project_path: Path,
    output_path: str,
    profile: RenderProfile,
) -> list[str]:
    """Build an melt (MLT framework) render command."""
    cmd = [
        "melt",
        str(project_path),
        "-consumer",
        f"avformat:{output_path}",
        f"vcodec={profile.video_codec}",
        f"vb={profile.video_bitrate}",
        f"acodec={profile.audio_codec}",
        f"ab={profile.audio_bitrate}",
        f"width={profile.width}",
        f"height={profile.height}",
        f"frame_rate_num={int(profile.fps)}",
        "frame_rate_den=1",
    ]
    return cmd


def _build_ffmpeg_command(
    project_path: Path,
    output_path: str,
    profile: RenderProfile,
) -> list[str]:
    """Build an ffmpeg re-encode command."""
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(project_path),
        "-vf",
        f"scale={profile.width}:{profile.height}",
        "-r",
        str(profile.fps),
        "-c:v",
        profile.video_codec,
        "-b:v",
        profile.video_bitrate,
        "-c:a",
        profile.audio_codec,
        "-b:a",
        profile.audio_bitrate,
    ]

    # Append extra args from the profile
    cmd.extend(profile.extra_args)
    cmd.append(output_path)

    return cmd
