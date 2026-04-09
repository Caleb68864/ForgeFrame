"""Unit tests for the Whisper STT engine adapter (formatting/conversion only)."""
from __future__ import annotations

import json
import re
import sys
from types import ModuleType
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.adapters.stt.whisper_engine import (
    is_available,
    transcript_to_json,
    transcript_to_srt,
)

_TS_RE = re.compile(r"\d{2}:\d{2}:\d{2},\d{3}")


def _make_transcript(*segments: tuple[float, float, str]) -> Transcript:
    segs = [
        TranscriptSegment(start_seconds=s, end_seconds=e, text=t)
        for s, e, t in segments
    ]
    return Transcript(asset_id=uuid4(), engine="whisper", model="small", segments=segs)


class TestIsAvailable:
    def test_returns_true_when_faster_whisper_importable(self):
        fake_mod = ModuleType("faster_whisper")
        with patch.dict(sys.modules, {"faster_whisper": fake_mod}):
            result = is_available()
        assert result is True

    def test_returns_true_when_only_whisper_importable(self):
        fake_mod = ModuleType("whisper")
        # Ensure faster_whisper is NOT importable
        with patch.dict(sys.modules, {"faster_whisper": None, "whisper": fake_mod}):
            result = is_available()
        assert result is True

    def test_returns_false_when_neither_available(self):
        with patch.dict(sys.modules, {"faster_whisper": None, "whisper": None}):
            result = is_available()
        assert result is False

    def test_returns_bool(self):
        with patch.dict(sys.modules, {"faster_whisper": None, "whisper": None}):
            result = is_available()
        assert isinstance(result, bool)


class TestTranscriptToSrt:
    def test_empty_transcript_produces_empty_string(self):
        t = _make_transcript()
        result = transcript_to_srt(t)
        assert result.strip() == ""

    def test_single_segment_produces_numbered_block(self):
        t = _make_transcript((0.0, 2.5, "Hello"))
        result = transcript_to_srt(t)
        lines = result.strip().splitlines()
        assert lines[0] == "1"

    def test_srt_timestamp_format(self):
        t = _make_transcript((5.25, 8.75, "Test segment"))
        result = transcript_to_srt(t)
        timecode_line = result.strip().splitlines()[1]
        assert "-->" in timecode_line
        parts = timecode_line.split("-->")
        assert _TS_RE.match(parts[0].strip())
        assert _TS_RE.match(parts[1].strip())

    def test_multiple_segments_numbered(self):
        t = _make_transcript(
            (0.0, 2.0, "First"),
            (3.0, 5.0, "Second"),
        )
        result = transcript_to_srt(t)
        assert "1\n" in result
        assert "2\n" in result

    def test_text_included_in_output(self):
        t = _make_transcript((0.0, 2.0, "Visible text"))
        result = transcript_to_srt(t)
        assert "Visible text" in result

    def test_hours_in_timestamp_for_long_audio(self):
        # 3661 seconds = 1h 1m 1s
        t = _make_transcript((3661.0, 3663.0, "Late segment"))
        result = transcript_to_srt(t)
        assert "01:01:01,000" in result


class TestTranscriptToJson:
    def test_returns_valid_json_string(self):
        t = _make_transcript((0.0, 2.0, "Hello"))
        result = transcript_to_json(t)
        parsed = json.loads(result)
        assert isinstance(parsed, dict)

    def test_json_contains_segments(self):
        t = _make_transcript((0.0, 2.0, "A"), (3.0, 5.0, "B"))
        result = transcript_to_json(t)
        parsed = json.loads(result)
        assert "segments" in parsed
        assert len(parsed["segments"]) == 2

    def test_json_segment_text_preserved(self):
        t = _make_transcript((0.0, 1.0, "Preserved"))
        result = transcript_to_json(t)
        parsed = json.loads(result)
        assert parsed["segments"][0]["text"] == "Preserved"
