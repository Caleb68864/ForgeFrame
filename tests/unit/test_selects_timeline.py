"""Tests for selects timeline pipeline (PL-08)."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from workshop_video_brain.core.models.markers import Marker, MarkerConfig
from workshop_video_brain.core.models.media import MediaAsset
from workshop_video_brain.edit_mcp.pipelines.selects_timeline import (
    SelectsEntry,
    build_selects,
    build_selects_timeline,
    selects_to_json,
    selects_to_markdown,
)

SELECTS_MOD = "workshop_video_brain.edit_mcp.pipelines.selects_timeline"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_marker(
    start: float = 0.0,
    end: float = 5.0,
    confidence: float = 0.8,
    category: str = "step_explanation",
    clip_ref: str = "/clip.mp4",
    reason: str = "r",
) -> Marker:
    return Marker(
        category=category,
        confidence_score=confidence,
        start_seconds=start,
        end_seconds=end,
        clip_ref=clip_ref,
        reason=reason,
    )


def make_config(weights: dict | None = None) -> MarkerConfig:
    return MarkerConfig(
        category_weights=weights or {"step_explanation": 0.9},
        silence_threshold_seconds=2.0,
        segment_merge_gap_seconds=3.0,
    )


def make_entry(
    start: float = 0.0,
    end: float = 5.0,
    confidence: float = 0.8,
    category: str = "step_explanation",
    reason: str = "r",
) -> SelectsEntry:
    m = make_marker(start=start, end=end, confidence=confidence, category=category, reason=reason)
    return SelectsEntry(
        marker=m,
        clip_ref=m.clip_ref,
        start_seconds=m.start_seconds,
        end_seconds=m.end_seconds,
        reason=m.reason,
        usefulness_score=round(confidence * 0.9, 6),
    )


# ---------------------------------------------------------------------------
# TestSelectsEntry
# ---------------------------------------------------------------------------


class TestSelectsEntry:
    def test_fields_match_marker(self):
        m = make_marker(start=1.0, end=6.0, confidence=0.7, reason="test")
        entry = SelectsEntry(
            marker=m,
            clip_ref=m.clip_ref,
            start_seconds=m.start_seconds,
            end_seconds=m.end_seconds,
            reason=m.reason,
            usefulness_score=0.63,
        )
        assert entry.clip_ref == "/clip.mp4"
        assert entry.start_seconds == 1.0
        assert entry.end_seconds == 6.0
        assert entry.reason == "test"
        assert isinstance(entry.usefulness_score, float)


# ---------------------------------------------------------------------------
# TestBuildSelects
# ---------------------------------------------------------------------------


class TestBuildSelects:
    def test_empty_markers_returns_empty_list(self):
        assert build_selects([], make_config()) == []

    def test_marker_below_min_confidence_excluded(self):
        m = make_marker(confidence=0.4)
        result = build_selects([m], make_config(), min_confidence=0.5)
        assert result == []

    def test_marker_at_min_confidence_included(self):
        m = make_marker(confidence=0.5)
        result = build_selects([m], make_config(), min_confidence=0.5)
        assert len(result) == 1

    def test_dead_air_category_excluded(self):
        m = make_marker(confidence=0.9, category="dead_air")
        result = build_selects([m], make_config())
        assert result == []

    def test_repetition_category_excluded(self):
        m = make_marker(confidence=0.9, category="repetition")
        result = build_selects([m], make_config())
        assert result == []

    def test_non_excluded_category_included(self):
        m = make_marker(confidence=0.7, category="step_explanation")
        result = build_selects([m], make_config())
        assert len(result) == 1

    def test_usefulness_score_is_confidence_times_weight(self):
        m = make_marker(confidence=0.8, category="step_explanation")
        result = build_selects([m], make_config({"step_explanation": 0.9}))
        assert result[0].usefulness_score == round(0.8 * 0.9, 6)

    def test_missing_category_weight_defaults_to_0_5(self):
        # Use a valid category that is NOT in the config weights → default 0.5
        m = make_marker(confidence=0.8, category="fix_recovery")
        config = make_config(weights={})  # empty weights → fallback to 0.5
        result = build_selects([m], config)
        assert result[0].usefulness_score == round(0.8 * 0.5, 6)

    def test_entries_sorted_by_usefulness_descending(self):
        m_high = make_marker(confidence=0.9, category="step_explanation", start=0.0)
        m_low = make_marker(confidence=0.4, category="step_explanation", start=5.0)
        config = make_config({"step_explanation": 1.0})
        result = build_selects([m_high, m_low], config, min_confidence=0.0)
        assert result[0].usefulness_score > result[1].usefulness_score

    def test_clip_ref_copied_from_marker(self):
        m = make_marker(clip_ref="/my/clip.mp4")
        result = build_selects([m], make_config())
        assert result[0].clip_ref == "/my/clip.mp4"

    def test_start_end_copied_from_marker(self):
        m = make_marker(start=3.0, end=9.0)
        result = build_selects([m], make_config())
        assert result[0].start_seconds == 3.0
        assert result[0].end_seconds == 9.0

    def test_reason_copied_from_marker(self):
        m = make_marker(reason="good take")
        result = build_selects([m], make_config())
        assert result[0].reason == "good take"

    def test_multiple_markers_mixed_filter(self):
        m_dead = make_marker(confidence=0.9, category="dead_air")
        m_low = make_marker(confidence=0.2, category="step_explanation")
        m_valid = make_marker(confidence=0.8, category="step_explanation")
        result = build_selects([m_dead, m_low, m_valid], make_config())
        assert len(result) == 1


# ---------------------------------------------------------------------------
# TestSelectsToJson
# ---------------------------------------------------------------------------


class TestSelectsToJson:
    def test_empty_selects_returns_empty_json_array(self):
        result = selects_to_json([])
        assert json.loads(result) == []

    def test_valid_selects_serializes_to_list(self):
        entry = make_entry()
        result = selects_to_json([entry])
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_output_is_valid_json(self):
        entry = make_entry()
        # Should not raise
        json.loads(selects_to_json([entry]))

    def test_usefulness_score_preserved_in_json(self):
        entry = make_entry(confidence=0.8)
        data = json.loads(selects_to_json([entry]))
        assert data[0]["usefulness_score"] == entry.usefulness_score

    def test_all_required_fields_present_in_json(self):
        entry = make_entry()
        data = json.loads(selects_to_json([entry]))
        required = {"marker", "clip_ref", "start_seconds", "end_seconds", "reason", "usefulness_score"}
        assert required.issubset(set(data[0].keys()))


# ---------------------------------------------------------------------------
# TestSelectsToMarkdown
# ---------------------------------------------------------------------------


class TestSelectsToMarkdown:
    def test_empty_selects_returns_header_and_empty_table(self):
        result = selects_to_markdown([])
        assert "| Time | Category | Reason | Score |" in result
        assert "| --- | --- | --- | --- |" in result

    def test_table_has_four_columns(self):
        result = selects_to_markdown([])
        assert result.startswith("| Time | Category | Reason | Score |")

    def test_time_formatted_correctly(self):
        entry = make_entry(start=10.5, end=20.0)
        result = selects_to_markdown([entry])
        assert "10.5s – 20.0s" in result

    def test_reason_pipe_escaped(self):
        entry = make_entry(reason="cut | measure")
        result = selects_to_markdown([entry])
        assert "cut \\| measure" in result

    def test_score_formatted_to_three_decimal_places(self):
        entry = make_entry(confidence=0.8)
        # 0.8 * 0.9 = 0.72
        result = selects_to_markdown([entry])
        assert "0.720" in result

    def test_category_string_in_row(self):
        entry = make_entry(category="step_explanation")
        result = selects_to_markdown([entry])
        assert "step_explanation" in result

    def test_output_ends_with_newline(self):
        entry = make_entry()
        result = selects_to_markdown([entry])
        assert result.endswith("\n")


# ---------------------------------------------------------------------------
# TestBuildSelectsTimeline
# ---------------------------------------------------------------------------


class TestBuildSelectsTimeline:
    @patch(f"{SELECTS_MOD}.serialize_versioned")
    def test_returns_path(self, mock_serialize, tmp_path):
        expected = tmp_path / "selects_v1.kdenlive"
        mock_serialize.return_value = expected
        selects = [make_entry()]
        result = build_selects_timeline(selects, [], tmp_path)
        assert result == expected

    @patch(f"{SELECTS_MOD}.serialize_versioned")
    def test_empty_selects_creates_empty_project(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "selects_v1.kdenlive"

        mock_serialize.side_effect = capture
        build_selects_timeline([], [], tmp_path)
        assert captured["project"].producers == []

    @patch(f"{SELECTS_MOD}.serialize_versioned")
    def test_producer_created_per_unique_clip_ref(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "selects_v1.kdenlive"

        mock_serialize.side_effect = capture

        e1 = make_entry()
        e2 = make_entry(start=10.0)
        e1.clip_ref = "/same.mp4"
        e2.clip_ref = "/same.mp4"

        build_selects_timeline([e1, e2], [], tmp_path)
        assert len(captured["project"].producers) == 1

    @patch(f"{SELECTS_MOD}.serialize_versioned")
    def test_in_out_points_from_selects_seconds(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "selects_v1.kdenlive"

        mock_serialize.side_effect = capture

        entry = make_entry(start=10.0, end=20.0)
        build_selects_timeline([entry], [], tmp_path)

        playlist_entry = captured["project"].playlists[0].entries[0]
        assert playlist_entry.in_point == 250
        assert playlist_entry.out_point == 500

    @patch(f"{SELECTS_MOD}.serialize_versioned")
    def test_asset_resolved_when_available(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "selects_v1.kdenlive"

        mock_serialize.side_effect = capture

        asset = MediaAsset(path="/real/path.mp4")
        entry = make_entry()
        entry.clip_ref = "/real/path.mp4"

        build_selects_timeline([entry], [asset], tmp_path)
        assert captured["project"].producers[0].resource == "/real/path.mp4"

    @patch(f"{SELECTS_MOD}.serialize_versioned")
    def test_guide_added_per_entry(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "selects_v1.kdenlive"

        mock_serialize.side_effect = capture

        e1 = make_entry(start=0.0)
        e2 = make_entry(start=10.0)
        e2.clip_ref = "/other.mp4"

        build_selects_timeline([e1, e2], [], tmp_path)
        assert len(captured["project"].guides) == 2

    @patch(f"{SELECTS_MOD}.serialize_versioned")
    def test_guide_label_is_reason_or_category(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "selects_v1.kdenlive"

        mock_serialize.side_effect = capture

        entry = make_entry(reason="Intro section")
        build_selects_timeline([entry], [], tmp_path)

        assert captured["project"].guides[0].label == "Intro section"

    @patch(f"{SELECTS_MOD}.serialize_versioned")
    def test_out_point_never_less_than_in_point(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "selects_v1.kdenlive"

        mock_serialize.side_effect = capture

        # Zero-length entry
        entry = make_entry(start=5.0, end=5.0)
        build_selects_timeline([entry], [], tmp_path)

        pe = captured["project"].playlists[0].entries[0]
        assert pe.out_point >= pe.in_point
