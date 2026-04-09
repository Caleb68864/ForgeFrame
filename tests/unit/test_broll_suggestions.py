"""Tests for B-roll suggestions pipeline (PL-02)."""
from __future__ import annotations

import uuid

import pytest

from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment
from workshop_video_brain.edit_mcp.pipelines.broll_suggestions import (
    detect_broll_opportunities,
    format_broll_suggestions,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_segment(text: str, start: float = 0.0, end: float = 5.0) -> TranscriptSegment:
    return TranscriptSegment(start_seconds=start, end_seconds=end, text=text)


def make_transcript(segments: list[TranscriptSegment]) -> Transcript:
    return Transcript(asset_id=uuid.uuid4(), segments=segments)


# ---------------------------------------------------------------------------
# TestDetectBrollOpportunities
# ---------------------------------------------------------------------------


class TestDetectBrollOpportunities:
    def test_empty_transcript_returns_empty_list(self):
        result = detect_broll_opportunities(make_transcript([]))
        assert result == []

    def test_blank_segment_text_skipped(self):
        result = detect_broll_opportunities(make_transcript([make_segment("   ")]))
        assert result == []

    def test_process_shot_keyword_detected(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("Now we sew the panels together")])
        )
        process_hits = [s for s in result if s["category"] == "process_shot"]
        assert len(process_hits) == 1
        assert process_hits[0]["confidence"] == 0.8

    def test_material_closeup_detected(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("This fabric is really nice")])
        )
        hits = [s for s in result if s["category"] == "material_closeup"]
        assert len(hits) == 1
        assert hits[0]["confidence"] == 0.75

    def test_tool_in_use_detected(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("Use the rotary cutter along the edge")])
        )
        hits = [s for s in result if s["category"] == "tool_in_use"]
        assert len(hits) == 1
        # "rotary cutter" is a multi-word keyword → strength 1.0 (exact phrase match)
        assert hits[0]["confidence"] == round(0.85 * 1.0, 4)

    def test_tool_in_use_exact_phrase_full_confidence(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("put the scissors away")])
        )
        hits = [s for s in result if s["category"] == "tool_in_use"]
        assert len(hits) == 1
        assert hits[0]["confidence"] == 0.85

    def test_result_reveal_detected(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("Here's what it looks like when finished")])
        )
        hits = [s for s in result if s["category"] == "result_reveal"]
        assert len(hits) >= 1

    def test_measurement_shot_with_numeric_unit(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("Cut to 12 inches from the edge")])
        )
        hits = [s for s in result if s["category"] == "measurement_shot"]
        assert len(hits) == 1
        assert hits[0]["confidence"] == 0.85

    def test_measurement_shot_via_keyword(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("measure along the seam")])
        )
        hits = [s for s in result if s["category"] == "measurement_shot"]
        assert len(hits) == 1
        assert hits[0]["confidence"] == 0.75

    def test_multi_category_segment_returns_multiple_suggestions(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("cut the fabric to 5cm")])
        )
        categories = {s["category"] for s in result}
        assert len(categories) >= 2

    def test_suggestion_dict_has_required_keys(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("sew the panels")])
        )
        assert result
        required = {"timestamp", "end_timestamp", "category", "description", "context", "confidence"}
        assert required.issubset(set(result[0].keys()))

    def test_timestamps_copied_from_segment(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("sew the edge", start=10.5, end=15.0)])
        )
        assert result
        assert result[0]["timestamp"] == 10.5
        assert result[0]["end_timestamp"] == 15.0

    def test_context_truncated_at_120_chars(self):
        long_text = "sew " + "x" * 150
        result = detect_broll_opportunities(
            make_transcript([make_segment(long_text)])
        )
        assert result
        assert len(result[0]["context"]) <= 120
        assert result[0]["context"].endswith("...")

    def test_context_not_truncated_when_under_120_chars(self):
        text = "sew the edge nicely"
        result = detect_broll_opportunities(
            make_transcript([make_segment(text)])
        )
        assert result
        assert result[0]["context"] == text

    def test_description_includes_label(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("sew the pieces")])
        )
        process_hits = [s for s in result if s["category"] == "process_shot"]
        assert process_hits
        assert process_hits[0]["description"].startswith("Show Process Shot:")

    def test_no_hits_returns_empty_list(self):
        result = detect_broll_opportunities(
            make_transcript([make_segment("Hello and welcome to my video today")])
        )
        # "today" matches hook_candidate as a process keyword only if it's in our lists
        # Let's test text with no known keywords
        result2 = detect_broll_opportunities(
            make_transcript([make_segment("Hello and welcome")])
        )
        assert result2 == []

    def test_partial_word_not_matched_as_process_shot(self):
        # "sewing" should NOT match the keyword "sew" (word boundary)
        result = detect_broll_opportunities(
            make_transcript([make_segment("sewing kit")])
        )
        process_hits = [s for s in result if s["category"] == "process_shot"]
        assert len(process_hits) == 0

    def test_multiple_segments_aggregated(self):
        segments = [
            make_segment("sew the pieces", start=0.0, end=5.0),
            make_segment("here's the final result", start=10.0, end=15.0),
        ]
        result = detect_broll_opportunities(make_transcript(segments))
        categories = [s["category"] for s in result]
        assert "process_shot" in categories
        assert "result_reveal" in categories


