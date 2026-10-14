"""Render executor.

Executes a render job using melt (MLT) or ffmpeg, captures logs, and
returns an updated RenderJob with final status.
"""
from __future__ import annotations

import logging
import json
import subprocess
from pathlib import Path

from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.edit_mcp.adapters.render.profiles import RenderProfile
from workshop_video_brain.edit_mcp.adapters.render.jobs import update_job_status
from workshop_video_brain.edit_mcp.adapters.render.media_check import (
    missing_media,
    missing_media_message,
)

logger = logging.getLogger(__name__)

# Default render timeout in seconds (30 minutes)
DEFAULT_TIMEOUT_SECONDS = 1800


def check_codec_available(codec_name: str) -> bool:
    """Check if an FFmpeg encoder is available on this system.

    Runs ``ffmpeg -encoders`` and searches for the encoder name in the output.

    Args:
        codec_name: Encoder name, e.g. "libx264", "prores_ks", "dnxhd".

    Returns:
        True if the codec is listed in FFmpeg's codec output, False otherwise.
    """
    try:
        result = subprocess.run(
            ["ffmpeg", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # Each codec line looks like: " DEV.L. libx264   description..."
        # Search for the codec name as a whole word
        for line in result.stdout.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                # The codec name is typically the second token after the flags
                if codec_name in parts or f"{codec_name})" in parts:
                    return True
        return False
    except FileNotFoundError:
        logger.warning(
            "Cannot check codec '%s': ffmpeg not found on PATH", codec_name
        )
        return False
    except subprocess.TimeoutExpired:
        logger.warning(
            "Cannot check codec '%s': ffmpeg -encoders timed out", codec_name
        )
        return False
    except OSError as exc:  # noqa: BLE001 -- best-effort availability probe
        logger.warning(
            "Could not check codec availability for '%s': %s", codec_name, exc
        )
        return False


def execute_render(
    job: RenderJob,
    profile: RenderProfile,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    _command_override: list[str] | None = None,
) -> RenderJob:
    """Execute a render job.

    Uses melt for Kdenlive XML and FFmpeg for direct media inputs. Captures
    stdout/stderr to the job's log file.

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
    from workshop_video_brain.core.utils.paths import assert_not_protected
    if running_job.output_path:
        assert_not_protected(running_job.output_path, "render output")
    if running_job.log_path:
        assert_not_protected(running_job.log_path, "render log")

    log_path = Path(running_job.log_path) if running_job.log_path else None
    if log_path:
        log_path.parent.mkdir(parents=True, exist_ok=True)

    # Record whether the output file already existed *before* this run so an
    # interrupted/failed render can never leave a half-written file behind for a
    # downstream tool (qc_check, a re-render, publish_bundle) to mistake for a
    # finished artifact. A file that this run newly created is, by definition,
    # partial when the render did not succeed.
    out_path = Path(running_job.output_path) if running_job.output_path else None
    output_preexisted = bool(out_path and out_path.exists())

    def _fail(message: str = "", error_type: str = "") -> RenderJob:
        _discard_partial_output(out_path, output_preexisted)
        failed = update_job_status(running_job, JobStatus.failed)
        if message:
            failed = failed.model_copy(
                update={"error_message": message, "error_type": error_type}
            )
        return failed

    # Precondition: every file-backed producer the project references must be on
    # disk. melt renders missing footage as blank frames and still exits 0, and
    # exit 0 is the only thing the branch below looks at -- so without this the
    # job reports "succeeded" against footage that no longer exists. Skipped when
    # the caller supplied _command_override: that hook replaces the render
    # command outright, so the project is not what gets executed.
    if _command_override is None:
        absent = missing_media(running_job.project_path)
        if absent:
            message = missing_media_message(running_job.project_path, absent)
            logger.error("Render aborted, media missing: %s", ", ".join(absent))
            if log_path:
                log_path.write_text(
                    f"Command: (not run -- pre-render media check failed)\n"
                    f"ERROR: {message}\n",
                    encoding="utf-8",
                )
            return _fail(message, "missing_file")

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
            duration, size = 0.0, 0
            if _command_override is None:
                try:
                    duration, size = verify_render_output(Path(running_job.output_path))
                except (OSError, ValueError, RuntimeError) as exc:
                    if log_path:
                        with log_path.open("a", encoding="utf-8") as log:
                            log.write(f"\nOutput verification failed: {exc}\n")
                    return _fail(str(exc), "invalid_output")
            logger.info("Render succeeded: %s", running_job.output_path)
            return update_job_status(running_job, JobStatus.succeeded).model_copy(
                update={"duration_seconds": duration, "file_size_bytes": size},
            )
        else:
            logger.error(
                "Render failed (exit %d): ...%s",
                result.returncode,
                result.stderr[-500:],
            )
            return _fail(f"Render failed (exit {result.returncode}): {result.stderr[-800:]}", "render_failed")

    except subprocess.TimeoutExpired:
        msg = f"Render timed out after {timeout_seconds}s."
        logger.error(msg)
        if log_path:
            log_path.write_text(
                f"Command: {' '.join(cmd)}\n"
                f"TIMEOUT after {timeout_seconds}s\n",
                encoding="utf-8",
            )
        return _fail(msg, "timeout")

    except FileNotFoundError as exc:
        binary = cmd[0] if cmd else "render binary"
        msg = (
            f"Render binary '{binary}' not found on PATH ({exc}). "
            f"Install it (e.g. 'apt install melt ffmpeg' / "
            f"'brew install mlt ffmpeg') and ensure it is on PATH."
        )
        logger.error(msg)
        if log_path:
            log_path.write_text(
                f"Command: {' '.join(cmd)}\n"
                f"ERROR: {msg}\n",
                encoding="utf-8",
            )
        return _fail(msg, "missing_binary")

    except Exception as exc:
        logger.exception("Unexpected render error: %s", exc)
        if log_path:
            log_path.write_text(
                f"Command: {' '.join(cmd)}\n"
                f"UNEXPECTED ERROR: {exc}\n",
                encoding="utf-8",
            )
        return _fail(str(exc), "render_failed")


def _discard_partial_output(out_path: Path | None, output_preexisted: bool) -> None:
    """Delete a half-written render output left by a failed/interrupted run.

    Only removes a file this run created (``output_preexisted`` is False): a
    pre-existing output is never touched. Best-effort — a cleanup failure is
    logged, never raised, so it cannot mask the real render failure.
    """
    if out_path is None or output_preexisted:
        return
    try:
        if out_path.exists():
            out_path.unlink()
            logger.warning(
                "Removed partial render output after failed render: %s", out_path
            )
    except OSError as exc:  # pragma: no cover - defensive
        logger.warning("Could not remove partial render output %s: %s", out_path, exc)


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
    """Build an melt (MLT framework) render command.

    Passes through alpha/advanced consumer properties when the profile
    defines them:

    - ``mlt_image_format`` (e.g. ``rgba``) preserves the alpha channel through
      the MLT pipeline instead of flattening onto black.
    - ``pix_fmt`` (e.g. ``yuva420p``, ``argb``) selects an alpha-capable
      encoder pixel format.
    - ``melt_args`` are raw ``key=value`` consumer properties (e.g. ``f=webm``
      to force the container, ``vprofile=4`` for ProRes 4444).
    - ``disable_audio`` emits ``an=1`` and omits the audio codec/bitrate.
    """
    cmd = [
        "melt",
        str(project_path),
        "-consumer",
        f"avformat:{output_path}",
        f"vcodec={profile.video_codec}",
        f"vb={profile.video_bitrate}",
    ]

    # Alpha renders need the MLT image format set before other properties so
    # the alpha channel is retained end to end.
    if profile.mlt_image_format:
        cmd.append(f"mlt_image_format={profile.mlt_image_format}")
    if profile.pix_fmt:
        cmd.append(f"pix_fmt={profile.pix_fmt}")

    if profile.disable_audio:
        cmd.append("an=1")
    else:
        cmd.append(f"acodec={profile.audio_codec}")
        cmd.append(f"ab={profile.audio_bitrate}")

    cmd.extend([
        f"width={profile.width}",
        f"height={profile.height}",
        f"frame_rate_num={profile.frame_rate.numerator}",
        f"frame_rate_den={profile.frame_rate.denominator}",
    ])

    if profile.container:
        cmd.append(f"f={profile.muxer}")
    if profile.fast_start or profile.movflags:
        cmd.append(f"movflags={profile.movflags or '+faststart'}")

    # Extra raw consumer properties (container format, encoder profile, ...).
    cmd.extend(profile.melt_args)

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
        str(profile.frame_rate),
        "-c:v",
        profile.video_codec,
        "-b:v",
        profile.video_bitrate,
        "-c:a",
        profile.audio_codec,
        "-b:a",
        profile.audio_bitrate,
    ]

    if profile.disable_audio:
        audio_index = cmd.index("-c:a")
        del cmd[audio_index:audio_index + 4]
        cmd.append("-an")
    if profile.pix_fmt:
        cmd.extend(["-pix_fmt", profile.pix_fmt])
    if profile.fast_start or profile.movflags:
        cmd.extend(["-movflags", profile.movflags or "+faststart"])
    if profile.container:
        cmd.extend(["-f", profile.muxer])
    # Append extra args from the profile
    cmd.extend(profile.extra_args)
    cmd.append(output_path)

    return cmd


def verify_render_output(path: Path) -> tuple[float, int]:
    """Require a nonempty, probeable artifact with a positive duration."""
    size = path.stat().st_size
    if size <= 0:
        raise ValueError(f"Render output is empty: {path}")
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode:
        raise RuntimeError(f"Cannot probe render output: {result.stderr[-800:]}")
    try:
        data = json.loads(result.stdout)
        duration = float(data.get("format", {}).get("duration", 0))
        if not data.get("streams") or not 0 < duration < float("inf"):
            raise ValueError("Render output has no streams or positive finite duration")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid ffprobe metadata for render output") from exc
    return duration, size
