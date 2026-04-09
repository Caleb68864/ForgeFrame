"""Tests for replay generator pipeline (PL-06)."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import Marker
from workshop_video_brain.edit_mcp.pipelines.replay_generator import (
    ReplayReport,
    ReplaySegment,
    _apply_padding,
    _load_markers,
    _merge_adjacent,
    _select_segments,
    generate_replay,
)

REPLAY_MOD = "workshop_video_brain.edit_mcp.pipelines.replay_generator"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_marker(
    start: float = 0.0,
    end: float = 10.0,
    confidence: float = 0.8,
    category: str = "chapter_candidate",
    clip_ref: str = "/fake/clip.mp4",
    reason: str = "test reason",
) -> Marker:
    return Marker(
        category=category,
        confidence_score=confidence,
        start_seconds=start,
        end_seconds=end,
        clip_ref=clip_ref,
        reason=reason,
    )


def write_markers_json(markers_dir: Path, filename: str, markers: list[Marker]) -> None:
    markers_dir.mkdir(parents=True, exist_ok=True)
    data = [m.model_dump(mode="json") for m in markers]
    (markers_dir / filename).write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# TestReplayModels
# ---------------------------------------------------------------------------


class TestReplayModels:
    def test_replay_segment_fields(self):
        seg = ReplaySegment(start=0.0, end=10.0, reason="r", source_clip="/x.mp4")
        assert seg.start == 0.0
        assert seg.end == 10.0
        assert seg.reason == "r"

    def test_replay_report_fields(self):
        report = ReplayReport(
            segment_count=2,
            total_duration=20.0,
            target_duration=60.0,
            segments_used=[],
        )
        assert report.segment_count == 2

    def test_replay_segment_is_pydantic_model(self):
        seg = ReplaySegment(start=0.0, end=5.0, reason="r", source_clip="/x.mp4")
        assert isinstance(seg, BaseModel)


# ---------------------------------------------------------------------------
# TestLoadMarkers
# ---------------------------------------------------------------------------


class TestLoadMarkers:
    def test_missing_markers_dir_returns_empty_list(self, tmp_path):
        # No markers/ directory
        result = _load_markers(tmp_path)
        assert result == []

    def test_loads_markers_from_json(self, tmp_path):
        markers = [make_marker(start=0.0, end=5.0), make_marker(start=10.0, end=15.0)]
        write_markers_json(tmp_path / "markers", "clip_markers.json", markers)
        result = _load_markers(tmp_path)
        assert len(result) == 2

    def test_only_files_matching_pattern_loaded(self, tmp_path):
        markers_dir = tmp_path / "markers"
        markers_dir.mkdir(parents=True)
        # Non-matching file
        (markers_dir / "notes.txt").write_text("not json", encoding="utf-8")
        # Matching file
        write_markers_json(markers_dir, "clip_markers.json", [make_marker()])
        result = _load_markers(tmp_path)
        assert len(result) == 1

    def test_corrupt_json_file_skipped(self, tmp_path):
        markers_dir = tmp_path / "markers"
        markers_dir.mkdir(parents=True)
        (markers_dir / "clip_markers.json").write_text("NOTJSON", encoding="utf-8")
        result = _load_markers(tmp_path)
        assert result == []


# ---------------------------------------------------------------------------
# TestSelectSegments
# ---------------------------------------------------------------------------


class TestSelectSegments:
    def test_empty_ranked_returns_empty(self):
        assert _select_segments([], target_duration=60.0) == []

    def test_single_marker_selected(self):
        markers = [make_marker(start=0.0, end=5.0)]
        result = _select_segments(markers, target_duration=60.0)
        assert len(result) == 1

    def test_stops_when_target_duration_met(self):
        # Each marker is 5s + 2*2s padding = 9s; target=15 → 2 fill it
        markers = [make_marker(start=i * 20.0, end=i * 20.0 + 5.0) for i in range(3)]
        result = _select_segments(markers, target_duration=15.0, padding=2.0)
        assert len(result) <= 2

    def test_overlapping_markers_excluded(self):
        # Marker 0-5, padded 0-7; Marker 3-8, padded 1-10 → overlap
        m1 = make_marker(start=0.0, end=5.0)
        m2 = make_marker(start=3.0, end=8.0, confidence=0.5)
        result = _select_segments([m1, m2], target_duration=60.0, padding=2.0)
        assert len(result) == 1

    def test_non_overlapping_markers_both_selected(self):
        # Marker 0-5 padded to (-2→2, 5→7); Marker 10-15 padded to (8→12, 15→17)
        # Gap between 7 and 8: no overlap
        m1 = make_marker(start=0.0, end=5.0)
        m2 = make_marker(start=10.0, end=15.0)
        result = _select_segments([m1, m2], target_duration=100.0, padding=2.0)
        assert len(result) == 2

    def test_padding_clamped_to_zero(self):
        # start=0.5, padding=2.0 → padded_start = max(0, 0.5-2) = 0.0
        m = make_marker(start=0.5, end=5.0)
        result = _select_segments([m], target_duration=60.0, padding=2.0)
        assert len(result) == 1
        # The padded start is clamped; verify via occupied tuple (indirectly)


# ---------------------------------------------------------------------------
# TestApplyPadding
# ---------------------------------------------------------------------------


class TestApplyPadding:
    def test_results_sorted_chronologically(self):
        m1 = make_marker(start=20.0, end=25.0)
        m2 = make_marker(start=5.0, end=10.0)
        result = _apply_padding([m1, m2], padding=0.0)
        assert result[0][0] == 5.0  # first entry starts at 5.0

    def test_start_padded(self):
        m = make_marker(start=10.0, end=15.0)
        result = _apply_padding([m], padding=2.0)
        assert result[0][0] == 8.0

    def test_end_padded(self):
        m = make_marker(start=10.0, end=15.0)
        result = _apply_padding([m], padding=2.0)
        assert result[0][1] == 17.0


# ---------------------------------------------------------------------------
# TestMergeAdjacent
# ---------------------------------------------------------------------------


class TestMergeAdjacent:
    def test_empty_input_returns_empty(self):
        assert _merge_adjacent([]) == []

    def test_single_segment_returned_as_is(self):
        m = make_marker()
        result = _merge_adjacent([(0.0, 10.0, m)])
        assert len(result) == 1
        assert result[0][0] == 0.0
        assert result[0][1] == 10.0

    def test_gap_less_than_merge_threshold_merges(self):
        m1 = make_marker(start=0.0, end=10.0)
        m2 = make_marker(start=12.0, end=20.0)
        result = _merge_adjacent([(0.0, 10.0, m1), (12.0, 20.0, m2)], merge_gap=3.0)
        assert len(result) == 1
        assert result[0][0] == 0.0
        assert result[0][1] == 20.0

    def test_gap_equal_to_merge_threshold_does_not_merge(self):
        m1 = make_marker(start=0.0, end=10.0)
        m2 = make_marker(start=13.0, end=20.0)
        result = _merge_adjacent([(0.0, 10.0, m1), (13.0, 20.0, m2)], merge_gap=3.0)
        assert len(result) == 2

    def test_gap_larger_than_merge_threshold_not_merged(self):
        m1 = make_marker(start=0.0, end=10.0)
        m2 = make_marker(start=20.0, end=30.0)
        result = _merge_adjacent([(0.0, 10.0, m1), (20.0, 30.0, m2)], merge_gap=3.0)
        assert len(result) == 2

    def test_merged_segment_contains_all_source_markers(self):
        m1 = make_marker(start=0.0, end=10.0, reason="reason1")
        m2 = make_marker(start=11.0, end=20.0, reason="reason2")
        result = _merge_adjacent([(0.0, 10.0, m1), (11.0, 20.0, m2)], merge_gap=3.0)
        assert len(result) == 1
        assert len(result[0][2]) == 2


# ---------------------------------------------------------------------------
# TestGenerateReplay
# ---------------------------------------------------------------------------


class TestGenerateReplay:
    def test_no_markers_raises_value_error(self, tmp_path):
        with pytest.raises(ValueError, match="No markers found"):
            generate_replay(tmp_path)

    @patch(f"{REPLAY_MOD}.serialize_versioned")
    @patch(f"{REPLAY_MOD}._load_assets")
    def test_returns_path_on_success(self, mock_load_assets, mock_serialize, tmp_path):
        mock_load_assets.return_value = []
        expected = tmp_path / "replay_v1.kdenlive"
        mock_serialize.return_value = expected

        markers = [make_marker(start=0.0, end=5.0)]
        write_markers_json(tmp_path / "markers", "clip_markers.json", markers)

        result = generate_replay(tmp_path)
        assert result == expected

    @patch(f"{REPLAY_MOD}.serialize_versioned")
    @patch(f"{REPLAY_MOD}._load_assets")
    def test_serialize_versioned_called_once(self, mock_load_assets, mock_serialize, tmp_path):
        mock_load_assets.return_value = []
        mock_serialize.return_value = tmp_path / "replay_v1.kdenlive"

        write_markers_json(
            tmp_path / "markers", "clip_markers.json",
            [make_marker(start=0.0, end=5.0)]
        )

        generate_replay(tmp_path)
        mock_serialize.assert_called_once()

    @patch(f"{REPLAY_MOD}.serialize_versioned")
    @patch(f"{REPLAY_MOD}._load_assets")
    def test_producers_created_per_unique_clip_ref(self, mock_load_assets, mock_serialize, tmp_path):
        mock_load_assets.return_value = []
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "replay_v1.kdenlive"

        mock_serialize.side_effect = capture

        # Two markers with same clip_ref → one producer
        markers = [
            make_marker(start=0.0, end=5.0, clip_ref="/clip.mp4"),
            make_marker(start=20.0, end=25.0, clip_ref="/clip.mp4"),
        ]
        write_markers_json(tmp_path / "markers", "clip_markers.json", markers)
        generate_replay(tmp_path)
        assert len(captured["project"].producers) == 1

    @patch(f"{REPLAY_MOD}.serialize_versioned")
    @patch(f"{REPLAY_MOD}._load_assets")
    def test_guides_added_per_merged_segment(self, mock_load_assets, mock_serialize, tmp_path):
        mock_load_assets.return_value = []
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "replay_v1.kdenlive"

        mock_serialize.side_effect = capture

        # Two far-apart markers that do NOT merge
        markers = [
            make_marker(start=0.0, end=5.0, clip_ref="/clip1.mp4", reason="First"),
            make_marker(start=100.0, end=105.0, clip_ref="/clip2.mp4", reason="Second"),
        ]
        write_markers_json(tmp_path / "markers", "clip_markers.json", markers)
        generate_replay(tmp_path, target_duration=200.0)

        guide_labels = [g.label for g in captured["project"].guides]
        highlight_guides = [g for g in guide_labels if "Highlight:" in g]
        assert len(highlight_guides) == 2

    @patch(f"{REPLAY_MOD}.serialize_versioned")
    @patch(f"{REPLAY_MOD}._load_assets")
    def test_crossfade_added_between_multiple_segments(self, mock_load_assets, mock_serialize, tmp_path):
        mock_load_assets.return_value = []
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "replay_v1.kdenlive"

        mock_serialize.side_effect = capture

        markers = [
            make_marker(start=0.0, end=5.0, clip_ref="/clip1.mp4"),
            make_marker(start=100.0, end=105.0, clip_ref="/clip2.mp4"),
        ]
        write_markers_json(tmp_path / "markers", "clip_markers.json", markers)
        generate_replay(tmp_path, target_duration=200.0)

        assert len(captured["project"].opaque_elements) >= 1

    @patch(f"{REPLAY_MOD}.serialize_versioned")
    @patch(f"{REPLAY_MOD}._load_assets")
    def test_no_crossfade_for_single_segment(self, mock_load_assets, mock_serialize, tmp_path):
        mock_load_assets.return_value = []
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "replay_v1.kdenlive"

        mock_serialize.side_effect = capture

        markers = [make_marker(start=0.0, end=5.0, clip_ref="/clip1.mp4")]
        write_markers_json(tmp_path / "markers", "clip_markers.json", markers)
        generate_replay(tmp_path)

        assert captured["project"].opaque_elements == []

    @patch(f"{REPLAY_MOD}.serialize_versioned")
    @patch(f"{REPLAY_MOD}._load_assets")
    def test_target_duration_respected(self, mock_load_assets, mock_serialize, tmp_path):
        mock_load_assets.return_value = []
        captured = {}

        def capture(project, *args, **kwargs):
            captured["project"] = project
            return tmp_path / "replay_v1.kdenlive"

        mock_serialize.side_effect = capture

        # 10 markers × 5s each, spread far apart (no merging), target=20s
        markers = [
            make_marker(start=i * 30.0, end=i * 30.0 + 5.0, clip_ref=f"/clip{i}.mp4")
            for i in range(10)
        ]
        write_markers_json(tmp_path / "markers", "clip_markers.json", markers)
        generate_replay(tmp_path, target_duration=20.0)

        # Should not have all 10 producers
        assert len(captured["project"].producers) <= 5
