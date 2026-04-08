"""Unit tests for clip_search pipeline."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.clips import ClipLabel
from workshop_video_brain.edit_mcp.pipelines.clip_search import _score_label, search_clips


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_label(
    clip_ref: str = "test_clip",
    content_type: str = "tutorial_step",
    topics: list[str] | None = None,
    summary: str = "",
    tags: list[str] | None = None,
    shot_type: str = "medium",
    has_speech: bool = True,
    speech_density: float = 0.7,
    duration: float = 30.0,
    source_path: str = "",
) -> ClipLabel:
    return ClipLabel(
        clip_ref=clip_ref,
        content_type=content_type,
        topics=topics or [],
        summary=summary,
        tags=tags or [],
        shot_type=shot_type,
        has_speech=has_speech,
        speech_density=speech_density,
        duration=duration,
        source_path=source_path,
    )


def _write_label(clips_dir: Path, label: ClipLabel) -> None:
    out_path = clips_dir / f"{label.clip_ref}_label.json"
    out_path.write_text(label.to_json(), encoding="utf-8")


def _setup_clips_dir(tmp_path: Path) -> Path:
    clips_dir = tmp_path / "clips"
    clips_dir.mkdir()
    return clips_dir


# ---------------------------------------------------------------------------
# Test: _score_label
# ---------------------------------------------------------------------------


class TestScoreLabel:
    def test_exact_tag_match_scores_one(self):
        label = _make_label(tags=["tutorial_step", "closeup", "wood"])
        score = _score_label(label, ["wood"])
        assert score >= 1.0

    def test_topic_contains_query_word_scores_point_eight(self):
        label = _make_label(topics=["woodworking", "table"], tags=[])
        score = _score_label(label, ["woodworking"])
        # tag match won't fire, but topic match should
        assert score >= 0.8

    def test_summary_contains_query_word_scores_point_five(self):
        label = _make_label(summary="We are cutting the board carefully", tags=[], topics=[])
        score = _score_label(label, ["cutting"])
        assert score >= 0.5

    def test_content_type_match_scores_point_eight(self):
        label = _make_label(content_type="tutorial_step", tags=[], topics=[], summary="")
        score = _score_label(label, ["tutorial"])
        assert score >= 0.8

    def test_no_match_returns_zero(self):
        label = _make_label(
            content_type="b_roll",
            topics=["exterior", "landscape"],
            summary="Wide shot of the garden",
            tags=["b_roll", "medium", "exterior"],
        )
        score = _score_label(label, ["soldering"])
        assert score == 0.0

    def test_multiple_words_accumulate_score(self):
        label = _make_label(
            tags=["wood", "cutting"],
            topics=["woodworking"],
            summary="We are cutting wood",
        )
        score_single = _score_label(label, ["wood"])
        score_multi = _score_label(label, ["wood", "cutting"])
        assert score_multi > score_single

    def test_case_insensitive_matching(self):
        label = _make_label(
            tags=["wood"],
            topics=["Woodworking"],
            summary="WOOD is used here",
        )
        score_lower = _score_label(label, ["wood"])
        score_upper = _score_label(label, ["WOOD"])
        assert score_lower == score_upper


# ---------------------------------------------------------------------------
# Test: search_clips
# ---------------------------------------------------------------------------


class TestSearchClips:
    def test_returns_empty_for_missing_clips_dir(self, tmp_path):
        results = search_clips(tmp_path, "wood")
        assert results == []

    def test_returns_empty_for_empty_clips_dir(self, tmp_path):
        _setup_clips_dir(tmp_path)
        results = search_clips(tmp_path, "wood")
        assert results == []

    def test_exact_tag_match_returns_result(self, tmp_path):
        clips_dir = _setup_clips_dir(tmp_path)
        label = _make_label(
            clip_ref="clip01",
            tags=["woodworking", "tutorial_step", "medium"],
        )
        _write_label(clips_dir, label)

        results = search_clips(tmp_path, "woodworking")
        assert len(results) == 1
        assert results[0]["clip_ref"] == "clip01"
        assert results[0]["score"] >= 1.0

    def test_no_match_returns_empty_list(self, tmp_path):
        clips_dir = _setup_clips_dir(tmp_path)
        label = _make_label(
            clip_ref="clip01",
            content_type="b_roll",
            tags=["b_roll", "exterior"],
            topics=["landscape"],
            summary="Wide outdoor shot",
        )
        _write_label(clips_dir, label)

        results = search_clips(tmp_path, "soldering")
        assert results == []

    def test_results_sorted_descending_by_score(self, tmp_path):
        clips_dir = _setup_clips_dir(tmp_path)
        # clip_high has more matching tags
        label_high = _make_label(
            clip_ref="clip_high",
            tags=["wood", "cutting", "tutorial_step"],
            topics=["woodworking"],
            summary="Cutting wood on the table",
        )
        label_low = _make_label(
            clip_ref="clip_low",
            tags=["material"],
            topics=["stone"],
            summary="Stone carving technique",
        )
        _write_label(clips_dir, label_high)
        _write_label(clips_dir, label_low)

        results = search_clips(tmp_path, "wood cutting")
        assert len(results) >= 1
        # Scores should be descending
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)
        # clip_high should rank above clip_low
        clip_refs = [r["clip_ref"] for r in results]
        if "clip_high" in clip_refs and "clip_low" in clip_refs:
            assert clip_refs.index("clip_high") < clip_refs.index("clip_low")

    def test_malformed_json_skipped_gracefully(self, tmp_path):
        clips_dir = _setup_clips_dir(tmp_path)
        # Write a good label
        label = _make_label(
            clip_ref="good_clip",
            tags=["wood"],
        )
        _write_label(clips_dir, label)
        # Write a bad label
        (clips_dir / "bad_clip_label.json").write_text(
            "{invalid json {{{{", encoding="utf-8"
        )

        # Should not raise, just skip the bad one
        results = search_clips(tmp_path, "wood")
        assert len(results) == 1
        assert results[0]["clip_ref"] == "good_clip"

    def test_query_normalization_case_insensitive(self, tmp_path):
        clips_dir = _setup_clips_dir(tmp_path)
        label = _make_label(
            clip_ref="clip01",
            tags=["woodworking", "tutorial_step"],
        )
        _write_label(clips_dir, label)

        results_lower = search_clips(tmp_path, "woodworking")
        results_upper = search_clips(tmp_path, "WOODWORKING")
        results_mixed = search_clips(tmp_path, "WoodWorking")

        assert len(results_lower) == len(results_upper) == len(results_mixed) == 1
        assert results_lower[0]["score"] == results_upper[0]["score"] == results_mixed[0]["score"]

    def test_result_contains_expected_fields(self, tmp_path):
        clips_dir = _setup_clips_dir(tmp_path)
        label = _make_label(
            clip_ref="clip01",
            content_type="tutorial_step",
            topics=["woodworking"],
            summary="Building a table",
            tags=["woodworking"],
            source_path="/some/path.mp4",
            duration=45.0,
        )
        _write_label(clips_dir, label)

        results = search_clips(tmp_path, "woodworking")
        assert len(results) == 1
        r = results[0]
        assert "clip_ref" in r
        assert "content_type" in r
        assert "topics" in r
        assert "summary" in r
        assert "score" in r
        assert "source_path" in r
        assert "duration" in r

    def test_multiple_clips_all_matching_returns_all(self, tmp_path):
        clips_dir = _setup_clips_dir(tmp_path)
        for i in range(3):
            label = _make_label(
                clip_ref=f"clip_{i:02d}",
                tags=["wood"],
                topics=["woodworking"],
            )
            _write_label(clips_dir, label)

        results = search_clips(tmp_path, "wood")
        assert len(results) == 3

    def test_topic_partial_match_scoring(self, tmp_path):
        clips_dir = _setup_clips_dir(tmp_path)
        label = _make_label(
            clip_ref="clip01",
            topics=["woodworking"],
            tags=[],
            summary="",
        )
        _write_label(clips_dir, label)

        results = search_clips(tmp_path, "wood")
        # "wood" is in "woodworking" → topic partial match
        assert len(results) == 1
        assert results[0]["score"] >= 0.8
