"""Unit tests for phrase detection, repetition detection, and export_mistakes."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from uuid import UUID

import pytest

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import Marker
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.pipelines.auto_mark import (
    detect_phrases,
    detect_repetition,
    export_mistakes,
)

_ASSET_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _make_transcript(segments: list[dict]) -> Transcript:
    return Transcript(
        asset_id=_ASSET_ID,
        engine="whisper",
        segments=[TranscriptSegment(**s) for s in segments],
    )


# ---------------------------------------------------------------------------
# detect_phrases — redo phrases
# ---------------------------------------------------------------------------


class TestRedoPhraseDetection:
    def test_let_me_start_over_detected(self):
        transcript = _make_transcript([
            {"start_seconds": 5.0, "end_seconds": 7.0, "text": "Let me start over from the beginning."},
        ])
        markers = detect_phrases(transcript)
        assert len(markers) >= 1
        m = markers[0]
        assert m.category == MarkerCategory.mistake_problem
        assert m.confidence_score == 0.9
        assert m.source_method == "phrase_detection"
        assert "let me start over" in m.reason

    def test_sorry_detected(self):
        transcript = _make_transcript([
            {"start_seconds": 1.0, "end_seconds": 2.0, "text": "Sorry about that."},
        ])
        markers = detect_phrases(transcript)
        redo_markers = [m for m in markers if m.confidence_score == 0.9]
        assert len(redo_markers) >= 1

    def test_hold_on_detected(self):
        transcript = _make_transcript([
            {"start_seconds": 3.0, "end_seconds": 5.0, "text": "Hold on, let me check that."},
        ])
        markers = detect_phrases(transcript)
        redo_markers = [m for m in markers if m.confidence_score == 0.9]
        assert len(redo_markers) >= 1

    def test_scratch_that_detected(self):
        transcript = _make_transcript([
            {"start_seconds": 10.0, "end_seconds": 11.0, "text": "Scratch that, I'll do it differently."},
        ])
        markers = detect_phrases(transcript)
        redo_markers = [m for m in markers if m.confidence_score == 0.9]
        assert len(redo_markers) >= 1
        assert "scratch that" in redo_markers[0].reason

    def test_no_redo_phrase_no_marker(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 2.0, "text": "This is a perfectly normal sentence."},
        ])
        markers = detect_phrases(transcript)
        redo_markers = [m for m in markers if m.confidence_score == 0.9]
        assert len(redo_markers) == 0

    def test_redo_phrase_case_insensitive(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 2.0, "text": "WAIT NO that's not right."},
        ])
        markers = detect_phrases(transcript)
        redo_markers = [m for m in markers if m.confidence_score == 0.9]
        assert len(redo_markers) >= 1

    def test_marker_has_correct_clip_ref_and_timing(self):
        transcript = _make_transcript([
            {"start_seconds": 12.5, "end_seconds": 14.0, "text": "Actually wait, that was wrong."},
        ])
        markers = detect_phrases(transcript)
        redo_markers = [m for m in markers if m.confidence_score == 0.9]
        assert len(redo_markers) >= 1
        m = redo_markers[0]
        assert m.clip_ref == _ASSET_ID.hex
        assert m.start_seconds == 12.5
        assert m.end_seconds == 14.0


# ---------------------------------------------------------------------------
# detect_phrases — filler cluster detection
# ---------------------------------------------------------------------------


class TestFillerClusterDetection:
    def test_filler_cluster_in_single_segment(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 3.0, "text": "Um um um uh we go this way."},
        ])
        markers = detect_phrases(transcript)
        filler_markers = [
            m for m in markers
            if m.source_method == "phrase_detection" and m.confidence_score == 0.6
        ]
        assert len(filler_markers) >= 1

    def test_filler_cluster_across_consecutive_segments_within_window(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 2.0, "text": "um uh go there"},
            {"start_seconds": 5.0, "end_seconds": 7.0, "text": "um like this way"},
        ])
        markers = detect_phrases(transcript)
        filler_markers = [
            m for m in markers
            if m.source_method == "phrase_detection" and m.confidence_score == 0.6
        ]
        assert len(filler_markers) >= 1

    def test_filler_below_threshold_no_marker(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 3.0, "text": "Um, we go this way and uh that way."},
        ])
        markers = detect_phrases(transcript)
        # 2 fillers ("um", "uh") — below threshold of 3
        filler_markers = [
            m for m in markers
            if m.source_method == "phrase_detection" and m.confidence_score == 0.6
        ]
        assert len(filler_markers) == 0

    def test_filler_outside_window_no_cross_segment_marker(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 2.0, "text": "um uh"},
            {"start_seconds": 20.0, "end_seconds": 22.0, "text": "um like"},  # >10s apart
        ])
        markers = detect_phrases(transcript)
        # Each has only 2 fillers, combined but outside window
        cross_markers = [
            m for m in markers
            if m.source_method == "phrase_detection"
            and m.confidence_score == 0.6
            and "across consecutive" in m.reason
        ]
        assert len(cross_markers) == 0


# ---------------------------------------------------------------------------
# detect_phrases — false start detection
# ---------------------------------------------------------------------------


class TestFalseStartDetection:
    def test_false_start_same_first_three_words_within_window(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 2.0, "text": "Now we are going to cut this piece."},
            {"start_seconds": 10.0, "end_seconds": 12.0, "text": "Now we are going to sand it down."},
        ])
        markers = detect_phrases(transcript)
        false_starts = [
            m for m in markers
            if m.source_method == "phrase_detection" and m.confidence_score == 0.5
        ]
        assert len(false_starts) >= 1
        assert "False start" in false_starts[0].reason

    def test_false_start_beyond_window_not_detected(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 2.0, "text": "Now we are cutting the wood piece."},
            {"start_seconds": 20.0, "end_seconds": 22.0, "text": "Now we are sanding the wood piece."},
        ])
        markers = detect_phrases(transcript)
        false_starts = [
            m for m in markers
            if m.source_method == "phrase_detection" and m.confidence_score == 0.5
        ]
        assert len(false_starts) == 0

    def test_false_start_fewer_than_three_words_ignored(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 1.0, "text": "Go there."},
            {"start_seconds": 5.0, "end_seconds": 6.0, "text": "Go here instead."},
        ])
        # Only 2 words each — shorter than threshold
        markers = detect_phrases(transcript)
        false_starts = [
            m for m in markers
            if m.source_method == "phrase_detection" and m.confidence_score == 0.5
        ]
        assert len(false_starts) == 0

    def test_false_start_marker_spans_both_segments(self):
        transcript = _make_transcript([
            {"start_seconds": 2.0, "end_seconds": 4.0, "text": "Let me show you how to do this properly."},
            {"start_seconds": 8.0, "end_seconds": 10.0, "text": "Let me show you how it actually works."},
        ])
        markers = detect_phrases(transcript)
        false_starts = [
            m for m in markers
            if m.source_method == "phrase_detection" and m.confidence_score == 0.5
        ]
        assert len(false_starts) >= 1
        m = false_starts[0]
        assert m.start_seconds == 2.0
        assert m.end_seconds == 10.0


# ---------------------------------------------------------------------------
# detect_repetition
# ---------------------------------------------------------------------------


class TestRepetitionDetection:
    def test_similar_segments_produce_repetition_marker(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 3.0, "text": "You need to sand the wood smoothly."},
            {"start_seconds": 10.0, "end_seconds": 13.0, "text": "You need to sand the wood smoothly."},
        ])
        markers = detect_repetition(transcript)
        assert len(markers) == 1
        m = markers[0]
        assert m.category == MarkerCategory.repetition
        assert m.source_method == "repetition_detection"
        # Later segment is flagged
        assert m.start_seconds == 10.0
        assert m.end_seconds == 13.0

    def test_repetition_confidence_is_jaccard_similarity(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 2.0, "text": "cut the wood piece"},
            {"start_seconds": 5.0, "end_seconds": 7.0, "text": "cut the wood piece"},
        ])
        markers = detect_repetition(transcript)
        assert len(markers) == 1
        # Identical text → Jaccard = 1.0
        assert markers[0].confidence_score == 1.0

    def test_repetition_reason_contains_earlier_segment_time(self):
        transcript = _make_transcript([
            {"start_seconds": 5.0, "end_seconds": 7.0, "text": "sand the wood piece smoothly and evenly"},
            {"start_seconds": 15.0, "end_seconds": 17.0, "text": "sand the wood piece smoothly and evenly"},
        ])
        markers = detect_repetition(transcript)
        assert len(markers) == 1
        assert "5.0s" in markers[0].reason

    def test_below_threshold_no_repetition_marker(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 3.0, "text": "first cut the plank lengthwise"},
            {"start_seconds": 5.0, "end_seconds": 8.0, "text": "then sand the surface smoothly"},
        ])
        markers = detect_repetition(transcript)
        assert len(markers) == 0

    def test_segments_beyond_60s_not_flagged(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 3.0, "text": "sand the wood piece smooth"},
            {"start_seconds": 65.0, "end_seconds": 68.0, "text": "sand the wood piece smooth"},
        ])
        markers = detect_repetition(transcript)
        assert len(markers) == 0

    def test_window_parameter_limits_comparison_range(self):
        # Segments at indices 0 and 5 have identical text; all other segments are
        # completely different from each other and from index 0/5.
        # With window=4, index 0 only compares against indices 1-4, so index 5 is
        # never compared against index 0 and should not be flagged.
        segs = [
            {"start_seconds": 0.0, "end_seconds": 3.0, "text": "sand the wood piece smooth"},
            {"start_seconds": 5.0, "end_seconds": 8.0, "text": "alpha bravo charlie delta echo"},
            {"start_seconds": 10.0, "end_seconds": 13.0, "text": "foxtrot golf hotel india juliet"},
            {"start_seconds": 15.0, "end_seconds": 18.0, "text": "kilo lima mike november oscar"},
            {"start_seconds": 20.0, "end_seconds": 23.0, "text": "papa quebec romeo sierra tango"},
            {"start_seconds": 25.0, "end_seconds": 28.0, "text": "sand the wood piece smooth"},
        ]
        transcript = _make_transcript(segs)
        markers = detect_repetition(transcript, window=4)
        # index 5 is 5 steps from index 0, outside window=4, so NOT detected
        assert len(markers) == 0

    def test_repetition_custom_threshold(self):
        # Two somewhat similar segments that exceed a lower threshold
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 3.0, "text": "cut the plank along the line"},
            {"start_seconds": 10.0, "end_seconds": 13.0, "text": "cut the board along the line"},
        ])
        # With default threshold 0.6: Jaccard("cut the plank along the line",
        # "cut the board along the line") = 4/6 ≈ 0.667 → should detect
        markers = detect_repetition(transcript, threshold=0.6)
        assert len(markers) == 1

    def test_empty_segments_skipped_gracefully(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 2.0, "text": ""},
            {"start_seconds": 3.0, "end_seconds": 5.0, "text": "sand the wood piece"},
            {"start_seconds": 10.0, "end_seconds": 12.0, "text": "sand the wood piece"},
        ])
        markers = detect_repetition(transcript)
        assert len(markers) == 1


# ---------------------------------------------------------------------------
# Empty transcript — no crash
# ---------------------------------------------------------------------------


class TestEmptyTranscript:
    def test_detect_phrases_empty_no_crash(self):
        transcript = _make_transcript([])
        markers = detect_phrases(transcript)
        assert markers == []

    def test_detect_repetition_empty_no_crash(self):
        transcript = _make_transcript([])
        markers = detect_repetition(transcript)
        assert markers == []

    def test_detect_phrases_whitespace_only_segments(self):
        transcript = _make_transcript([
            {"start_seconds": 0.0, "end_seconds": 1.0, "text": "   "},
            {"start_seconds": 2.0, "end_seconds": 3.0, "text": "\t"},
        ])
        markers = detect_phrases(transcript)
        assert markers == []


# ---------------------------------------------------------------------------
# export_mistakes
# ---------------------------------------------------------------------------


class TestExportMistakes:
    def _make_markers(self) -> list[Marker]:
        return [
            Marker(
                category=MarkerCategory.mistake_problem,
                confidence_score=0.9,
                source_method="phrase_detection",
                reason="Redo phrase",
                clip_ref="abc",
                start_seconds=1.0,
                end_seconds=2.0,
            ),
            Marker(
                category=MarkerCategory.repetition,
                confidence_score=0.8,
                source_method="repetition_detection",
                reason="Repeated segment",
                clip_ref="abc",
                start_seconds=5.0,
                end_seconds=7.0,
            ),
            Marker(
                category=MarkerCategory.dead_air,
                confidence_score=1.0,
                source_method="silence_detection",
                reason="Silence gap",
                clip_ref="abc",
                start_seconds=10.0,
                end_seconds=15.0,
            ),
            Marker(
                category=MarkerCategory.chapter_candidate,
                confidence_score=0.7,
                source_method="keyword_rule",
                reason="Keyword match",
                clip_ref="abc",
                start_seconds=20.0,
                end_seconds=22.0,
            ),
        ]

    def test_export_filters_to_mistake_categories(self):
        markers = self._make_markers()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "mistakes.json"
            result_path = export_mistakes(markers, output_path)
            data = json.loads(result_path.read_text())
        assert len(data) == 3
        categories = {item["category"] for item in data}
        assert categories == {"mistake_problem", "repetition", "dead_air"}
        assert "chapter_candidate" not in categories

    def test_export_returns_output_path(self):
        markers = self._make_markers()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "mistakes.json"
            result_path = export_mistakes(markers, output_path)
        assert result_path == output_path

    def test_export_writes_valid_json(self):
        markers = self._make_markers()
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "mistakes.json"
            export_mistakes(markers, output_path)
            raw = output_path.read_text()
        parsed = json.loads(raw)
        assert isinstance(parsed, list)
        for item in parsed:
            assert "category" in item
            assert "confidence_score" in item
            assert "start_seconds" in item
            assert "end_seconds" in item

    def test_export_empty_markers_writes_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "mistakes.json"
            export_mistakes([], output_path)
            data = json.loads(output_path.read_text())
        assert data == []

    def test_export_only_non_mistake_markers_writes_empty_list(self):
        markers = [
            Marker(
                category=MarkerCategory.chapter_candidate,
                confidence_score=0.6,
                source_method="keyword_rule",
                reason="Chapter",
                clip_ref="abc",
                start_seconds=0.0,
                end_seconds=1.0,
            ),
            Marker(
                category=MarkerCategory.intro_candidate,
                confidence_score=0.8,
                source_method="position_heuristic",
                reason="Intro",
                clip_ref="abc",
                start_seconds=0.0,
                end_seconds=30.0,
            ),
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "mistakes.json"
            export_mistakes(markers, output_path)
            data = json.loads(output_path.read_text())
        assert data == []
