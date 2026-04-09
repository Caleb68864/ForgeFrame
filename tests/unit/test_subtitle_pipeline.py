"""Unit tests for subtitle_pipeline: SRT generation, import, and export."""
from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.timeline import SubtitleCue
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.pipelines.subtitle_pipeline import (
    _parse_srt_content,
    export_srt,
    generate_srt,
    import_srt,
    save_srt,
)

# SRT timestamp pattern: HH:MM:SS,mmm
_TS_RE = re.compile(r"\d{2}:\d{2}:\d{2},\d{3}")


def _make_transcript(*segments: tuple[float, float, str]) -> Transcript:
    """Helper to build a Transcript from (start, end, text) tuples."""
    segs = [
        TranscriptSegment(start_seconds=s, end_seconds=e, text=t)
        for s, e, t in segments
    ]
    return Transcript(asset_id=uuid4(), segments=segs)


class TestGenerateSrt:
    def test_empty_transcript_returns_empty_string(self):
        t = _make_transcript()
        result = generate_srt(t)
        assert result == ""

    def test_single_segment_produces_one_block(self):
        t = _make_transcript((0.0, 3.0, "Hello world"))
        result = generate_srt(t)
        blocks = [b for b in result.strip().split("\n\n") if b.strip()]
        assert len(blocks) == 1

    def test_srt_block_numbered_from_one(self):
        t = _make_transcript((0.0, 2.0, "First"), (3.0, 5.0, "Second"))
        result = generate_srt(t)
        lines = result.splitlines()
        assert lines[0] == "1"

    def test_timestamp_format_is_srt(self):
        t = _make_transcript((1.5, 4.75, "Test"))
        result = generate_srt(t)
        # Expect line like "00:00:01,500 --> 00:00:04,750"
        timecode_line = result.splitlines()[1]
        assert "-->" in timecode_line
        parts = timecode_line.split("-->")
        assert _TS_RE.match(parts[0].strip())
        assert _TS_RE.match(parts[1].strip())

    def test_multiple_segments_numbered_sequentially(self):
        t = _make_transcript(
            (0.0, 2.0, "One"),
            (2.0, 4.0, "Two"),
            (4.0, 6.0, "Three"),
        )
        result = generate_srt(t)
        lines = [l for l in result.splitlines() if l.isdigit()]
        assert lines == ["1", "2", "3"]

    def test_long_segment_is_split(self):
        # 12-second segment should be split when max_duration=5
        t = _make_transcript((0.0, 12.0, "A " * 30))
        result = generate_srt(t, max_duration=5.0)
        blocks = [b for b in result.strip().split("\n\n") if b.strip()]
        assert len(blocks) > 1

    def test_max_line_length_respected(self):
        long_text = "word " * 20
        t = _make_transcript((0.0, 3.0, long_text.strip()))
        result = generate_srt(t, max_line_length=20)
        # Text lines (non-numeric, non-timecode) should be <= 20 chars each
        for line in result.splitlines():
            if line and not line.isdigit() and "-->" not in line:
                assert len(line) <= 20, f"Line too long: {line!r}"

    def test_blank_segment_text_skipped(self):
        t = _make_transcript((0.0, 2.0, "   "), (2.0, 4.0, "Real text"))
        result = generate_srt(t)
        blocks = [b for b in result.strip().split("\n\n") if b.strip()]
        assert len(blocks) == 1


class TestExportSrt:
    def test_export_produces_numbered_blocks(self):
        cues = [
            SubtitleCue(start_seconds=0.0, end_seconds=2.0, text="Hello"),
            SubtitleCue(start_seconds=2.5, end_seconds=4.5, text="World"),
        ]
        result = export_srt(cues)
        lines = result.splitlines()
        assert lines[0] == "1"

    def test_empty_cues_returns_empty_string(self):
        assert export_srt([]) == ""

    def test_export_ends_with_newline(self):
        cues = [SubtitleCue(start_seconds=0.0, end_seconds=1.0, text="Test")]
        result = export_srt(cues)
        assert result.endswith("\n")

    def test_timecode_format_in_export(self):
        cues = [SubtitleCue(start_seconds=3661.5, end_seconds=3663.0, text="One hour")]
        result = export_srt(cues)
        # 3661.5s = 01:01:01,500
        assert "01:01:01,500" in result
        assert "01:01:03,000" in result


class TestImportSrt:
    def test_import_roundtrip(self, tmp_path: Path):
        cues = [
            SubtitleCue(start_seconds=0.0, end_seconds=2.0, text="Hello"),
            SubtitleCue(start_seconds=3.0, end_seconds=5.0, text="World"),
        ]
        srt_content = export_srt(cues)
        srt_file = tmp_path / "test.srt"
        srt_file.write_text(srt_content, encoding="utf-8")

        imported = import_srt(srt_file)
        assert len(imported) == 2
        assert imported[0].text == "Hello"
        assert imported[1].text == "World"

    def test_import_preserves_timestamps(self, tmp_path: Path):
        cues = [SubtitleCue(start_seconds=10.5, end_seconds=13.25, text="Timing")]
        srt_content = export_srt(cues)
        srt_file = tmp_path / "timing.srt"
        srt_file.write_text(srt_content, encoding="utf-8")

        imported = import_srt(srt_file)
        assert imported[0].start_seconds == pytest.approx(10.5, abs=0.001)
        assert imported[0].end_seconds == pytest.approx(13.25, abs=0.001)

    def test_parse_invalid_content_returns_empty(self):
        result = _parse_srt_content("this is not valid srt content")
        assert result == []

    def test_parse_empty_string_returns_empty(self):
        result = _parse_srt_content("")
        assert result == []

    def test_generate_then_import_roundtrip(self, tmp_path: Path):
        t = _make_transcript(
            (0.0, 2.0, "First segment"),
            (3.0, 5.0, "Second segment"),
        )
        srt_content = generate_srt(t)
        srt_file = tmp_path / "gen.srt"
        srt_file.write_text(srt_content, encoding="utf-8")
        imported = import_srt(srt_file)
        assert len(imported) == 2
        assert imported[0].text == "First segment"
        assert imported[1].text == "Second segment"
