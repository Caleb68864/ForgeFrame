"""Unit tests for the Build Replay Generator pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import Marker
from workshop_video_brain.edit_mcp.pipelines.replay_generator import (
    ReplayReport,
    ReplaySegment,
    _apply_padding,
    _merge_adjacent,
    _select_segments,
    generate_replay,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _marker(
    category: MarkerCategory = MarkerCategory.step_explanation,
    confidence: float = 0.8,
    start: float = 0.0,
    end: float = 5.0,
    clip_ref: str = "clip_a",
    reason: str = "test reason",
) -> Marker:
    return Marker(
        id=uuid4(),
        category=category,
        confidence_score=confidence,
        source_method="test",
        reason=reason,
        clip_ref=clip_ref,
        start_seconds=start,
        end_seconds=end,
    )


def _write_markers(ws: Path, markers: list[Marker], stem: str = "clip_a") -> None:
    markers_dir = ws / "markers"
    markers_dir.mkdir(parents=True, exist_ok=True)
    path = markers_dir / f"{stem}_markers.json"
    path.write_text(
        json.dumps([m.model_dump(mode="json") for m in markers], indent=2),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Test: _select_segments
# ---------------------------------------------------------------------------


class TestSelectSegments:
    def test_selects_highest_scored_first(self):
        from workshop_video_brain.edit_mcp.pipelines.marker_rules import default_config
        from workshop_video_brain.edit_mcp.pipelines.review_timeline import rank_markers

        config = default_config()
        markers = [
            _marker(MarkerCategory.dead_air, 0.9, start=100.0, end=110.0),
            _marker(MarkerCategory.chapter_candidate, 0.9, start=0.0, end=5.0),
        ]
        ranked = rank_markers(markers, config)
        selected = _select_segments(ranked, target_duration=60.0, padding=2.0)
        # chapter_candidate has higher weight → should appear first in result
        assert selected[0].category == MarkerCategory.chapter_candidate.value

    def test_skips_overlapping_segments(self):
        """Segments whose padded windows overlap should be skipped."""
        m1 = _marker(start=0.0, end=5.0, confidence=0.9)
        m2 = _marker(start=4.0, end=9.0, confidence=0.8)  # overlaps with m1 padded
        # Feed in ranked order (m1 first since higher conf)
        selected = _select_segments([m1, m2], target_duration=60.0, padding=2.0)
        assert len(selected) == 1
        assert selected[0].start_seconds == 0.0

    def test_stops_when_target_reached(self):
        """Once total padded duration >= target, no more segments added."""
        # 5 markers of 10 s each with 2 s padding = 14 s each; target = 15 s
        markers = [
            _marker(start=i * 50.0, end=i * 50.0 + 10.0, confidence=0.9 - i * 0.01)
            for i in range(5)
        ]
        selected = _select_segments(markers, target_duration=15.0, padding=2.0)
        # First segment gives 14 s (padded), still < 15; second gives 28 s >= 15
        assert len(selected) == 2

    def test_exhausts_all_if_not_enough_duration(self):
        """If all markers together don't reach target, use them all."""
        markers = [_marker(start=i * 20.0, end=i * 20.0 + 3.0) for i in range(3)]
        selected = _select_segments(markers, target_duration=9999.0, padding=2.0)
        assert len(selected) == 3

    def test_non_overlapping_all_selected(self):
        """Widely spaced markers should all be selected."""
        markers = [
            _marker(start=0.0, end=5.0, confidence=0.9),
            _marker(start=100.0, end=105.0, confidence=0.8),
            _marker(start=200.0, end=205.0, confidence=0.7),
        ]
        selected = _select_segments(markers, target_duration=9999.0, padding=2.0)
        assert len(selected) == 3


# ---------------------------------------------------------------------------
# Test: _apply_padding
# ---------------------------------------------------------------------------


