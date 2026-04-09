"""Tests for review timeline pipeline (PL-07)."""
from __future__ import annotations

import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.kdenlive import Guide
from workshop_video_brain.core.models.markers import Marker, MarkerConfig
from workshop_video_brain.core.models.media import MediaAsset
from workshop_video_brain.edit_mcp.pipelines.review_timeline import (
    build_review_timeline,
    chronological_order,
    export_chapters_to_markdown,
    generate_chapter_markers,
    rank_markers,
)

REVIEW_MOD = "workshop_video_brain.edit_mcp.pipelines.review_timeline"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_marker(
    start: float = 0.0,
    end: float = 5.0,
    confidence: float = 0.8,
    category: str = "step_explanation",
    clip_ref: str = "/fake/clip.mp4",
    reason: str = "reason",
    label: str = "",
) -> Marker:
    return Marker(
        category=category,
        confidence_score=confidence,
        start_seconds=start,
        end_seconds=end,
        clip_ref=clip_ref,
        reason=reason,
        suggested_label=label,
    )


def make_config(weights: dict | None = None) -> MarkerConfig:
    return MarkerConfig(
        category_weights=weights or {
            "step_explanation": 0.9,
            "chapter_candidate": 1.0,
        },
        silence_threshold_seconds=2.0,
        segment_merge_gap_seconds=3.0,
    )


# ---------------------------------------------------------------------------
# TestRankMarkers
# ---------------------------------------------------------------------------


class TestRankMarkers:
    def test_empty_list_returns_empty(self):
        assert rank_markers([], make_config()) == []

    def test_single_marker_returned(self):
        m = make_marker()
        result = rank_markers([m], make_config())
        assert len(result) == 1

    def test_markers_sorted_by_score_descending(self):
        ma = make_marker(confidence=0.9, category="chapter_candidate")
        mb = make_marker(confidence=0.5, category="chapter_candidate")
        result = rank_markers([mb, ma], make_config())
        assert result[0].confidence_score == 0.9

    def test_missing_category_defaults_to_0_5_weight(self):
        m = make_marker(confidence=0.8, category="broll_candidate")
        config = make_config(weights={})  # no weights defined
        result = rank_markers([m], config)
        # score = 0.8 * 0.5 = 0.4
        assert len(result) == 1

    def test_equal_score_preserves_stable_sort_order(self):
        ma = make_marker(confidence=0.8, category="step_explanation")
        mb = make_marker(confidence=0.8, category="step_explanation")
        result = rank_markers([ma, mb], make_config())
        assert len(result) == 2


# ---------------------------------------------------------------------------
# TestChronologicalOrder
# ---------------------------------------------------------------------------


class TestChronologicalOrder:
    def test_empty_list_returns_empty(self):
        assert chronological_order([]) == []

    def test_single_marker_returned(self):
        m = make_marker()
        assert chronological_order([m]) == [m]

    def test_markers_sorted_by_start_seconds_ascending(self):
        m30 = make_marker(start=30.0)
        m5 = make_marker(start=5.0)
        m15 = make_marker(start=15.0)
        result = chronological_order([m30, m5, m15])
        assert [r.start_seconds for r in result] == [5.0, 15.0, 30.0]

    def test_original_list_not_mutated(self):
        markers = [make_marker(start=30.0), make_marker(start=5.0)]
        original_order = [m.start_seconds for m in markers]
        chronological_order(markers)
        assert [m.start_seconds for m in markers] == original_order


# ---------------------------------------------------------------------------
# TestGenerateChapterMarkers
# ---------------------------------------------------------------------------


class TestGenerateChapterMarkers:
    def test_empty_list_returns_empty(self):
        assert generate_chapter_markers([]) == []

    def test_non_chapter_markers_excluded(self):
        m = make_marker(category="step_explanation")
        assert generate_chapter_markers([m]) == []

    def test_chapter_candidate_converted_to_guide(self):
        m = make_marker(
            category="chapter_candidate",
            start=60.0,
            label="Intro",
        )
        result = generate_chapter_markers([m])
        assert len(result) == 1
        assert result[0].label == "Intro"
        assert result[0].position == 60 * 25
        assert result[0].category == "chapter"

    def test_reason_used_when_no_suggested_label(self):
        m = make_marker(category="chapter_candidate", start=30.0, reason="My Reason", label="")
        result = generate_chapter_markers([m])
        assert result[0].label == "My Reason"

    def test_fallback_label_when_both_none(self):
        m = make_marker(category="chapter_candidate", start=30.0, reason="", label="")
        result = generate_chapter_markers([m])
        assert result[0].label == "Chapter"


# ---------------------------------------------------------------------------
# TestExportChaptersToMarkdown
# ---------------------------------------------------------------------------


class TestExportChaptersToMarkdown:
    def test_empty_chapters_returns_no_chapters_message(self):
        result = export_chapters_to_markdown([])
        assert result == "# Chapters\n\n_No chapters found._\n"

    def test_single_chapter_formatted(self):
        g = Guide(position=0, label="Intro", category="chapter")
        result = export_chapters_to_markdown([g])
        assert "00:00:00" in result
        assert "Intro" in result

    def test_chapters_sorted_by_position(self):
        g1 = Guide(position=2500, label="Late", category="chapter")
        g2 = Guide(position=500, label="Early", category="chapter")
        result = export_chapters_to_markdown([g1, g2])
        assert result.index("Early") < result.index("Late")

    def test_timestamp_conversion_correct(self):
        # position=3750, fps=25.0 → 150s = 00:02:30
        g = Guide(position=3750, label="Mid", category="chapter")
        result = export_chapters_to_markdown([g], fps=25.0)
        assert "00:02:30" in result

    def test_custom_fps(self):
        # position=300, fps=30.0 → 10s → "00:00:10"
        g = Guide(position=300, label="Test", category="chapter")
        result = export_chapters_to_markdown([g], fps=30.0)
        assert "00:00:10" in result

    def test_output_starts_with_chapters_heading(self):
        g = Guide(position=0, label="Start", category="chapter")
        result = export_chapters_to_markdown([g])
        assert result.startswith("# Chapters")


