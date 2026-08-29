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

from workshop_video_brain.core.models.media import MediaAsset
from workshop_video_brain.core.models.visual_research import FrameCandidate
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg

logger = logging.getLogger(__name__)


def _default_output_path(
    video_path: Path,
    timestamp_seconds: float,
    fmt: str,
    output_dir: Path | None = None,
) -> Path:
    """``<output_dir or video_path.parent>/<stem>_frame_<ts>.<fmt>``.

    Callers that extract *scratch* frames (bursts, candidate generation) must
    pass ``output_dir`` -- the beside-the-source default exists for the
    explicit single-frame CLI/tool case only. Writing scratch PNGs next to a
    user's source video pollutes ``media/raw/`` (a protected tree) and makes
    two concurrent runs on the same file race on identical filenames.
    """
    stem = video_path.stem
    ts_tag = f"{timestamp_seconds:.3f}".replace(".", "_")
    base = Path(output_dir) if output_dir is not None else video_path.parent
    return base / f"{stem}_frame_{ts_tag}.{fmt}"


def _probe_once(video_path: Path, asset: MediaAsset | None) -> MediaAsset | None:
    """Return *asset* if usable, else probe *video_path* once (None on failure)."""
    if asset is not None:
        return asset
    try:
        return probe_media(video_path)
    except Exception as exc:  # noqa: BLE001 -- extract_frame degrades gracefully
        logger.warning("Could not probe %s: %s", video_path, exc)
        return None


def extract_frame(
    video_path: Path,
    timestamp_seconds: float,
    output_path: Path | None = None,
    quality: str = "high",
    fmt: str = "png",
    output_dir: Path | None = None,
    asset: MediaAsset | None = None,
) -> FrameCandidate:
    """Extract a single frame from *video_path* at *timestamp_seconds*.

    ``output_path`` names the file exactly; otherwise the frame is written to
    ``output_dir`` (or, when that is also omitted, beside the source video --
    see :func:`_default_output_path`).

    ``asset`` is the already-probed source (for VFR detection and frame
    dimensions). Bursts and candidate generation probe once and pass it down;
    without it every frame costs two extra ffprobe spawns.

    ``quality="high"`` uses accurate (post-``-i``) seek; ``quality="fast"``
    uses a pre-input (keyframe) seek via ``pre_input_args``. VFR sources
    always force accurate seek and set a ``vfr_warning`` on the candidate.
    """
    video_path = Path(video_path)
    if output_path is None:
        output_path = _default_output_path(video_path, timestamp_seconds, fmt, output_dir)
    else:
        output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    metadata: dict = {}
    vfr_warning: str | None = None
    if asset is None:
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
    if not (width and height):
        # No scale filter is applied, so the frame has the source's coded
        # dimensions; only probe the PNG when the source probe lacked them.
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
    output_dir: Path | None = None,
    asset: MediaAsset | None = None,
) -> list[FrameCandidate]:
    """Extract frames uniformly across ``[start_seconds, end_seconds]``.

    Widens ``interval_seconds`` (evenly) if the naive count would exceed
    ``max_frames``. Timestamps are deduplicated and returned chronologically.
    Frames land in ``output_dir`` when given (pipelines must pass one; see
    :func:`_default_output_path`).
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

    asset = _probe_once(video_path, asset)
    candidates: list[FrameCandidate] = []
    for t in deduped:
        candidate = extract_frame(
            video_path, t, quality="fast", output_dir=output_dir, asset=asset
        )
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
    output_dir: Path | None = None,
    asset: MediaAsset | None = None,
) -> list[FrameCandidate]:
    """Extract a uniform burst of frames centered on ``anchor_seconds``."""
    start_seconds = max(0.0, anchor_seconds - before_seconds)
    end_seconds = anchor_seconds + after_seconds
    return extract_frame_burst(
        video_path,
        start_seconds,
        end_seconds,
        interval_seconds=interval_seconds,
        output_dir=output_dir,
        asset=asset,
    )