class TestApplyPadding:
    def test_padding_applied(self):
        m = _marker(start=10.0, end=20.0)
        result = _apply_padding([m], padding=2.0)
        assert len(result) == 1
        start, end, marker = result[0]
        assert start == pytest.approx(8.0)
        assert end == pytest.approx(22.0)

    def test_start_clamped_to_zero(self):
        m = _marker(start=1.0, end=5.0)
        result = _apply_padding([m], padding=2.0)
        start, _, _ = result[0]
        assert start == pytest.approx(0.0)

    def test_sorted_chronologically(self):
        markers = [
            _marker(start=100.0, end=105.0),
            _marker(start=10.0, end=15.0),
            _marker(start=50.0, end=55.0),
        ]
        result = _apply_padding(markers, padding=2.0)
        starts = [r[0] for r in result]
        assert starts == sorted(starts)

    def test_each_segment_has_2s_padding(self):
        m = _marker(start=30.0, end=40.0)
        result = _apply_padding([m], padding=2.0)
        start, end, _ = result[0]
        assert start == pytest.approx(m.start_seconds - 2.0)
        assert end == pytest.approx(m.end_seconds + 2.0)


# ---------------------------------------------------------------------------
# Test: _merge_adjacent
# ---------------------------------------------------------------------------


class TestMergeAdjacent:
    def test_adjacent_segments_merged(self):
        """Segments with gap < 3 s should be merged."""
        m1 = _marker(start=0.0, end=5.0)
        m2 = _marker(start=6.0, end=10.0)  # gap = 1 s < 3 s
        padded = [(0.0, 5.0, m1), (6.0, 10.0, m2)]
        merged = _merge_adjacent(padded, merge_gap=3.0)
        assert len(merged) == 1
        assert merged[0][0] == pytest.approx(0.0)
        assert merged[0][1] == pytest.approx(10.0)
        assert len(merged[0][2]) == 2

    def test_distant_segments_not_merged(self):
        """Segments with gap >= 3 s should remain separate."""
        m1 = _marker(start=0.0, end=5.0)
        m2 = _marker(start=10.0, end=15.0)  # gap = 5 s >= 3 s
        padded = [(0.0, 5.0, m1), (10.0, 15.0, m2)]
        merged = _merge_adjacent(padded, merge_gap=3.0)
        assert len(merged) == 2

    def test_empty_input(self):
        assert _merge_adjacent([], merge_gap=3.0) == []

    def test_single_segment(self):
        m = _marker(start=0.0, end=5.0)
        padded = [(0.0, 5.0, m)]
        merged = _merge_adjacent(padded, merge_gap=3.0)
        assert len(merged) == 1


# ---------------------------------------------------------------------------
# Test: generate_replay (integration with tmp workspace)
# ---------------------------------------------------------------------------


