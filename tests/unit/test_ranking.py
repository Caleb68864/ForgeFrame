"""Unit tests for review_timeline ranking and selects_timeline export."""
from __future__ import annotations

import json
from uuid import UUID

import pytest

from workshop_video_brain.core.models.enums import MarkerCategory
from workshop_video_brain.core.models.markers import Marker, MarkerConfig
from workshop_video_brain.edit_mcp.pipelines.marker_rules import default_config
from workshop_video_brain.edit_mcp.pipelines.review_timeline import (
    chronological_order,
    group_by_clip,
    rank_markers,
)
from workshop_video_brain.edit_mcp.pipelines.selects_timeline import (
    SelectsEntry,
    build_selects,
    selects_to_json,
    selects_to_markdown,
)


def _marker(
    category: MarkerCategory,
    confidence: float,
    start: float = 0.0,
    end: float = 5.0,
    clip_ref: str = "clip_a",
    reason: str = "test",
) -> Marker:
    return Marker(
        category=category,
        confidence_score=confidence,
        source_method="test",
        reason=reason,
        clip_ref=clip_ref,
        start_seconds=start,
        end_seconds=end,
    )


class TestRankMarkers:
    def test_ranked_order_by_score(self):
        config = default_config()
        markers = [
            _marker(MarkerCategory.dead_air, 1.0),         # weight 0.3 → score 0.30
            _marker(MarkerCategory.chapter_candidate, 0.9), # weight 1.0 → score 0.90
            _marker(MarkerCategory.step_explanation, 0.8),  # weight 0.9 → score 0.72
            _marker(MarkerCategory.important_caution, 0.7), # weight 0.8 → score 0.56
        ]
        ranked = rank_markers(markers, config)
        scores = [
            ranked[i].confidence_score * config.category_weights.get(str(ranked[i].category), 0.5)
            for i in range(len(ranked))
        ]
        assert scores == sorted(scores, reverse=True)

    def test_highest_ranked_is_chapter_candidate(self):
        config = default_config()
        markers = [
            _marker(MarkerCategory.dead_air, 0.95),
            _marker(MarkerCategory.chapter_candidate, 0.9),
            _marker(MarkerCategory.repetition, 1.0),
        ]
        ranked = rank_markers(markers, config)
        assert str(ranked[0].category) == MarkerCategory.chapter_candidate.value

    def test_empty_markers_returns_empty(self):
        config = default_config()
        assert rank_markers([], config) == []

    def test_single_marker_unchanged(self):
        config = default_config()
        m = _marker(MarkerCategory.hook_candidate, 0.8)
        result = rank_markers([m], config)
        assert len(result) == 1

    def test_missing_category_weight_defaults_to_half(self):
        """A category not in weights should use 0.5."""
        config = default_config()
        # Remove one category from weights to test default
        weights = dict(config.category_weights)
        weights.pop("intro_candidate", None)
        custom_config = MarkerConfig(
            rules=config.rules,
            category_weights=weights,
        )
        m = _marker(MarkerCategory.intro_candidate, 1.0)
        ranked = rank_markers([m], custom_config)
        assert len(ranked) == 1


class TestChronologicalOrder:
    def test_sorted_by_start_seconds(self):
        markers = [
            _marker(MarkerCategory.step_explanation, 0.8, start=30.0),
            _marker(MarkerCategory.hook_candidate, 0.9, start=0.5),
            _marker(MarkerCategory.ending_reveal, 0.75, start=160.0),
            _marker(MarkerCategory.chapter_candidate, 0.85, start=60.0),
        ]
        ordered = chronological_order(markers)
        starts = [m.start_seconds for m in ordered]
        assert starts == sorted(starts)

    def test_empty_returns_empty(self):
        assert chronological_order([]) == []


class TestGroupByClip:
    def test_groups_by_clip_ref(self):
        markers = [
            _marker(MarkerCategory.step_explanation, 0.8, clip_ref="clip_a"),
            _marker(MarkerCategory.hook_candidate, 0.9, clip_ref="clip_b"),
            _marker(MarkerCategory.ending_reveal, 0.75, clip_ref="clip_a"),
            _marker(MarkerCategory.chapter_candidate, 0.85, clip_ref="clip_c"),
        ]
        groups = group_by_clip(markers)
        assert set(groups.keys()) == {"clip_a", "clip_b", "clip_c"}
        assert len(groups["clip_a"]) == 2
        assert len(groups["clip_b"]) == 1
        assert len(groups["clip_c"]) == 1

    def test_empty_returns_empty_dict(self):
        assert group_by_clip([]) == {}

    def test_multi_clip_all_present(self):
        markers = [
            _marker(MarkerCategory.step_explanation, 0.8, clip_ref="A"),
            _marker(MarkerCategory.step_explanation, 0.8, clip_ref="B"),
            _marker(MarkerCategory.step_explanation, 0.8, clip_ref="C"),
        ]
        groups = group_by_clip(markers)
        assert len(groups) == 3


