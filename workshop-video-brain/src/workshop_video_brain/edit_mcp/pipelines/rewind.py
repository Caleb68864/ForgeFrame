"""Pure helpers for the VHS rewind effect (``effect_rewind``).

No I/O lives here: this module only does deterministic string / number work --
output filename construction, segment + duration math, and the ffmpeg
filtergraph / argument construction used to render a *reversed* copy of a clip
segment. All side effects (running ffmpeg, snapshotting, patching the project)
live in the bundle module ``edit_mcp/server/bundles/rewind.py``.

The reverse route is the reliable one described in the improvement plan: MLT has
no working timewarp/reverse producer through this integration, so we render the
segment reversed with ffmpeg (``reverse`` / ``areverse``) into ``media/processed``
and insert that as a new producer -- fully additive, never touching originals.
"""
from __future__ import annotations

import re

DEFAULT_SPEED = 2.0

# ffmpeg's atempo filter only accepts a tempo factor in [0.5, 2.0], so speeds
# outside that range are expressed as a chain of atempo filters whose product is
# the requested speed.
_ATEMPO_MAX = 2.0
_ATEMPO_MIN = 0.5
_EPS = 1e-9


def _fmt(value: float) -> str:
    """Format a float for use inside an ffmpeg filter (no trailing zeros)."""
    text = f"{float(value):.6f}".rstrip("0").rstrip(".")
    return text or "0"


def _tag(value: float) -> str:
    """Format a number for use inside a filename (``1.5`` -> ``1p5``)."""
    return _fmt(value).replace(".", "p").replace("-", "m")


def segment_duration(start_seconds: float, end_seconds: float) -> float:
    """Duration of the ``[start, end]`` window in seconds.

    Raises:
        ValueError: if the window is empty or inverted, or start is negative.
    """
    start = float(start_seconds)
    end = float(end_seconds)
    if start < 0:
        raise ValueError(f"start_seconds must be >= 0 (got {start})")
    if end <= start:
        raise ValueError(
            f"end_seconds ({end}) must be greater than start_seconds ({start})"
        )
    return end - start


def _validate_speed(speed: float) -> float:
    s = float(speed)
    if s <= 0:
        raise ValueError(f"speed must be > 0 (got {s})")
    return s


def reversed_duration(start_seconds: float, end_seconds: float, speed: float) -> float:
    """Expected duration (seconds) of the reversed, sped-up segment."""
    seg = segment_duration(start_seconds, end_seconds)
    return seg / _validate_speed(speed)


def reversed_frame_count(
    start_seconds: float, end_seconds: float, speed: float, fps: float
) -> int:
    """Expected frame count of the reversed clip at ``fps`` (>= 1)."""
    if fps <= 0:
        raise ValueError(f"fps must be > 0 (got {fps})")
    frames = round(reversed_duration(start_seconds, end_seconds, speed) * float(fps))
    return max(1, int(frames))


def atempo_factors(speed: float) -> list[float]:
    """Decompose ``speed`` into atempo factors, each within [0.5, 2.0].

    The product of the returned factors equals ``speed``.
    """
    remaining = _validate_speed(speed)
    factors: list[float] = []
    while remaining > _ATEMPO_MAX + _EPS:
        factors.append(_ATEMPO_MAX)
        remaining /= _ATEMPO_MAX
    while remaining < _ATEMPO_MIN - _EPS:
        factors.append(_ATEMPO_MIN)
        remaining /= _ATEMPO_MIN
    factors.append(remaining)
    return factors


def atempo_chain(speed: float) -> list[str]:
    """atempo filter strings (e.g. ``["atempo=2", "atempo=1.5"]``) for ``speed``."""
    return [f"atempo={_fmt(f)}" for f in atempo_factors(speed)]


def build_video_filter(start_seconds: float, end_seconds: float, speed: float) -> str:
    """Video filtergraph: trim the window, reverse it, then apply the speed-up.

    The trim happens *before* ``reverse`` so only the requested segment is
    buffered/reversed (reverse loads its whole input into memory).
    """
    segment_duration(start_seconds, end_seconds)
    speed = _validate_speed(speed)
    return (
        f"trim=start={_fmt(start_seconds)}:end={_fmt(end_seconds)},"
        "setpts=PTS-STARTPTS,"
        "reverse,"
        f"setpts=PTS/{_fmt(speed)}"
    )


def build_audio_filter(start_seconds: float, end_seconds: float, speed: float) -> str:
    """Audio filtergraph mirroring :func:`build_video_filter` (atrim/areverse)."""
    segment_duration(start_seconds, end_seconds)
    chain = ",".join(atempo_chain(speed))
    return (
        f"atrim=start={_fmt(start_seconds)}:end={_fmt(end_seconds)},"
        "asetpts=PTS-STARTPTS,"
        "areverse,"
        f"{chain}"
    )


def build_reverse_args(
    start_seconds: float,
    end_seconds: float,
    speed: float = DEFAULT_SPEED,
    include_audio: bool = True,
) -> list[str]:
    """ffmpeg args (between ``-i input`` and ``output``) to reverse a segment.

    Compatible with :func:`workshop_video_brain.edit_mcp.adapters.ffmpeg.runner.run_ffmpeg`.
    When ``include_audio`` is False, audio is dropped (``-an``) so sources with no
    audio stream do not error.
    """
    args = ["-vf", build_video_filter(start_seconds, end_seconds, speed)]
    if include_audio:
        args += ["-af", build_audio_filter(start_seconds, end_seconds, speed)]
    else:
        args += ["-an"]
    return args


def reversed_clip_name(
    source_stem: str,
    start_seconds: float,
    end_seconds: float,
    speed: float,
    suffix: str = ".mp4",
) -> str:
    """Deterministic output filename for the reversed segment.

    Safe for a filesystem (non ``[A-Za-z0-9._-]`` characters become ``_``) and
    encodes the segment + speed so distinct requests never collide.
    """
    segment_duration(start_seconds, end_seconds)
    _validate_speed(speed)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", source_stem) or "clip"
    tag = f"{_tag(start_seconds)}-{_tag(end_seconds)}_x{_tag(speed)}"
    return f"{safe}_rewind_{tag}{suffix}"
