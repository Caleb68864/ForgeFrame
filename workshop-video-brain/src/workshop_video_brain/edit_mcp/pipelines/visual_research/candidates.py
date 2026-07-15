"""Adaptive frame-candidate generation for a single :class:`ResearchRegion`.

Combines three extraction strategies into one capped, deduplicated
``FrameCandidate`` list per region:

1. **Anchor** -- a single ``exact_timestamp`` frame at ``region.anchor_seconds``
   (or the region midpoint when no anchor is set).
2. **Uniform burst** -- :func:`extract_frame_burst` across the region span,
   tagged ``uniform_burst``.
3. **Scene change** -- :func:`detect_scene_changes` within the region span,
   with a frame extracted at each detected timestamp via :func:`extract_frame`,
   tagged ``scene_change``. When the source is static (no real scene changes),
   ``detect_scene_changes`` itself falls back to bounded uniform sampling, so
   this stage still yields candidates.

Candidates are merged in anchor -> uniform_burst -> scene_change order,
deduplicated by rounded timestamp (first occurrence wins), and capped at
``config.candidate_generation.max_candidates_per_region``.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.core.models.media import MediaAsset
from workshop_video_brain.core.models.visual_research import (
    FrameCandidate,
    ResearchConfig,
    ResearchRegion,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.frames import (
    extract_frame,
    extract_frame_burst,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.scene import detect_scene_changes

_TIMESTAMP_DEDUPE_PRECISION = 3


def generate_candidates(
    video_path: Path,
    region: ResearchRegion,
    source: MediaAsset,
    config: ResearchConfig,
) -> list[FrameCandidate]:
    """Generate a capped, deduplicated candidate list for ``region``.

    Merges an anchor frame, a uniform burst, and scene-change frames (which
    fall back to periodic sampling on a static source), then dedupes by
    rounded timestamp and caps at
    ``config.candidate_generation.max_candidates_per_region``.
    """
    video_path = Path(video_path)
    gen_config = config.candidate_generation
    max_candidates = gen_config.max_candidates_per_region

    raw: list[FrameCandidate] = []

    anchor_seconds = region.anchor_seconds
    if anchor_seconds is None:
        anchor_seconds = (region.start_seconds + region.end_seconds) / 2.0
    anchor_seconds = max(region.start_seconds, min(region.end_seconds, anchor_seconds))
    anchor_candidate = extract_frame(video_path, anchor_seconds, quality="high")
    anchor_candidate.extraction_method = "exact_timestamp"
    raw.append(anchor_candidate)

    burst_candidates = extract_frame_burst(
        video_path,
        region.start_seconds,
        region.end_seconds,
        interval_seconds=gen_config.burst_spacing_seconds,
        max_frames=gen_config.burst_count,
    )
    raw.extend(burst_candidates)

    scene_changes = detect_scene_changes(
        video_path,
        start_seconds=region.start_seconds,
        end_seconds=region.end_seconds,
    )
    for change in scene_changes:
        scene_candidate = extract_frame(video_path, change.timestamp_seconds, quality="fast")
        scene_candidate.extraction_method = "scene_change"
        scene_candidate.metadata["scene_score"] = change.score
        raw.append(scene_candidate)

    deduped: list[FrameCandidate] = []
    seen_timestamps: set[float] = set()
    for candidate in raw:
        key = round(candidate.timestamp_seconds, _TIMESTAMP_DEDUPE_PRECISION)
        if key in seen_timestamps:
            continue
        seen_timestamps.add(key)
        candidate.source_id = source.id
        candidate.region_id = region.region_id
        deduped.append(candidate)

    deduped.sort(key=lambda c: c.timestamp_seconds)
    return deduped[:max_candidates]