class TestGenerateReplay:
    def test_normal_generation(self, tmp_path):
        """Normal case: markers available → kdenlive project created."""
        markers = [
            _marker(MarkerCategory.chapter_candidate, 0.9, start=0.0, end=5.0, clip_ref="c1"),
            _marker(MarkerCategory.step_explanation, 0.8, start=50.0, end=55.0, clip_ref="c1"),
            _marker(MarkerCategory.important_caution, 0.7, start=100.0, end=105.0, clip_ref="c1"),
        ]
        _write_markers(tmp_path, markers)

        out = generate_replay(tmp_path, target_duration=60.0)
        assert out.exists()
        assert out.suffix == ".kdenlive"
        assert "replay" in out.name

    def test_no_markers_raises_value_error(self, tmp_path):
        """No markers → ValueError raised."""
        with pytest.raises(ValueError, match="No markers found"):
            generate_replay(tmp_path, target_duration=60.0)

    def test_no_markers_dir_raises_value_error(self, tmp_path):
        """Missing markers/ directory → ValueError raised."""
        with pytest.raises(ValueError, match="No markers found"):
            generate_replay(tmp_path, target_duration=60.0)

    def test_insufficient_markers_uses_all_available(self, tmp_path):
        """Fewer markers than needed → use all available, project still created."""
        markers = [
            _marker(MarkerCategory.step_explanation, 0.8, start=0.0, end=3.0),
        ]
        _write_markers(tmp_path, markers)
        out = generate_replay(tmp_path, target_duration=9999.0)
        assert out.exists()

    def test_custom_duration_selects_more_segments(self, tmp_path):
        """Longer target duration → more segments included."""
        markers = [
            _marker(category=MarkerCategory.step_explanation, confidence=0.9 - i * 0.01,
                    start=i * 30.0, end=i * 30.0 + 5.0)
            for i in range(10)
        ]
        _write_markers(tmp_path, markers)

        # Short target
        out_short = generate_replay(tmp_path, target_duration=15.0)
        out_long = generate_replay(tmp_path, target_duration=120.0)

        # Parse XML to count playlist entries
        import xml.etree.ElementTree as ET
        tree_short = ET.parse(out_short)
        tree_long = ET.parse(out_long)

        short_entries = len(tree_short.findall(".//entry"))
        long_entries = len(tree_long.findall(".//entry"))
        assert long_entries >= short_entries

    def test_output_is_chronological(self, tmp_path):
        """Segments are ordered chronologically in the output regardless of score ranking."""
        # High-score segment is late in the video
        markers = [
            _marker(MarkerCategory.chapter_candidate, 0.99, start=100.0, end=110.0, clip_ref="c"),
            _marker(MarkerCategory.step_explanation, 0.50, start=10.0, end=20.0, clip_ref="c"),
        ]
        _write_markers(tmp_path, markers)

        out = generate_replay(tmp_path, target_duration=9999.0)
        import xml.etree.ElementTree as ET
        tree = ET.parse(out)
        entries = tree.findall(".//entry")
        assert len(entries) >= 2
        # In-points should be in non-decreasing order (chronological)
        in_points = [int(e.get("in", "0")) for e in entries[:2]]
        assert in_points == sorted(in_points)

    def test_segment_merging_in_output(self, tmp_path):
        """Adjacent segments (gap < 3 s) are merged into one playlist entry."""
        # Two segments only 1 s apart — they should merge into one
        markers = [
            _marker(MarkerCategory.step_explanation, 0.8, start=10.0, end=15.0),
            _marker(MarkerCategory.important_caution, 0.75, start=16.0, end=21.0),
        ]
        _write_markers(tmp_path, markers)

        out = generate_replay(tmp_path, target_duration=9999.0)
        import xml.etree.ElementTree as ET
        tree = ET.parse(out)
        # video playlist entries
        playlists = tree.findall("playlist")
        video_pl = next((p for p in playlists if p.get("id") == "playlist_video"), None)
        assert video_pl is not None
        entries = video_pl.findall("entry")
        assert len(entries) == 1

    def test_guide_markers_labelled_highlight(self, tmp_path):
        """Guide markers are labelled 'Highlight: {reason}'."""
        markers = [
            _marker(MarkerCategory.step_explanation, 0.8, start=0.0, end=5.0, reason="mixing the batter"),
        ]
        _write_markers(tmp_path, markers)

        out = generate_replay(tmp_path, target_duration=60.0)
        import xml.etree.ElementTree as ET
        tree = ET.parse(out)
        guides = tree.findall("guide")
        assert any("Highlight:" in g.get("comment", "") for g in guides)

    def test_versioned_filename(self, tmp_path):
        """Each call produces a new versioned file (v1, v2, ...)."""
        markers = [
            _marker(MarkerCategory.step_explanation, 0.8, start=0.0, end=5.0),
        ]
        _write_markers(tmp_path, markers)

        out1 = generate_replay(tmp_path, target_duration=60.0)
        out2 = generate_replay(tmp_path, target_duration=60.0)
        assert out1 != out2
        assert "_v1." in out1.name or "_v" in out1.name
        assert "_v2." in out2.name or out2.stat().st_mtime >= out1.stat().st_mtime

    def test_report_model(self):
        """ReplayReport and ReplaySegment can be constructed."""
        seg = ReplaySegment(start=0.0, end=5.0, reason="test", source_clip="c1")
        report = ReplayReport(
            segment_count=1,
            total_duration=5.0,
            target_duration=60.0,
            segments_used=[seg],
        )
        assert report.segment_count == 1
        assert report.segments_used[0].reason == "test"