# ---------------------------------------------------------------------------
# TestFormatBrollSuggestions
# ---------------------------------------------------------------------------


class TestFormatBrollSuggestions:
    def test_empty_list_returns_no_opportunities_message(self):
        result = format_broll_suggestions([])
        assert "No B-roll opportunities detected" in result

    def test_output_starts_with_heading(self):
        result = format_broll_suggestions([])
        assert result.startswith("# B-Roll Suggestions")

    def test_total_count_present(self):
        suggestions = [
            {"timestamp": i * 10.0, "end_timestamp": i * 10.0 + 5.0,
             "category": "process_shot", "description": "desc",
             "context": "ctx", "confidence": 0.8}
            for i in range(3)
        ]
        result = format_broll_suggestions(suggestions)
        assert "Total suggestions: 3" in result

    def test_categories_grouped_under_headings(self):
        suggestions = [
            {"timestamp": 0.0, "end_timestamp": 5.0, "category": "process_shot",
             "description": "d", "context": "c", "confidence": 0.8},
            {"timestamp": 10.0, "end_timestamp": 15.0, "category": "tool_in_use",
             "description": "d", "context": "c", "confidence": 0.85},
        ]
        result = format_broll_suggestions(suggestions)
        assert "## Process Shot" in result
        assert "## Tool in Use" in result

    def test_items_sorted_by_timestamp_within_category(self):
        suggestions = [
            {"timestamp": 30.0, "end_timestamp": 35.0, "category": "process_shot",
             "description": "d", "context": "c", "confidence": 0.8},
            {"timestamp": 5.0, "end_timestamp": 10.0, "category": "process_shot",
             "description": "d", "context": "c", "confidence": 0.8},
        ]
        result = format_broll_suggestions(suggestions)
        pos_5 = result.index("0:05")
        pos_30 = result.index("0:30")
        assert pos_5 < pos_30

    def test_timestamp_formatted_as_mm_ss(self):
        suggestions = [
            {"timestamp": 125.0, "end_timestamp": 130.0, "category": "process_shot",
             "description": "d", "context": "c", "confidence": 0.8},
        ]
        result = format_broll_suggestions(suggestions)
        assert "2:05" in result

    def test_confidence_displayed_to_two_decimal_places(self):
        suggestions = [
            {"timestamp": 0.0, "end_timestamp": 5.0, "category": "process_shot",
             "description": "d", "context": "c", "confidence": 0.8},
        ]
        result = format_broll_suggestions(suggestions)
        assert "confidence: 0.80" in result

    def test_unknown_category_falls_back_to_category_key(self):
        suggestions = [
            {"timestamp": 0.0, "end_timestamp": 5.0, "category": "custom_cat",
             "description": "d", "context": "c", "confidence": 0.9},
        ]
        # Should not raise; uses raw category key as label
        result = format_broll_suggestions(suggestions)
        assert "custom_cat" in result
