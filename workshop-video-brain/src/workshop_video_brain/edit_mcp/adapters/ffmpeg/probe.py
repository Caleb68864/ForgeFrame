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

logger = logging.getLogger(__name__)

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
        subprocess.CalledProcessError: if ffprobe fails.
        json.JSONDecodeError: if ffprobe output is not valid JSON.
    """
    path = Path(path)

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
    )

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

    Per-file errors are logged as warnings; the scan continues.

    Args:
        dir: Directory to scan.
        extensions: File extensions to match (include the dot, e.g. ``".mp4"``).
                    Defaults to :data:`DEFAULT_EXTENSIONS`.

    Returns:
        List of successfully probed :class:`MediaAsset` objects.
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
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to probe %s: %s", path, exc)

    return assets


@dataclass
class LoudnessResult:
    """Loudness measurement result."""
    input_i: float    # Integrated loudness (LUFS)
    input_tp: float   # True peak (dBTP)
    input_lra: float  # Loudness range (LU)


def measure_loudness(path: Path) -> LoudnessResult | None:
    """Measure integrated loudness, true peak, and loudness range using FFmpeg loudnorm filter.

    Returns LoudnessResult with input_i (LUFS), input_tp (dBTP), input_lra (LU).
    Returns None on failure.
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
        # loudnorm JSON is in stderr
        match = re.search(r'\{[^}]*"input_i"[^}]*\}', result.stderr, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return LoudnessResult(
                input_i=float(data.get("input_i", 0)),
                input_tp=float(data.get("input_tp", 0)),
                input_lra=float(data.get("input_lra", 0)),
            )
        return None
    except Exception:
        logger.warning("Loudness measurement failed for %s", path)
        return None
