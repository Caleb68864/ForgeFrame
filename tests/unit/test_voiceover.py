"""Unit tests for production_brain.skills.voiceover."""
from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_transcript(segments: list[dict], asset_id: str | None = None) -> dict:
    """Return a transcript dict suitable for writing as JSON."""
    return {
        "id": str(uuid.uuid4()),
        "asset_id": asset_id or str(uuid.uuid4()),
        "engine": "test",
        "model": "test",
        "language": "en",
        "segments": segments,
        "raw_text": " ".join(s["text"] for s in segments),
        "created_at": "2024-01-01T00:00:00",
    }


def _make_segment(start: float, end: float, text: str) -> dict:
    return {
        "start_seconds": start,
        "end_seconds": end,
        "text": text,
        "confidence": 1.0,
        "words": [],
    }


def _make_marker(
    category: str,
    start: float,
    end: float,
    confidence: float = 0.9,
    reason: str = "test reason",
) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "category": category,
        "confidence_score": confidence,
        "source_method": "test",
        "reason": reason,
        "clip_ref": "abc",
        "start_seconds": start,
        "end_seconds": end,
        "suggested_label": "",
    }


def _write_transcript(tmp_path: Path, name: str, segments: list[dict]) -> Path:
    transcripts_dir = tmp_path / "transcripts"
    transcripts_dir.mkdir(exist_ok=True)
    data = _make_transcript(segments)
    out = transcripts_dir / f"{name}_transcript.json"
    out.write_text(json.dumps(data), encoding="utf-8")
    return out


def _write_markers(tmp_path: Path, name: str, markers: list[dict]) -> Path:
    markers_dir = tmp_path / "markers"
    markers_dir.mkdir(exist_ok=True)
    out = markers_dir / f"{name}_markers.json"
    out.write_text(json.dumps(markers), encoding="utf-8")
    return out


# ---------------------------------------------------------------------------
# extract_fixable_segments
# ---------------------------------------------------------------------------


