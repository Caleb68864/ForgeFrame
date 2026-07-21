"""Unit tests for the read-only research_transcript MCP tools.

Exercises both tools against the checked-in ``tests/fixtures/transcripts``
fixtures -- one behavioral case per supported format (.json, .srt, .vtt) --
plus error paths for missing and malformed transcript files.
"""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.edit_mcp.server.tools import research_transcript

from tests._testkit import call_tool as _invoke

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "transcripts"
JSON_FIXTURE = FIXTURES_DIR / "sample.json"
SRT_FIXTURE = FIXTURES_DIR / "sample.srt"
VTT_FIXTURE = FIXTURES_DIR / "sample.vtt"


class TestResearchTranscriptSearch:
    def test_finds_matching_segment_json(self):
        result = _invoke(
            research_transcript.research_transcript_search,
            transcript_path=str(JSON_FIXTURE),
            query="greenscreen",
        )
        assert result["status"] == "success"
        segments = result["data"]["segments"]
        assert len(segments) == 1
        assert "greenscreen" in segments[0]["text"].lower()
        assert segments[0]["start_seconds"] == 6.0
        assert segments[0]["end_seconds"] == 9.2

    def test_finds_matching_segment_srt(self):
        result = _invoke(
            research_transcript.research_transcript_search,
            transcript_path=str(SRT_FIXTURE),
            query="studio setup",
        )
        assert result["status"] == "success"
        segments = result["data"]["segments"]
        assert len(segments) == 1
        assert "studio setup" in segments[0]["text"].lower()

    def test_finds_matching_segment_vtt(self):
        result = _invoke(
            research_transcript.research_transcript_search,
            transcript_path=str(VTT_FIXTURE),
            query="Welcome back",
        )
        assert result["status"] == "success"
        segments = result["data"]["segments"]
        assert len(segments) == 1
        assert segments[0]["start_seconds"] == 0.0

    def test_zero_hits_returns_empty_list_not_error(self):
        result = _invoke(
            research_transcript.research_transcript_search,
            transcript_path=str(JSON_FIXTURE),
            query="nonexistent term xyz",
        )
        assert result["status"] == "success"
        assert result["data"]["segments"] == []
        assert result["data"]["count"] == 0

    def test_missing_file(self, tmp_path):
        missing = tmp_path / "does_not_exist.json"
        result = _invoke(
            research_transcript.research_transcript_search,
            transcript_path=str(missing),
            query="anything",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "missing_file"

    def test_malformed_transcript_returns_invalid_input(self, tmp_path):
        bad = tmp_path / "broken.json"
        bad.write_text("{not valid json", encoding="utf-8")
        result = _invoke(
            research_transcript.research_transcript_search,
            transcript_path=str(bad),
            query="anything",
        )
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_input"


class TestResearchTranscriptContext:
    def test_mid_transcript_timestamp_returns_ordered_overlaps(self):
        result = _invoke(
            research_transcript.research_transcript_context,
            transcript_path=str(JSON_FIXTURE),
            timestamp_seconds=5.0,
            window_seconds=2.0,
        )
        assert result["status"] == "success"
        segments = result["data"]["segments"]
        assert len(segments) >= 1
        starts = [seg["start_seconds"] for seg in segments]
        assert starts == sorted(starts)

    def test_timestamp_beyond_transcript_returns_empty_with_message(self):
        result = _invoke(
            research_transcript.research_transcript_context,
            transcript_path=str(JSON_FIXTURE),
            timestamp_seconds=1000.0,
            window_seconds=1.0,
        )
        assert result["status"] == "success"
        assert result["data"]["segments"] == []
        assert "9.2" in result["data"]["message"]

    def test_missing_file(self, tmp_path):
        missing = tmp_path / "does_not_exist.srt"
        result = _invoke(
            research_transcript.research_transcript_context,
            transcript_path=str(missing),
            timestamp_seconds=1.0,
        )
        assert result["status"] == "error"
        assert result["error_type"] == "missing_file"

    def test_malformed_transcript_returns_invalid_input(self, tmp_path):
        bad = tmp_path / "broken.json"
        bad.write_text("{not valid json", encoding="utf-8")
        result = _invoke(
            research_transcript.research_transcript_context,
            transcript_path=str(bad),
            timestamp_seconds=1.0,
        )
        assert result["status"] == "error"
        assert result["error_type"] == "invalid_input"