class TestBuildSelects:
    def test_filters_by_min_confidence(self):
        config = default_config()
        markers = [
            _marker(MarkerCategory.step_explanation, 0.8),
            _marker(MarkerCategory.chapter_candidate, 0.3),  # below 0.5
            _marker(MarkerCategory.important_caution, 0.6),
        ]
        selects = build_selects(markers, config, min_confidence=0.5)
        assert all(e.marker.confidence_score >= 0.5 for e in selects)
        assert len(selects) == 2

    def test_excludes_dead_air(self):
        config = default_config()
        markers = [
            _marker(MarkerCategory.dead_air, 1.0),
            _marker(MarkerCategory.step_explanation, 0.8),
        ]
        selects = build_selects(markers, config)
        cats = {str(e.marker.category) for e in selects}
        assert MarkerCategory.dead_air.value not in cats

    def test_excludes_repetition(self):
        config = default_config()
        markers = [
            _marker(MarkerCategory.repetition, 1.0),
            _marker(MarkerCategory.chapter_candidate, 0.9),
        ]
        selects = build_selects(markers, config)
        cats = {str(e.marker.category) for e in selects}
        assert MarkerCategory.repetition.value not in cats

    def test_usefulness_score_is_confidence_times_weight(self):
        config = default_config()
        m = _marker(MarkerCategory.chapter_candidate, 0.9)
        selects = build_selects([m], config)
        assert len(selects) == 1
        expected = 0.9 * config.category_weights["chapter_candidate"]
        assert abs(selects[0].usefulness_score - expected) < 1e-6

    def test_sorted_best_first(self):
        config = default_config()
        markers = [
            _marker(MarkerCategory.dead_air, 1.0),         # excluded
            _marker(MarkerCategory.step_explanation, 0.8),  # 0.8*0.9=0.72
            _marker(MarkerCategory.chapter_candidate, 0.7), # 0.7*1.0=0.70
            _marker(MarkerCategory.important_caution, 0.9), # 0.9*0.8=0.72
        ]
        selects = build_selects(markers, config)
        scores = [e.usefulness_score for e in selects]
        assert scores == sorted(scores, reverse=True)

    def test_empty_markers_returns_empty(self):
        config = default_config()
        assert build_selects([], config) == []

    def test_all_excluded_returns_empty(self):
        config = default_config()
        markers = [
            _marker(MarkerCategory.dead_air, 1.0),
            _marker(MarkerCategory.repetition, 1.0),
        ]
        assert build_selects(markers, config) == []


class TestSelectsToJson:
    def test_valid_json_array(self):
        config = default_config()
        markers = [
            _marker(MarkerCategory.chapter_candidate, 0.9, start=10.0, end=15.0),
            _marker(MarkerCategory.step_explanation, 0.8, start=20.0, end=25.0),
        ]
        selects = build_selects(markers, config)
        result = selects_to_json(selects)
        parsed = json.loads(result)
        assert isinstance(parsed, list)
        assert len(parsed) == 2

    def test_json_contains_required_fields(self):
        config = default_config()
        m = _marker(MarkerCategory.chapter_candidate, 0.9, start=5.0, end=10.0, reason="test reason")
        selects = build_selects([m], config)
        result = selects_to_json(selects)
        parsed = json.loads(result)
        entry = parsed[0]
        assert "clip_ref" in entry
        assert "start_seconds" in entry
        assert "end_seconds" in entry
        assert "reason" in entry
        assert "usefulness_score" in entry
        assert "marker" in entry

    def test_empty_selects_produces_empty_array(self):
        result = selects_to_json([])
        assert json.loads(result) == []


class TestSelectsToMarkdown:
    def test_has_header_row(self):
        result = selects_to_markdown([])
        assert "| Time |" in result
        assert "| Category |" in result
        assert "| Reason |" in result
        assert "| Score |" in result

    def test_has_separator_row(self):
        result = selects_to_markdown([])
        assert "| --- |" in result

    def test_rows_match_selects_count(self):
        config = default_config()
        markers = [
            _marker(MarkerCategory.chapter_candidate, 0.9, start=10.0, end=15.0),
            _marker(MarkerCategory.step_explanation, 0.8, start=20.0, end=25.0),
            _marker(MarkerCategory.important_caution, 0.7, start=30.0, end=35.0),
        ]
        selects = build_selects(markers, config)
        result = selects_to_markdown(selects)
        lines = [l for l in result.strip().split("\n") if l.startswith("|")]
        # 1 header + 1 separator + N data rows
        assert len(lines) == 2 + len(selects)

    def test_time_format_in_rows(self):
        config = default_config()
        m = _marker(MarkerCategory.chapter_candidate, 0.9, start=10.5, end=15.2)
        selects = build_selects([m], config)
        result = selects_to_markdown(selects)
        assert "10.5s" in result
        assert "15.2s" in result

    def test_category_name_in_rows(self):
        config = default_config()
        m = _marker(MarkerCategory.chapter_candidate, 0.9, start=10.0, end=15.0)
        selects = build_selects([m], config)
        result = selects_to_markdown(selects)
        assert "chapter_candidate" in result
