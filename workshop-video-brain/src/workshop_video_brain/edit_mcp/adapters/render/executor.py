"""Render executor.

Executes a render job using melt (MLT) or ffmpeg, captures logs, and
returns an updated RenderJob with final status.
"""
from __future__ import annotations

import logging
import codecs
import json
import os
import subprocess
import signal
import tempfile
import threading
import time
import xml.etree.ElementTree as ET
from math import gcd
from pathlib import Path

from workshop_video_brain.core.models.enums import JobStatus
from workshop_video_brain.core.models.project import RenderJob
from workshop_video_brain.edit_mcp.adapters.render.profiles import RenderProfile
from workshop_video_brain.edit_mcp.adapters.render.jobs import update_job_status
from workshop_video_brain.edit_mcp.adapters.render.progress import (
    MeltProgressReader,
    ProgressCallback,
    RenderProgress,
)
from workshop_video_brain.edit_mcp.adapters.render.timeline_length import timeline_length
from workshop_video_brain.edit_mcp.adapters.render.media_check import (
    missing_media,
    missing_media_message,
)

from workshop_video_brain.edit_mcp.adapters.mlt.display import (
    HEADLESS_MESSAGE,
    HEADLESS_SUGGESTION,
    mlt_env,
    qt_display_failed,
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
    on_progress: ProgressCallback | None = None,
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
        on_progress: Called with frame positions as they are rendered. Only the
                     bindings engine (``WVB_RENDER_ENGINE``) reports them.

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

    use_bindings = _command_override is None and _select_render_engine(Path(running_job.project_path)) == "mlt"
    melt_profile = None
    if _command_override is None and not use_bindings and cmd[0] == "melt":
        melt_profile = _write_melt_profile(Path(running_job.project_path), profile.width, profile.height)
        if melt_profile is not None:
            cmd = _with_melt_profile(cmd, melt_profile)

    # Timeline length: the progress total and the shortest acceptable output.
    length = timeline_length(running_job.project_path) if _command_override is None else None
    total_frames = length[0] if length else 0

    def report(update: RenderProgress) -> None:
        # A progress consumer (job record, UI) must never kill the render.
        try:
            on_progress(update)  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001
            logger.debug("Render progress callback failed: %s", exc)

    try:
        if use_bindings:
            result = _render_with_bindings(running_job, cmd, timeout_seconds, on_progress)
        else:
            is_melt = bool(cmd) and Path(cmd[0]).name == "melt"
            reader = (MeltProgressReader(report, total_frames)
                      if on_progress is not None and is_melt else None)
            # Headless: let MLT's Qt module start offscreen (adapters/mlt/display).
            env = mlt_env() if is_melt else None
            watched = is_melt and "-progress2" in cmd
            if watched or reader is not None:
                # Stream stderr: melt's progress lines feed the callback and the
                # stall watchdog. One stalled attempt is retried from scratch.
                stall = _stall_seconds() if watched else None
                try:
                    result = _run_render_process(cmd, timeout_seconds, reader.feed if reader else None,
                                                 env=env, stall_seconds=stall)
                except RenderStalled as first:
                    logger.warning("Render stalled (%s); retrying once", first)
                    _discard_partial_output(out_path, output_preexisted)
                    try:
                        result = _run_render_process(cmd, timeout_seconds, reader.feed if reader else None,
                                                     env=env, stall_seconds=stall)
                    except RenderStalled as second:
                        msg = (f"Render stalled: melt printed no progress for {second.seconds:.0f}s, twice "
                               "(it was killed both times). This is melt hanging, not a slow render; retry "
                               "the render, and if it keeps happening run it when the machine is less busy. "
                               "WVB_RENDER_STALL_SECONDS raises the limit for very heavy frames.")
                        logger.error(msg)
                        if log_path:
                            log_path.write_text(f"Command: {' '.join(cmd)}\nSTALLED twice after "
                                                f"{second.seconds:.0f}s without progress\n--- stderr ---\n"
                                                f"{second.stderr[-4000:]}\n", encoding="utf-8")
                        return _fail(msg, "render_stalled")
            else:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=timeout_seconds, env=env,
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

        if result.returncode == 0 and qt_display_failed(result.stderr):
            # melt exits 0 with titles drawn as "INVALID": never a success.
            logger.error("Render rejected: MLT's Qt module had no display")
            return _fail(f"{HEADLESS_MESSAGE} {HEADLESS_SUGGESTION}", "missing_dependency")

        if result.returncode == 0:
            duration, size = 0.0, 0
            if _command_override is None:
                try:
                    duration, size = verify_render_output(
                        Path(running_job.output_path),
                        expected_duration=(length[0] / length[1]) if length else None,
                        expect_audio=not profile.disable_audio,
                    )
                except (OSError, ValueError, RuntimeError) as exc:
                    if log_path:
                        with log_path.open("a", encoding="utf-8") as log:
                            log.write(f"\nOutput verification failed: {exc}\n")
                    return _fail(str(exc), "invalid_output")
            if on_progress is not None and not use_bindings and total_frames:
                # melt never prints 100 %; it is only true once the output verified.
                report(RenderProgress(frame=total_frames - 1, total_frames=total_frames,
                                      percent=100.0, engine="melt"))
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

    finally:
        if melt_profile is not None:
            melt_profile.unlink(missing_ok=True)


class RenderStalled(RuntimeError):
    """melt printed no progress for ``seconds``: it is stuck, not slow."""

    def __init__(self, cmd: list[str], seconds: float, stderr: str = "") -> None:
        super().__init__(f"melt printed no progress for {seconds:.0f}s")
        self.cmd, self.seconds, self.stderr = cmd, seconds, stderr


#: A melt render prints a progress line several times a second with
#: ``-progress2``. Under CPU contention melt 7.42 sometimes loads its plugins
#: and then renders nothing, forever (see ``adapters/mlt/engine._melt_frame``);
#: without a watchdog a stuck render held a job for the whole 30-minute timeout.
DEFAULT_STALL_SECONDS = 120.0


def _stall_seconds() -> float:
    try:
        return max(1.0, float(os.environ.get("WVB_RENDER_STALL_SECONDS", DEFAULT_STALL_SECONDS)))
    except ValueError:
        return DEFAULT_STALL_SECONDS


def _descendants(pid: int) -> list[int]:
    """Child processes of *pid*, recursively (Linux ``/proc``; empty elsewhere)."""
    children: dict[int, list[int]] = {}
    proc = Path("/proc")
    if not proc.is_dir():
        return []
    for entry in proc.iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        children.setdefault(int(fields[1]), []).append(int(entry.name))
    found, stack = [], [pid]
    while stack:
        for child in children.get(stack.pop(), []):
            found.append(child)
            stack.append(child)
    return found


def _kill_tree(process: subprocess.Popen) -> None:
    """Kill the render and everything it started, then reap it.

    The render stays in the caller's process group on purpose: a detached
    job is cancelled by signalling its whole group (``workspace/jobs``), and a
    render in a group of its own would escape that. So the tree is walked
    instead of signalling a group.
    """
    for pid in reversed(_descendants(process.pid)):
        try:
            os.kill(pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
    process.kill()
    process.wait()


def _run_render_process(
    cmd: list[str],
    timeout_seconds: float,
    on_chunk=None,
    *,
    env: dict | None = None,
    stall_seconds: float | None = None,
    progress_pattern: str = "Current Frame",
) -> subprocess.CompletedProcess:
    """Run a render command, streaming stderr to *on_chunk* as it arrives.

    Both pipes are drained on their own threads (MLT writes ~170 lines of
    registration noise; an unread pipe would deadlock it). stderr is read in
    chunks, not lines, so melt's ``\r``-ended progress is seen live. On the
    deadline, or when ``stall_seconds`` pass without a chunk containing
    ``progress_pattern``, the process and its descendants are killed and
    ``TimeoutExpired`` / :class:`RenderStalled` raised.
    """
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
    out_parts: list[str] = []
    err_parts: list[str] = []
    last_progress = [time.monotonic()]

    def chunks(stream):
        """Whatever bytes are available, decoded -- not a blocking read(4096): a text-mode
        read(n) waits for n characters, so progress would arrive in 4 KB lumps, not live."""
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while True:
            data = stream.read1(4096)
            if not data:
                tail = decoder.decode(b"", final=True)
                if tail:
                    yield tail
                return
            text = decoder.decode(data)
            if text:
                yield text

    def drain_stdout() -> None:
        for chunk in chunks(process.stdout):
            out_parts.append(chunk)

    def drain_stderr() -> None:
        for chunk in chunks(process.stderr):
            err_parts.append(chunk)
            if progress_pattern in chunk:
                last_progress[0] = time.monotonic()
            if on_chunk is not None:
                try:
                    on_chunk(chunk)
                except Exception as exc:  # noqa: BLE001 -- progress must not stop the drain
                    logger.debug("Render output callback failed: %s", exc)

    threads = [threading.Thread(target=drain_stdout, daemon=True),
               threading.Thread(target=drain_stderr, daemon=True)]
    for thread in threads:
        thread.start()
    deadline = time.monotonic() + timeout_seconds
    while True:
        now = time.monotonic()
        try:
            process.wait(timeout=max(0.0, min(0.5, deadline - now)))
            break
        except subprocess.TimeoutExpired:
            now = time.monotonic()
            stalled = stall_seconds is not None and now - last_progress[0] >= stall_seconds
            if now < deadline and not stalled:
                continue
            _kill_tree(process)
            for thread in threads:
                thread.join(5)
            if stalled and now < deadline:
                raise RenderStalled(cmd, stall_seconds, "".join(err_parts)) from None
            raise subprocess.TimeoutExpired(cmd, timeout_seconds) from None
    for thread in threads:
        thread.join()
    return subprocess.CompletedProcess(cmd, process.returncode, "".join(out_parts), "".join(err_parts))


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


def _write_melt_profile(project_path: Path, width: int, height: int) -> Path | None:
    """Write a temporary MLT profile: the render's size at the project's frame rate.

    ``melt -profile`` is the only way to size a render correctly. ``width=`` and
    ``height=`` consumer properties make melt render through its default profile,
    which pillarboxes the picture and shifts its colours. Combined with a project
    rate other than 25 fps they hang it outright, and melt has no real frame rate
    conversion, so the render keeps the project's rate.
    Returns None for a project with no readable ``<profile>``.
    """
    try:
        source = ET.parse(project_path).getroot().find("profile")
        rate_num, rate_den = int(source.get("frame_rate_num")), int(source.get("frame_rate_den"))
    except (ET.ParseError, OSError, AttributeError, TypeError, ValueError):
        return None
    divisor = gcd(width, height) or 1
    handle, name = tempfile.mkstemp(prefix="wvb-render-", suffix=".mltprofile")
    with os.fdopen(handle, "w", encoding="utf-8") as profile_file:
        profile_file.write(
            f"description=ForgeFrame render\nframe_rate_num={rate_num}\nframe_rate_den={rate_den}\n"
            f"width={width}\nheight={height}\nprogressive=1\nsample_aspect_num=1\nsample_aspect_den=1\n"
            f"display_aspect_num={width // divisor}\ndisplay_aspect_den={height // divisor}\n"
            f"colorspace={source.get('colorspace') or '709'}\n"
        )
    return Path(name)


def _with_melt_profile(cmd: list[str], profile_path: Path) -> list[str]:
    """Replace a melt command's size and rate properties with ``-profile``."""
    dropped = ("width=", "height=", "frame_rate_num=", "frame_rate_den=")
    kept = [token for token in cmd[1:] if not token.startswith(dropped)]
    return [cmd[0], "-profile", str(profile_path), *kept]


def _select_render_engine(project_path: Path) -> str:
    """Pick the engine for a project: ``mlt`` only when asked for, and only for .kdenlive."""
    from workshop_video_brain.edit_mcp.adapters.mlt import engine

    requested = os.environ.get("WVB_RENDER_ENGINE", "melt").strip().lower()
    if project_path.suffix.lower() != ".kdenlive":
        return "melt"
    if requested == "mlt" or (requested == "auto" and engine.find_mlt_python() is not None):
        return "mlt"
    return "melt"


def _melt_consumer_props(cmd: list[str]) -> dict[str, str]:
    """The ``key=value`` consumer properties of a melt command, so both engines get the same."""
    start = next(index for index, token in enumerate(cmd) if token.startswith("avformat:")) + 1
    return dict(token.split("=", 1) for token in cmd[start:] if "=" in token)


def _render_with_bindings(
    job: RenderJob,
    cmd: list[str],
    timeout_seconds: int,
    on_progress: ProgressCallback | None,
) -> subprocess.CompletedProcess:
    """Render through the MLT worker, shaped like the melt call it stands in for."""
    from workshop_video_brain.edit_mcp.adapters.mlt import engine

    def forward(event: dict) -> None:
        if on_progress is None or event.get("event") != "progress":
            return
        frame, total = int(event.get("frame", 0)), int(event.get("total", 0))
        percent = min(100.0, 100.0 * (frame + 1) / total) if total else 0.0
        on_progress(RenderProgress(frame=frame, total_frames=total, percent=percent, engine="mlt"))

    args = {"path": str(job.project_path), "out": str(job.output_path), "props": _melt_consumer_props(cmd)}
    try:
        _result, stderr = engine.run_streaming_worker("render", args, timeout=timeout_seconds, on_event=forward)
    except engine.MltWorkerError as exc:
        return subprocess.CompletedProcess(cmd, 1, "", f"{exc}\n{exc.stderr_tail}")
    except engine.MltUnavailable as exc:
        return subprocess.CompletedProcess(cmd, 1, "", str(exc))
    return subprocess.CompletedProcess(cmd, 0, "", stderr)


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
        # One progress report per line on stderr (``Current Frame: N, percentage: P``).
        "-progress2",
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


_AUDIO_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".aac", ".ogg", ".oga", ".opus"}


def verify_render_output(
    path: Path,
    *,
    expected_duration: float | None = None,
    expect_video: bool = True,
    expect_audio: bool | None = None,
) -> tuple[float, int]:
    """Require a nonempty, probeable artifact with a positive duration.

    Also, when asked: a video stream (skipped for audio containers), an audio
    stream, and a length no shorter than the timeline's -- a melt that stops
    early still exits 0 with a valid but truncated file.
    """
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
        streams = data.get("streams") or []
        if not streams or not 0 < duration < float("inf"):
            raise ValueError("Render output has no streams or positive finite duration")
    except (TypeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid ffprobe metadata for render output") from exc

    kinds = [stream.get("codec_type") for stream in streams]
    if expect_video and path.suffix.lower() not in _AUDIO_EXTENSIONS and "video" not in kinds:
        raise ValueError(f"Render output has no video stream: {path}")
    if expect_audio and "audio" not in kinds:
        raise ValueError(f"Render output has no audio stream: {path}")
    if expected_duration:
        video = next((s for s in streams if s.get("codec_type") == "video"), {})
        try:
            actual = float(video.get("duration") or duration)
        except (TypeError, ValueError):
            actual = duration
        fps = 25.0
        rate = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "")
        if "/" in rate:
            num, den = rate.split("/", 1)
            try:
                fps = float(num) / float(den) if float(den) else fps
            except ValueError:
                pass
        slack = max(2 / fps, 0.005 * expected_duration)
        if actual < expected_duration - slack:
            raise ValueError(
                f"Render is shorter than the timeline: {actual:.2f}s of "
                f"{expected_duration:.2f}s -- melt stopped early; see the log"
            )
        if actual > expected_duration + slack:
            logger.warning("Render is %.2fs, timeline %.2fs (longer is normal for audio padding)",
                           actual, expected_duration)
    return duration, size
