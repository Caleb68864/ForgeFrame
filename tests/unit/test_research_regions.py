"""Unit tests for the research region selector."""
from __future__ import annotations

from uuid import uuid4

from workshop_video_brain.core.models import ResearchConfig, ResearchQuery
from workshop_video_brain.core.models.transcript import TranscriptSegment
from workshop_video_brain.edit_mcp.pipelines.transcript_repository import (
    TranscriptRepository,
)
from workshop_video_brain.edit_mcp.pipelines.visual_research.regions import (
    select_regions,
)


def _segment(start, end, text, segment_id):
    return TranscriptSegment(
        start_seconds=start,
        end_seconds=end,
        text=text,
        segment_id=segment_id,
    )


def test_keyword_hit_windowed_and_clamped():
    source_id = uuid4()
    config = ResearchConfig()
    repo = TranscriptRepository(
        [_segment(100.0, 101.0, "the widget explodes here", "seg-1")]
    )
    query = ResearchQuery(source_id=source_id, text="widget")

    regions = select_regions(repo, query, config)

    assert len(regions) == 1
    region = regions[0]
    assert region.source_method == "transcript"
    assert region.reason
    assert region.transcript_segment_ids == ["seg-1"]
    expected_start = 100.0 - config.windowing.pre_roll_seconds
    expected_end = 101.0 + config.windowing.post_roll_seconds
    assert region.start_seconds == expected_start
    assert region.end_seconds == expected_end


def test_keyword_hit_clamped_to_maximum_region_seconds():
    source_id = uuid4()
    config = ResearchConfig()
    config.windowing.maximum_region_seconds = 5.0
    repo = TranscriptRepository(
        [_segment(100.0, 101.0, "the widget explodes here", "seg-1")]
    )
    query = ResearchQuery(source_id=source_id, text="widget")

    regions = select_regions(repo, query, config)

    assert len(regions) == 1
    region = regions[0]
    span = region.end_seconds - region.start_seconds
    assert span <= config.windowing.maximum_region_seconds + 1e-9


def test_near_adjacent_matches_merge_and_union_segment_ids():
    source_id = uuid4()
    config = ResearchConfig()
    config.windowing.pre_roll_seconds = 1.0
    config.windowing.post_roll_seconds = 1.0
    config.windowing.merge_gap_seconds = 2.0
    repo = TranscriptRepository(
        [
            _segment(10.0, 11.0, "widget alpha", "seg-1"),
            _segment(13.0, 14.0, "widget beta", "seg-2"),
        ]
    )
    query = ResearchQuery(source_id=source_id, text="widget")

    regions = select_regions(repo, query, config)

    assert len(regions) == 1
    region = regions[0]
    assert set(region.transcript_segment_ids) == {"seg-1", "seg-2"}
    assert region.start_seconds <= 9.0
    assert region.end_seconds >= 14.0


def test_far_apart_matches_do_not_merge():
    source_id = uuid4()
    config = ResearchConfig()
    config.windowing.pre_roll_seconds = 1.0
    config.windowing.post_roll_seconds = 1.0
    config.windowing.merge_gap_seconds = 1.0
    repo = TranscriptRepository(
        [
            _segment(10.0, 11.0, "widget alpha", "seg-1"),
            _segment(50.0, 51.0, "widget beta", "seg-2"),
        ]
    )
    query = ResearchQuery(source_id=source_id, text="widget")

    regions = select_regions(repo, query, config)

    assert len(regions) == 2


def test_explicit_timestamps_with_no_transcript_yield_manual_timestamp_regions():
    source_id = uuid4()
    config = ResearchConfig()
    query = ResearchQuery(source_id=source_id, timestamps=[30.0, 90.0])

    regions = select_regions(None, query, config)

    assert len(regions) == 2
    for region in regions:
        assert region.source_method == "manual_timestamp"
        assert region.reason
        assert region.transcript_segment_ids == []


def test_explicit_range_yields_query_region():
    source_id = uuid4()
    config = ResearchConfig()
    query = ResearchQuery(source_id=source_id, start_seconds=20.0, end_seconds=25.0)

    regions = select_regions(None, query, config)

    assert len(regions) == 1
    assert regions[0].source_method == "query"


def test_explicit_segment_ids_resolve_via_repository():
    source_id = uuid4()
    config = ResearchConfig()
    repo = TranscriptRepository(
        [
            _segment(5.0, 6.0, "one", "seg-a"),
            _segment(20.0, 21.0, "two", "seg-b"),
        ]
    )
    query = ResearchQuery(source_id=source_id, segment_ids=["seg-b"])

    regions = select_regions(repo, query, config)

    assert len(regions) == 1
    assert regions[0].source_method == "query"
    assert regions[0].transcript_segment_ids == ["seg-b"]
    assert regions[0].transcript_excerpt == "two"


def test_no_matches_returns_empty_list():
    source_id = uuid4()
    config = ResearchConfig()
    repo = TranscriptRepository([_segment(0.0, 1.0, "nothing relevant", "seg-1")])
    query = ResearchQuery(source_id=source_id, text="nonexistent")

    regions = select_regions(repo, query, config)

    assert regions == []