# ---------------------------------------------------------------------------
# TestBuildReviewTimeline
# ---------------------------------------------------------------------------


class TestBuildReviewTimeline:
    @patch(f"{REVIEW_MOD}.serialize_versioned")
    def test_returns_path_to_kdenlive_file(self, mock_serialize, tmp_path):
        expected = tmp_path / "review_timeline_v1.kdenlive"
        mock_serialize.return_value = expected
        m = make_marker()
        result = build_review_timeline([m], [], tmp_path)
        assert result == expected

    @patch(f"{REVIEW_MOD}.serialize_versioned")
    def test_ranked_mode_orders_by_confidence(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "review_timeline_v1.kdenlive"

        mock_serialize.side_effect = capture

        m_low = make_marker(confidence=0.3, clip_ref="/low.mp4")
        m_high = make_marker(confidence=0.9, clip_ref="/high.mp4")

        build_review_timeline([m_low, m_high], [], tmp_path, mode="ranked")

        # High confidence producer should be first
        resources = [p.resource for p in captured["project"].producers]
        assert resources[0] == "/high.mp4"

    @patch(f"{REVIEW_MOD}.serialize_versioned")
    def test_chronological_mode_orders_by_start_seconds(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "review_timeline_v1.kdenlive"

        mock_serialize.side_effect = capture

        m_late = make_marker(start=30.0, clip_ref="/late.mp4")
        m_early = make_marker(start=5.0, clip_ref="/early.mp4")

        build_review_timeline([m_late, m_early], [], tmp_path, mode="chronological")

        video_playlist = captured["project"].playlists[0]
        assert video_playlist.entries[0].in_point == int(5.0 * 25)

    @patch(f"{REVIEW_MOD}.serialize_versioned")
    def test_empty_markers_creates_empty_project(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "review_timeline_v1.kdenlive"

        mock_serialize.side_effect = capture

        build_review_timeline([], [], tmp_path)
        assert captured["project"].producers == []

    @patch(f"{REVIEW_MOD}.serialize_versioned")
    def test_asset_resolved_by_clip_ref(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "review_timeline_v1.kdenlive"

        mock_serialize.side_effect = capture

        asset = MediaAsset(path="/real/path.mp4")
        m = make_marker(clip_ref="/real/path.mp4")

        build_review_timeline([m], [asset], tmp_path)
        assert captured["project"].producers[0].resource == "/real/path.mp4"

    @patch(f"{REVIEW_MOD}.serialize_versioned")
    def test_unknown_clip_ref_uses_clip_ref_as_resource(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "review_timeline_v1.kdenlive"

        mock_serialize.side_effect = capture

        m = make_marker(clip_ref="/unknown/path.mp4")
        build_review_timeline([m], [], tmp_path)
        assert captured["project"].producers[0].resource == "/unknown/path.mp4"

    @patch(f"{REVIEW_MOD}.serialize_versioned")
    def test_guide_label_includes_category_reason_and_confidence(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "review_timeline_v1.kdenlive"

        mock_serialize.side_effect = capture

        m = make_marker(
            category="step_explanation",
            reason="saw the cut",
            confidence=0.85,
        )
        build_review_timeline([m], [], tmp_path)

        guide_labels = [g.label for g in captured["project"].guides]
        assert len(guide_labels) == 1
        assert "step_explanation" in guide_labels[0]
        assert "saw the cut" in guide_labels[0]
        assert "0.85" in guide_labels[0]

    @patch(f"{REVIEW_MOD}.serialize_versioned")
    def test_review_report_markdown_written(self, mock_serialize, tmp_path):
        mock_serialize.return_value = tmp_path / "review_timeline_v1.kdenlive"
        m = make_marker()
        build_review_timeline([m], [], tmp_path)
        reports_dir = tmp_path / "reports"
        assert reports_dir.exists()
        md_files = list(reports_dir.glob("*.md"))
        assert len(md_files) >= 1

    @patch(f"{REVIEW_MOD}.serialize_versioned")
    def test_duplicate_clip_refs_reuse_same_producer(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "review_timeline_v1.kdenlive"

        mock_serialize.side_effect = capture

        m1 = make_marker(start=0.0, end=5.0, clip_ref="/same.mp4")
        m2 = make_marker(start=10.0, end=15.0, clip_ref="/same.mp4")

        build_review_timeline([m1, m2], [], tmp_path)
        assert len(captured["project"].producers) == 1
        video_playlist = captured["project"].playlists[0]
        assert len(video_playlist.entries) == 2

    @patch(f"{REVIEW_MOD}.serialize_versioned")
    def test_in_out_points_match_marker_timestamps(self, mock_serialize, tmp_path):
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "review_timeline_v1.kdenlive"

        mock_serialize.side_effect = capture

        m = make_marker(start=10.0, end=20.0)
        build_review_timeline([m], [], tmp_path)

        entry = captured["project"].playlists[0].entries[0]
        assert entry.in_point == 250
        assert entry.out_point == 500
