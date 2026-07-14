"""Unit tests for visual-research domain models."""
from __future__ import annotations

from workshop_video_brain.core.models import (
    FrameCandidate,
    FrameEvaluation,
    FrameVisualMetrics,
    MediaAsset,
    ResearchCapture,
    ResearchConfig,
    ResearchManifest,
    ResearchQuery,
    ResearchRegion,
    SceneChange,
    TranscriptSegment,
)


def test_research_config_defaults_construct():
    config = ResearchConfig()
    assert config.windowing.window_seconds == 10.0
    assert config.candidate_generation.max_candidates_per_region == 20
    assert config.scene_detection.threshold == 0.3
    assert config.quality.min_sharpness == 0.0
    assert config.deduplication.enabled is True
    assert config.ocr.enabled is False
    assert config.vision.enabled is False
    assert config.export.image_format == "jpg"


def test_frame_candidate_extraction_method_constrained():
    asset = MediaAsset(path="/tmp/video.mp4")
    candidate = FrameCandidate(
        source_id=asset.id,
        timestamp_seconds=1.5,
        image_path="/tmp/frame.jpg",
        extraction_method="scene_change",
        metrics=FrameVisualMetrics(sharpness=0.9),
    )
    assert candidate.extraction_method == "scene_change"
    assert candidate.region_id is None
    assert candidate.metrics.sharpness == 0.9


def test_transcript_segment_additive_fields_default():
    segment = TranscriptSegment(start_seconds=0.0, end_seconds=1.0, text="hello")
    assert segment.segment_id is None
    assert segment.speaker is None
    assert segment.tags == []
    assert segment.metadata == {}


def test_transcript_segment_additive_fields_populated():
    segment = TranscriptSegment(
        start_seconds=0.0,
        end_seconds=1.0,
        text="hello",
        segment_id="seg-1",
        speaker="host",
        tags=["intro"],
        metadata={"source": "test"},
    )
    assert segment.segment_id == "seg-1"
    assert segment.speaker == "host"
    assert segment.tags == ["intro"]
    assert segment.metadata == {"source": "test"}


def test_research_manifest_round_trips_through_serializable_mixin():
    asset = MediaAsset(path="/tmp/video.mp4")
    region = ResearchRegion(
        source_id=asset.id,
        start_seconds=0.0,
        end_seconds=10.0,
        label="intro",
    )
    candidate = FrameCandidate(
        source_id=asset.id,
        region_id=region.region_id,
        timestamp_seconds=2.0,
        image_path="/tmp/frame.jpg",
        width=1920,
        height=1080,
    )
    capture = ResearchCapture(
        region_id=region.region_id,
        source_id=asset.id,
        candidates=[candidate],
    )
    manifest = ResearchManifest(
        source=asset,
        regions=[region],
        captures=[capture],
    )

    roundtripped = ResearchManifest.from_json(manifest.to_json())

    assert roundtripped.manifest_id == manifest.manifest_id
    assert roundtripped.source.id == asset.id
    assert roundtripped.source.path == asset.path
    assert len(roundtripped.regions) == 1
    assert roundtripped.regions[0].region_id == region.region_id
    assert len(roundtripped.captures) == 1
    assert roundtripped.captures[0].candidates[0].candidate_id == candidate.candidate_id
    assert roundtripped.captures[0].candidates[0].image_path == candidate.image_path


def test_scene_change_and_frame_evaluation_and_query():
    change = SceneChange(timestamp_seconds=3.2, score=0.7)
    assert change.timestamp_seconds == 3.2

    evaluation = FrameEvaluation(candidate_id="00000000-0000-0000-0000-000000000000".replace("0", "1"))
    assert evaluation.passed is False

    query = ResearchQuery(source_id="11111111-1111-1111-1111-111111111111")
    assert query.max_candidates == 20