class TestExtractFixableSegments:
    def test_basic_extraction(self, tmp_path):
        """Segments extracted for mistake_problem, repetition, dead_air markers."""
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = [
            _make_segment(0.0, 5.0, "Let me redo that, sorry."),
            _make_segment(5.0, 10.0, "This is the correct way to cut."),
            _make_segment(10.0, 15.0, "Make sure the blade is sharp."),
        ]
        _write_transcript(tmp_path, "clip01", segments)

        markers = [
            _make_marker("mistake_problem", 0.0, 5.0, confidence=0.9, reason="Redo phrase detected"),
        ]
        _write_markers(tmp_path, "clip01", markers)

        result = extract_fixable_segments(tmp_path)
        assert isinstance(result, list)
        assert len(result) == 1
        seg = result[0]
        assert seg["category"] == "mistake_problem"
        assert seg["start"] == 0.0
        assert seg["end"] == 5.0
        assert "redo" in seg["original_text"].lower() or "sorry" in seg["original_text"].lower()

    def test_no_markers_returns_empty(self, tmp_path):
        """Returns empty list when no markers present."""
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = [_make_segment(0.0, 5.0, "Clean narration here.")]
        _write_transcript(tmp_path, "clip01", segments)
        # No markers file written

        result = extract_fixable_segments(tmp_path)
        assert result == []

    def test_no_transcript_files_returns_empty(self, tmp_path):
        """Returns empty list when no transcript files present."""
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        # Write markers but no transcript
        markers_dir = tmp_path / "markers"
        markers_dir.mkdir()
        markers = [_make_marker("mistake_problem", 0.0, 5.0, confidence=0.9)]
        (markers_dir / "clip01_markers.json").write_text(
            json.dumps(markers), encoding="utf-8"
        )

        result = extract_fixable_segments(tmp_path)
        # No transcript text found, so no results
        assert result == []

    def test_neither_dir_exists_returns_empty(self, tmp_path):
        """Returns empty list when neither transcripts/ nor markers/ exist."""
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        result = extract_fixable_segments(tmp_path)
        assert result == []

    def test_context_extraction(self, tmp_path):
        """2 segments before and after the flagged segment included as context."""
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = [
            _make_segment(0.0, 3.0, "First segment."),
            _make_segment(3.0, 6.0, "Second segment."),
            _make_segment(6.0, 9.0, "This is the problem segment."),
            _make_segment(9.0, 12.0, "Fourth segment."),
            _make_segment(12.0, 15.0, "Fifth segment."),
        ]
        _write_transcript(tmp_path, "clip01", segments)

        markers = [
            _make_marker("mistake_problem", 6.0, 9.0, confidence=0.9),
        ]
        _write_markers(tmp_path, "clip01", markers)

        result = extract_fixable_segments(tmp_path)
        assert len(result) == 1
        seg = result[0]
        assert "First segment" in seg["context_before"] or "Second segment" in seg["context_before"]
        assert "Fourth segment" in seg["context_after"] or "Fifth segment" in seg["context_after"]
        assert "problem segment" in seg["original_text"]

    def test_adjacent_markers_grouped(self, tmp_path):
        """Markers within 5 seconds of each other are grouped into one region."""
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = [
            _make_segment(0.0, 5.0, "Um uh you know like."),
            _make_segment(5.0, 10.0, "Let me start over."),
            _make_segment(10.0, 15.0, "Clean explanation here."),
        ]
        _write_transcript(tmp_path, "clip01", segments)

        markers = [
            _make_marker("mistake_problem", 0.0, 5.0, confidence=0.9),
            # Gap is 0s — starts right when previous ends: within 5s threshold
            _make_marker("mistake_problem", 5.0, 10.0, confidence=0.85),
        ]
        _write_markers(tmp_path, "clip01", markers)

        result = extract_fixable_segments(tmp_path)
        # Should be grouped into one region covering 0-10
        assert len(result) == 1
        assert result[0]["start"] == 0.0
        assert result[0]["end"] == 10.0

    def test_non_adjacent_markers_not_grouped(self, tmp_path):
        """Markers more than 5 seconds apart are not grouped."""
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = [
            _make_segment(0.0, 5.0, "Problem segment one."),
            _make_segment(5.0, 60.0, "Long clean section in the middle."),
            _make_segment(60.0, 65.0, "Problem segment two."),
        ]
        _write_transcript(tmp_path, "clip01", segments)

        markers = [
            _make_marker("mistake_problem", 0.0, 5.0, confidence=0.9),
            _make_marker("repetition", 60.0, 65.0, confidence=0.75),
        ]
        _write_markers(tmp_path, "clip01", markers)

        result = extract_fixable_segments(tmp_path)
        assert len(result) == 2
        assert result[0]["start"] == 0.0
        assert result[1]["start"] == 60.0

    def test_confidence_filtering(self, tmp_path):
        """Markers with confidence <= 0.5 are excluded."""
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = [
            _make_segment(0.0, 5.0, "Low confidence problem."),
            _make_segment(5.0, 10.0, "Borderline confidence."),
            _make_segment(10.0, 15.0, "High confidence problem."),
        ]
        _write_transcript(tmp_path, "clip01", segments)

        markers = [
            _make_marker("mistake_problem", 0.0, 5.0, confidence=0.3),   # below 0.5 — excluded
            _make_marker("mistake_problem", 5.0, 10.0, confidence=0.5),  # exactly 0.5 — excluded
            _make_marker("mistake_problem", 10.0, 15.0, confidence=0.51),  # above 0.5 — included
        ]
        _write_markers(tmp_path, "clip01", markers)

        result = extract_fixable_segments(tmp_path)
        assert len(result) == 1
        assert result[0]["start"] == 10.0

    def test_non_fixable_categories_excluded(self, tmp_path):
        """intro_candidate, chapter_candidate etc. are not included."""
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = [
            _make_segment(0.0, 5.0, "Chapter intro."),
            _make_segment(5.0, 10.0, "Real problem here."),
        ]
        _write_transcript(tmp_path, "clip01", segments)

        markers = [
            _make_marker("intro_candidate", 0.0, 5.0, confidence=0.9),   # excluded
            _make_marker("chapter_candidate", 0.0, 5.0, confidence=0.9), # excluded
            _make_marker("mistake_problem", 5.0, 10.0, confidence=0.9),  # included
        ]
        _write_markers(tmp_path, "clip01", markers)

        result = extract_fixable_segments(tmp_path)
        assert len(result) == 1
        assert result[0]["start"] == 5.0

    def test_all_three_fixable_categories_included(self, tmp_path):
        """mistake_problem, repetition, and dead_air all produce results."""
        from workshop_video_brain.production_brain.skills.voiceover import (
            extract_fixable_segments,
        )

        segments = [
            _make_segment(0.0, 5.0, "Problem segment."),
            _make_segment(20.0, 25.0, "Repeated segment."),
            _make_segment(50.0, 55.0, "Dead air."),
        ]
        _write_transcript(tmp_path, "clip01", segments)

        markers = [
            _make_marker("mistake_problem", 0.0, 5.0, confidence=0.9),
            _make_marker("repetition", 20.0, 25.0, confidence=0.8),
            _make_marker("dead_air", 50.0, 55.0, confidence=0.95),
        ]
        _write_markers(tmp_path, "clip01", markers)

        result = extract_fixable_segments(tmp_path)
        assert len(result) == 3
        categories = {r["category"] for r in result}
        assert "mistake_problem" in categories
        assert "repetition" in categories
        assert "dead_air" in categories


