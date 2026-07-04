"""FFprobe adapter: probe media files and scan directories."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from workshop_video_brain.core.models import MediaAsset
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import (
    FFmpegCommandError,
    FFmpegNotFound,
    FFmpegTimeout,
    _FFMPEG_INSTALL_HINT,
    _stderr_tail,
)

logger = logging.getLogger(__name__)

# A probe should be near-instant; this only guards against a wedged ffprobe.
_PROBE_TIMEOUT_SECONDS = 120.0

DEFAULT_EXTENSIONS: set[str] = {
    ".mp4", ".mkv", ".mov", ".avi", ".webm",
    ".mts", ".m2ts", ".mp3", ".wav", ".flac",
}


def _parse_frame_rate(rate_str: str) -> float:
    """Parse 'num/den' frame rate string to float."""
    try:
        num, den = rate_str.split("/")
        return int(num) / int(den) if int(den) != 0 else 0.0
    except (ValueError, ZeroDivisionError):
        return 0.0


def probe_media(path: Path) -> MediaAsset:
    """Run ffprobe on *path* and return a populated MediaAsset.

    Raises:
        FileNotFoundError: if *path* does not exist.
        FFmpegNotFound: if the ffprobe binary is missing (carries install hint).
        FFmpegTimeout: if ffprobe hangs past the probe timeout.
        FFmpegCommandError: if ffprobe exits nonzero (carries the stderr tail).
        json.JSONDecodeError: if ffprobe output is not valid JSON.
    """
    path = Path(path)

    if not path.exists():
        raise FileNotFoundError(f"Media file does not exist: {path}")

    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-print_format", "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=_PROBE_TIMEOUT_SECONDS,
        )
    except FileNotFoundError as exc:
        raise FFmpegNotFound(
            f"ffprobe binary not found on PATH (probing {path}). "
            f"{_FFMPEG_INSTALL_HINT}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise FFmpegTimeout(
            f"ffprobe timed out after {_PROBE_TIMEOUT_SECONDS:.0f}s on {path}."
        ) from exc
    except subprocess.CalledProcessError as exc:
        raise FFmpegCommandError(
            f"ffprobe failed (rc={exc.returncode}) on {path}.\n"
            f"stderr tail:\n{_stderr_tail(exc.stderr or '')}"
        ) from exc

    data = json.loads(result.stdout)
    fmt = data.get("format", {})
    streams = data.get("streams", [])

    # Separate video and audio streams
    video_stream = next(
        (s for s in streams if s.get("codec_type") == "video"), {}
    )
    audio_stream = next(
        (s for s in streams if s.get("codec_type") == "audio"), {}
    )

    # Duration: prefer format-level, fall back to video stream
    duration = float(fmt.get("duration") or video_stream.get("duration") or 0.0)

    # FPS from r_frame_rate (e.g. "25/1")
    fps = 0.0
    r_frame_rate = video_stream.get("r_frame_rate", "0/1")
    try:
        num, den = r_frame_rate.split("/")
        if int(den) > 0:
            fps = float(int(num) / int(den))
    except (ValueError, ZeroDivisionError):
        pass

    # VFR detection: compare r_frame_rate vs avg_frame_rate
    avg_frame_rate = video_stream.get("avg_frame_rate", "0/1")
    r_fps = _parse_frame_rate(r_frame_rate)
    avg_fps = _parse_frame_rate(avg_frame_rate)
    is_vfr = False
    if r_fps > 0 and avg_fps > 0:
        divergence = abs(r_fps - avg_fps) / max(r_fps, avg_fps)
        is_vfr = divergence > 0.05

    # Color metadata
    color_space = video_stream.get("color_space")
    color_primaries = video_stream.get("color_primaries")
    color_transfer = video_stream.get("color_transfer")

    # Bitrate in bits/s
    bitrate = int(fmt.get("bit_rate") or 0)

    # File size
    file_size = int(fmt.get("size") or path.stat().st_size)

    # Container / format name
    container = fmt.get("format_name", "").split(",")[0]

    # Media type determination
    if video_stream:
        media_type = "video"
    elif audio_stream:
        media_type = "audio"
    else:
        media_type = "unknown"

    # Fingerprint: MD5 of first 64 KB
    file_hash = ""
    try:
        with open(path, "rb") as fh:
            chunk = fh.read(65536)
        file_hash = hashlib.md5(chunk).hexdigest()
    except OSError as exc:
        logger.warning("Could not compute hash for %s: %s", path, exc)

    # Channels
    channels = int(audio_stream.get("channels") or 0)

    # Sample rate
    sample_rate = int(audio_stream.get("sample_rate") or 0)

    return MediaAsset(
        path=str(path),
        media_type=media_type,
        container=container,
        video_codec=video_stream.get("codec_name", ""),
        audio_codec=audio_stream.get("codec_name", ""),
        duration=duration,
        duration_seconds=duration,
        fps=fps,
        width=int(video_stream.get("width") or 0),
        height=int(video_stream.get("height") or 0),
        channels=channels,
        sample_rate=sample_rate,
        bitrate=bitrate,
        file_size=file_size,
        file_size_bytes=file_size,
        hash=file_hash,
        is_vfr=is_vfr,
        color_space=color_space,
        color_primaries=color_primaries,
        color_transfer=color_transfer,
    )


def scan_directory(
    dir: Path,
    extensions: set[str] | None = None,
) -> list[MediaAsset]:
    """Recursively scan *dir* for media files and probe each one.

    Per-file probe errors (corrupt/unreadable media) are logged as warnings and
    the scan continues -- this is a deliberate best-effort scan. A *missing
    ffprobe binary* is an environment error, not a per-file problem, so it is
    re-raised loudly instead of being swallowed for every file.

    Args:
        dir: Directory to scan.
        extensions: File extensions to match (include the dot, e.g. ``".mp4"``).
                    Defaults to :data:`DEFAULT_EXTENSIONS`.

    Returns:
        List of successfully probed :class:`MediaAsset` objects.

    Raises:
        FFmpegNotFound: if the ffprobe binary is missing.
    """
    if extensions is None:
        extensions = DEFAULT_EXTENSIONS

    dir = Path(dir)
    assets: list[MediaAsset] = []

    for path in dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in extensions:
            continue
        try:
            asset = probe_media(path)
            assets.append(asset)
        except (FFmpegNotFound, FFmpegTimeout):
            # Environment/hang failures are not per-file; don't bury them.
            raise
        except Exception as exc:  # noqa: BLE001 -- best-effort per-file skip
            logger.warning("Failed to probe %s: %s", path, exc)

    return assets


def probe_duration_seconds(media_path: Path) -> float | None:
    """Best-effort media duration in seconds via ffprobe (None if unavailable).

    Prefers the video stream's ``duration`` and falls back to the container
    ``format.duration``. Returns ``None`` (never raises) if ffprobe is missing,
    exits nonzero, times out, or the output cannot be parsed. Shared by
    placement/multicam bundles that only need a rough length and treat missing
    duration as "unknown".
    """
    import shutil

    if not shutil.which("ffprobe"):
        return None
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(media_path),
            ],
            capture_output=True, text=True, timeout=30,
        )
        if proc.returncode != 0:
            return None
        data = json.loads(proc.stdout or "{}")
        for stream in data.get("streams", []):
            if stream.get("codec_type") == "video" and stream.get("duration"):
                return float(stream["duration"])
        dur = data.get("format", {}).get("duration")
        return float(dur) if dur else None
    except Exception:  # noqa: BLE001 -- documented best-effort: None on any failure
        return None


def probe_format_duration(path: Path, *, log_label: str = "duration probe") -> float | None:
    """Best-effort ``format=duration`` probe that logs loudly on failure.

    Unlike :func:`probe_duration_seconds`, a missing/corrupt file is logged (at
    WARNING, prefixed with *log_label*) so a ``None`` is never silently
    indistinguishable from a real zero-duration file. Returns ``None`` on any
    failure. Shared by the dupe-scan and slideshow bundles.
    """
    if not Path(path).exists():
        logger.warning("%s: file missing: %s", log_label, path)
        return None
    try:
        out = subprocess.run(
            [
                "ffprobe", "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True, text=True, check=False,
        )
    except FileNotFoundError:
        logger.warning("%s: ffprobe binary not on PATH", log_label)
        return None
    except OSError as exc:
        logger.warning("%s: ffprobe failed on %s: %s", log_label, path, exc)
        return None
    if out.returncode != 0:
        logger.warning(
            "%s: ffprobe exited %d on %s: %s",
            log_label, out.returncode, path, out.stderr.strip()[-200:],
        )
        return None
    text = out.stdout.strip()
    try:
        return float(text)
    except ValueError:
        logger.warning("%s: unparseable duration %r for %s", log_label, text, path)
        return None


@dataclass
class LoudnessResult:
    """Loudness measurement result."""
    input_i: float    # Integrated loudness (LUFS)
    input_tp: float   # True peak (dBTP)
    input_lra: float  # Loudness range (LU)


def measure_loudness(path: Path) -> LoudnessResult | None:
    """Measure integrated loudness, true peak, and loudness range using FFmpeg loudnorm filter.

    Returns LoudnessResult with input_i (LUFS), input_tp (dBTP), input_lra (LU).

    Best-effort: returns ``None`` (with a WARNING naming the path and cause) if
    ffmpeg is missing, times out, or the loudnorm JSON cannot be parsed. Callers
    treat ``None`` as "loudness unknown" rather than a hard failure.
    """
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-i", str(path),
                "-af", "loudnorm=print_format=json",
                "-f", "null", "-"
            ],
            capture_output=True,
            text=True,
            timeout=120,
        )
    except FileNotFoundError:
        logger.warning(
            "Loudness measurement skipped for %s: ffmpeg not found on PATH", path
        )
        return None
    except subprocess.TimeoutExpired:
        logger.warning("Loudness measurement timed out (120s) for %s", path)
        return None
    except Exception as exc:  # noqa: BLE001 -- documented best-effort: None on any failure
        logger.warning("Loudness measurement failed for %s: %s", path, exc)
        return None

    # loudnorm JSON is in stderr
    match = re.search(r'\{[^}]*"input_i"[^}]*\}', result.stderr, re.DOTALL)
    if not match:
        logger.warning(
            "Loudness measurement failed for %s: no loudnorm JSON in ffmpeg "
            "output (rc=%d)", path, result.returncode
        )
        return None
    try:
        data = json.loads(match.group())
        return LoudnessResult(
            input_i=float(data.get("input_i", 0)),
            input_tp=float(data.get("input_tp", 0)),
            input_lra=float(data.get("input_lra", 0)),
        )
    except (ValueError, json.JSONDecodeError) as exc:
        logger.warning(
            "Loudness measurement failed for %s: unparseable loudnorm data (%s)",
            path, exc,
        )
        return None
