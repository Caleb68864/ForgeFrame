"""Frame-extraction adapter: exact, burst, and centered-burst extraction.

Built on :func:`run_ffmpeg`'s ``pre_input_args`` seek support. ``quality`` picks
the seek strategy:

* ``"high"`` -- accurate seek (``-ss`` placed *after* ``-i``, decoded frame-by-frame).
* ``"fast"`` -- inaccurate/keyframe seek (``-ss`` placed *before* ``-i`` via
  ``pre_input_args``), much faster but may land on the nearest keyframe.

VFR sources always force accurate seek regardless of the requested quality,
since keyframe-seek timestamps are unreliable when the frame rate varies.
"""
from __future__ import annotations

import logging
from pathlib import Path
from uuid import UUID

from workshop_video_brain.core.models.visual_research import FrameCandidate
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg

logger = logging.getLogger(__name__)


def _default_output_path(video_path: Path, timestamp_seconds: float, fmt: str) -> Path:
    stem = video_path.stem
    ts_tag = f"{timestamp_seconds:.3f}".replace(".", "_")
    return video_path.parent / f"{stem}_frame_{ts_tag}.{fmt}"


def extract_frame(
    video_path: Path,
    timestamp_seconds: float,
    output_path: Path | None = None,
    quality: str = "high",
    fmt: str = "png",
) -> FrameCandidate:
    """Extract a single frame from *video_path* at *timestamp_seconds*.

    ``quality="high"`` uses accurate (post-``-i``) seek; ``quality="fast"``
    uses a pre-input (keyframe) seek via ``pre_input_args``. VFR sources
    always force accurate seek and set a ``vfr_warning`` on the candidate.
    """
    video_path = Path(video_path)
    if output_path is None:
        output_path = _default_output_path(video_path, timestamp_seconds, fmt)
    else:
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata: dict = {}
    vfr_warning: str | None = None
    try:
        asset = probe_media(video_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not probe %s for VFR detection: %s", video_path, exc)
        asset = None

    effective_quality = quality
    if asset is not None and asset.is_vfr:
        vfr_warning = (
            "Source probes as variable frame rate; forcing accurate seek "
            "regardless of requested quality."
        )
        effective_quality = "high"

    pre_input_args: list[str] | None = None
    ffmpeg_args = ["-frames:v", "1"]
    if effective_quality == "fast":
        pre_input_args = ["-ss", str(timestamp_seconds)]
    else:
        ffmpeg_args = ["-ss", str(timestamp_seconds)] + ffmpeg_args

    result = run_ffmpeg(
        ffmpeg_args,
        video_path,
        output_path,
        overwrite=True,
        pre_input_args=pre_input_args,
    )

    if not result.success:
        if output_path.exists():
            output_path.unlink(missing_ok=True)
        raise RuntimeError(
            f"ffmpeg frame extraction failed for {video_path} @ {timestamp_seconds}s: "
            f"{result.stderr[-500:]}"
        )

    width = asset.width if asset is not None else 0
    height = asset.height if asset is not None else 0
    try:
        probed_frame = probe_media(output_path)
        if probed_frame.width:
            width = probed_frame.width
        if probed_frame.height:
            height = probed_frame.height
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not probe extracted frame %s: %s", output_path, exc)

    if vfr_warning:
        metadata["vfr_warning"] = vfr_warning

    return FrameCandidate(
        source_id=UUID(int=0),
        timestamp_seconds=timestamp_seconds,
        image_path=str(output_path),
        width=width,
        height=height,
        extraction_method="exact_timestamp",
        metadata=metadata,
    )


def extract_frame_burst(
    video_path: Path,
    start_seconds: float,
    end_seconds: float,
    interval_seconds: float = 0.5,
    max_frames: int = 20,
) -> list[FrameCandidate]:
    """Extract frames uniformly across ``[start_seconds, end_seconds]``.

    Widens ``interval_seconds`` (evenly) if the naive count would exceed
    ``max_frames``. Timestamps are deduplicated and returned chronologically.
    """
    video_path = Path(video_path)
    if end_seconds < start_seconds:
        start_seconds, end_seconds = end_seconds, start_seconds

    span = end_seconds - start_seconds
    if span <= 0:
        timestamps = [start_seconds]
    else:
        count = int(span / interval_seconds) + 1
        if count > max_frames:
            interval_seconds = span / (max_frames - 1) if max_frames > 1 else span
            count = max_frames
        timestamps = [start_seconds + i * interval_seconds for i in range(count)]
        timestamps = [t for t in timestamps if t <= end_seconds + 1e-9]
        if not timestamps or timestamps[-1] < end_seconds - 1e-9:
            timestamps.append(end_seconds)

    deduped: list[float] = []
    seen: set[float] = set()
    for t in sorted(timestamps):
        key = round(t, 6)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(t)
    deduped = deduped[:max_frames]

    candidates: list[FrameCandidate] = []
    for t in deduped:
        candidate = extract_frame(video_path, t, quality="fast")
        candidate.extraction_method = "uniform_burst"
        candidates.append(candidate)

    candidates.sort(key=lambda c: c.timestamp_seconds)
    return candidates


def extract_centered_burst(
    video_path: Path,
    anchor_seconds: float,
    before_seconds: float = 3,
    after_seconds: float = 5,
    interval_seconds: float = 0.5,
) -> list[FrameCandidate]:
    """Extract a uniform burst of frames centered on ``anchor_seconds``."""
    start_seconds = max(0.0, anchor_seconds - before_seconds)
    end_seconds = anchor_seconds + after_seconds
    return extract_frame_burst(
        video_path,
        start_seconds,
        end_seconds,
        interval_seconds=interval_seconds,
    )
