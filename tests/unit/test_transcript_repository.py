"""Unit tests for transcript parsers and TranscriptRepository."""
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.transcript.parsers import (
    parse_json_transcript,
    parse_srt,
    parse_transcript,
    parse_vtt,
)
from workshop_video_brain.edit_mcp.pipelines.transcript_repository import (
    TranscriptRepository,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "transcripts"


def test_parse_srt_fixture():
    segments = parse_transcript(FIXTURES / "sample.srt")
    assert len(segments) == 3
    assert segments[0].start_seconds == pytest.approx(0.0)
    assert segments[0].end_seconds == pytest.approx(2.5)
    assert segments[0].text == "Welcome back to the workshop."
    assert "reporter on camera" in segments[1].text
    assert segments[1].start_seconds == pytest.approx(2.5)
    assert segments[1].end_seconds == pytest.approx(5.75)


def test_parse_vtt_fixture():
    segments = parse_transcript(FIXTURES / "sample.vtt")
    assert len(segments) == 3
    assert segments[0].start_seconds == pytest.approx(0.0)
    assert segments[0].end_seconds == pytest.approx(2.5)
    assert "reporter on camera" in segments[1].text
    assert segments[2].start_seconds == pytest.approx(6.0)
    assert segments[2].end_seconds == pytest.approx(9.2)


def test_parse_json_fixture():
    segments = parse_transcript(FIXTURES / "sample.json")
    assert len(segments) == 3
    assert segments[1].text == "Today we have our reporter on camera covering the studio setup."
    assert segments[1].start_seconds == pytest.approx(2.5)
    assert segments[1].end_seconds == pytest.approx(5.75)

    # Fixture content must resolve within greenscreen_reporter_720.mp4's duration.
    reporter_segments = [s for s in segments if "reporter on camera" in s.text.lower()]
    assert reporter_segments
    for seg in reporter_segments:
        assert 0.0 <= seg.start_seconds
        assert seg.end_seconds <= 20.02


def test_parse_srt_direct():
    text = (
        "1\n00:00:00,000 --> 00:00:01,000\nHello there\n\n"
        "2\n00:00:01,000 --> 00:00:02,000\nSecond line\n"
    )
    segments = parse_srt(text)
    assert len(segments) == 2
    assert segments[0].text == "Hello there"


def test_parse_vtt_direct():
    text = "WEBVTT\n\n00:00:00.000 --> 00:00:01.000\nHello there\n"
    segments = parse_vtt(text)
    assert len(segments) == 1
    assert segments[0].text == "Hello there"


def test_parse_json_transcript_bare_list():
    raw = '[{"start": 0.0, "end": 1.0, "text": "hi"}]'
    segments = parse_json_transcript(raw)
    assert len(segments) == 1
    assert segments[0].start_seconds == 0.0
    assert segments[0].text == "hi"


def test_repository_search_case_insensitive():
    repo = TranscriptRepository(parse_transcript(FIXTURES / "sample.srt"))
    assert repo.search("REPORTER") == repo.search("reporter")
    assert len(repo.search("reporter")) == 1


def test_repository_search_substring_match():
    repo = TranscriptRepository(parse_transcript(FIXTURES / "sample.srt"))
    results = repo.search("camera")
    assert len(results) == 1
    assert "camera" in results[0].text.lower()


def test_repository_overlapping():
    repo = TranscriptRepository(parse_transcript(FIXTURES / "sample.srt"))
    # Overlaps segment 0 [0, 2.5) and segment 1 [2.5, 5.75)
    results = repo.overlapping(2.0, 3.0)
    assert len(results) == 2

    # No overlap with any segment.
    assert repo.overlapping(100.0, 101.0) == []

    # Touching boundary only (segment.end == start) should not count.
    results = repo.overlapping(5.75, 6.0)
    assert results == []


def test_repository_context_around():
    repo = TranscriptRepository(parse_transcript(FIXTURES / "sample.srt"))
    results = repo.context_around(2.5, 0.1)
    assert len(results) == 2  # segment ending at 2.5 and segment starting at 2.5... only one touches
    starts = sorted(seg.start_seconds for seg in results)
    assert starts[0] == pytest.approx(0.0) or starts[0] == pytest.approx(2.5)


def test_repository_merge_adjacent():
    repo = TranscriptRepository(parse_transcript(FIXTURES / "sample.srt"))
    merged = repo.merge_adjacent(gap_seconds=0.5)
    # segment 0 ends 2.5, segment 1 starts 2.5 (gap 0) -> merge
    # segment 1 ends 5.75, segment 2 starts 6.0 (gap 0.25 <= 0.5) -> merge
    assert len(merged) == 1
    assert merged[0].start_seconds == pytest.approx(0.0)
    assert merged[0].end_seconds == pytest.approx(9.2)


def test_repository_merge_adjacent_respects_gap():
    repo = TranscriptRepository(parse_transcript(FIXTURES / "sample.srt"))
    merged = repo.merge_adjacent(gap_seconds=0.0)
    # Only segments 0 and 1 touch with zero gap; segment 2 has a 0.25s gap.
    assert len(merged) == 2
