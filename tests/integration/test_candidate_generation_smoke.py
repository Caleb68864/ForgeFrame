"""Adaptive candidate-generation smoke tests.

Exercises ``workshop_video_brain.edit_mcp.pipelines.visual_research.candidates``
against ``tests/fixtures/media_generated/greenscreen_reporter_720.mp4``.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from workshop_video_brain.core.models.media import MediaAsset
from workshop_video_brain.core.models.visual_research import (
    ResearchConfig,
    ResearchRegion,
)
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.pipelines.visual_research.candidates import (
    generate_candidates,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURES = REPO_ROOT / "tests" / "fixtures" / "media_generated"
VIDEO_CLIP = FIXTURES / "greenscreen_reporter_720.mp4"


def _require(path: Path) -> None:
    if not path.exists():
        pytest.skip(f"Fixture not available: {path}")


def _source(duration_seconds: float) -> MediaAsset:
    return MediaAsset(
        path=str(VIDEO_CLIP),
        media_type="video",
        duration_seconds=duration_seconds,
    )


def test_generate_candidates_respects_cap_and_includes_uniform_burst(tmp_path):
    _require(VIDEO_CLIP)
    duration = probe_media(VIDEO_CLIP).duration_seconds

    config = ResearchConfig()
    region = ResearchRegion(
        source_id=(source := _source(duration)).id,
        start_seconds=0.0,
        end_seconds=min(duration, 3.0),
        anchor_seconds=min(duration, 1.0),
    )

    candidates = generate_candidates(VIDEO_CLIP, region, source, config)

    assert len(candidates) > 0
    assert len(candidates) <= config.candidate_generation.max_candidates_per_region
    methods = {c.extraction_method for c in candidates}
    assert "uniform_burst" in methods
    for candidate in candidates:
        assert region.start_seconds - 1e-6 <= candidate.timestamp_seconds <= region.end_seconds + 1e-6
        assert candidate.source_id == source.id
        assert candidate.region_id == region.region_id


def test_generate_candidates_static_region_falls_back_to_periodic_scene_sampling(tmp_path):
    _require(VIDEO_CLIP)
    duration = probe_media(VIDEO_CLIP).duration_seconds

    config = ResearchConfig()
    region = ResearchRegion(
        source_id=(source := _source(duration)).id,
        start_seconds=0.0,
        end_seconds=min(duration, 1.5),
        anchor_seconds=0.0,
    )

    candidates = generate_candidates(VIDEO_CLIP, region, source, config)

    assert len(candidates) > 0
    methods = {c.extraction_method for c in candidates}
    assert methods & {"scene_change", "uniform_burst", "exact_timestamp"}


def test_generate_candidates_returns_deduplicated_timestamps(tmp_path):
    _require(VIDEO_CLIP)
    duration = probe_media(VIDEO_CLIP).duration_seconds

    config = ResearchConfig()
    region = ResearchRegion(
        source_id=(source := _source(duration)).id,
        start_seconds=0.0,
        end_seconds=min(duration, 2.0),
        anchor_seconds=0.5,
    )

    candidates = generate_candidates(VIDEO_CLIP, region, source, config)

    rounded_timestamps = [round(c.timestamp_seconds, 3) for c in candidates]
    assert len(rounded_timestamps) == len(set(rounded_timestamps))