# ---------------------------------------------------------------------------
# format_for_review
# ---------------------------------------------------------------------------


class TestFormatForReview:
    def test_returns_string(self):
        from workshop_video_brain.production_brain.skills.voiceover import (
            format_for_review,
        )

        segments = [
            {
                "start": 10.0,
                "end": 15.0,
                "original_text": "Um uh let me redo that.",
                "context_before": "Previous sentence.",
                "context_after": "Next sentence.",
                "reason": "Redo phrase detected",
                "category": "mistake_problem",
                "confidence": 0.9,
            }
        ]
        result = format_for_review(segments)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_contains_timestamps(self):
        from workshop_video_brain.production_brain.skills.voiceover import (
            format_for_review,
        )

        segments = [
            {
                "start": 70.0,   # 1:10
                "end": 90.0,     # 1:30
                "original_text": "Some text.",
                "context_before": "",
                "context_after": "",
                "reason": "test",
                "category": "dead_air",
                "confidence": 0.95,
            }
        ]
        result = format_for_review(segments)
        assert "1:10" in result
        assert "1:30" in result

    def test_contains_original_text(self):
        from workshop_video_brain.production_brain.skills.voiceover import (
            format_for_review,
        )

        original = "This is the rambling text that needs to be fixed."
        segments = [
            {
                "start": 0.0,
                "end": 5.0,
                "original_text": original,
                "context_before": "",
                "context_after": "",
                "reason": "test",
                "category": "mistake_problem",
                "confidence": 0.8,
            }
        ]
        result = format_for_review(segments)
        assert original in result

    def test_contains_reason(self):
        from workshop_video_brain.production_brain.skills.voiceover import (
            format_for_review,
        )

        reason = "Filler word cluster detected across consecutive segments"
        segments = [
            {
                "start": 5.0,
                "end": 10.0,
                "original_text": "Um you know like.",
                "context_before": "",
                "context_after": "",
                "reason": reason,
                "category": "mistake_problem",
                "confidence": 0.6,
            }
        ]
        result = format_for_review(segments)
        assert reason in result

    def test_contains_confidence_score(self):
        from workshop_video_brain.production_brain.skills.voiceover import (
            format_for_review,
        )

        segments = [
            {
                "start": 0.0,
                "end": 5.0,
                "original_text": "Text.",
                "context_before": "",
                "context_after": "",
                "reason": "test",
                "category": "dead_air",
                "confidence": 0.75,
            }
        ]
        result = format_for_review(segments)
        assert "0.75" in result

    def test_empty_segments_returns_no_segments_message(self):
        from workshop_video_brain.production_brain.skills.voiceover import (
            format_for_review,
        )

        result = format_for_review([])
        assert "No fixable voiceover segments found" in result

    def test_multiple_segments_all_present(self):
        from workshop_video_brain.production_brain.skills.voiceover import (
            format_for_review,
        )

        segments = [
            {
                "start": 0.0,
                "end": 5.0,
                "original_text": "Alpha text.",
                "context_before": "",
                "context_after": "",
                "reason": "reason A",
                "category": "mistake_problem",
                "confidence": 0.9,
            },
            {
                "start": 30.0,
                "end": 35.0,
                "original_text": "Beta text.",
                "context_before": "",
                "context_after": "",
                "reason": "reason B",
                "category": "repetition",
                "confidence": 0.7,
            },
        ]
        result = format_for_review(segments)
        assert "Alpha text" in result
        assert "Beta text" in result
        assert "Segment 1" in result
        assert "Segment 2" in result

    def test_valid_markdown_headers(self):
        from workshop_video_brain.production_brain.skills.voiceover import (
            format_for_review,
        )

        segments = [
            {
                "start": 0.0,
                "end": 5.0,
                "original_text": "Test.",
                "context_before": "",
                "context_after": "",
                "reason": "test",
                "category": "dead_air",
                "confidence": 0.9,
            }
        ]
        result = format_for_review(segments)
        # Should have at least one H1 (top level)
        assert result.startswith("#")
        # Should have H2 for segment
        assert "## " in result
