---
scenario_id: "PL-07"
title: "Review Timeline"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario PL-07: Review Timeline

## Description
Tests `build_review_timeline`, `rank_markers`, `chronological_order`,
`generate_chapter_markers`, and `export_chapters_to_markdown` from
`review_timeline.py`. The pipeline builds a `KdenliveProject` from a list of
`Marker` objects, ordering them by confidence (ranked) or time (chronological),
and serializes it with `serialize_versioned`. A companion markdown review report
is also written. Covers: empty marker list, ranked vs chronological ordering,
asset resolution, guide label formatting, chapter marker filtering, markdown
chapter export, and the `_write_review_report` side effect.

## Preconditions
- `workshop-video-brain` installed in editable mode
- `tmp_path` provides workspace root
- `serialize_versioned` patched to return a deterministic `Path` and avoid
  actual file I/O
- `Marker`, `MarkerConfig`, `MarkerCategory` imported from core models
- `MediaAsset` available for asset-map tests

## Test Cases

```
tests/unit/test_review_timeline.py

from unittest.mock import patch, MagicMock
import uuid
from pathlib import Path

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_marker(start, end, confidence=0.8, category="step_explanation",
                clip_ref="/fake/clip.mp4", reason="reason", label=None)
    # Returns a Marker instance

def make_config(weights=None)
    # Returns a MarkerConfig with provided or default category_weights

# ── rank_markers ──────────────────────────────────────────────────────────────

class TestRankMarkers:
    def test_empty_list_returns_empty()
        # rank_markers([], config) == []

    def test_single_marker_returned()
        # rank_markers([marker], config) == [marker]

    def test_markers_sorted_by_score_descending()
        # marker_a: confidence=0.9, category weight=1.0 → score=0.9
        # marker_b: confidence=0.5, category weight=1.0 → score=0.5
        # result[0] is marker_a

    def test_missing_category_defaults_to_0_5_weight()
        # Marker with category not in config.category_weights
        # score == confidence_score * 0.5

    def test_equal_score_preserves_stable_sort_order()
        # Two markers with identical score — both present in result

# ── chronological_order ───────────────────────────────────────────────────────

class TestChronologicalOrder:
    def test_empty_list_returns_empty()
        # chronological_order([]) == []

    def test_single_marker_returned()
        # chronological_order([marker]) == [marker]

    def test_markers_sorted_by_start_seconds_ascending()
        # markers at t=30, t=5, t=15 → sorted [5, 15, 30]

    def test_original_list_not_mutated()
        # Original list order unchanged after chronological_order call

# ── generate_chapter_markers ──────────────────────────────────────────────────

class TestGenerateChapterMarkers:
    def test_empty_list_returns_empty()
        # generate_chapter_markers([]) == []

    def test_non_chapter_markers_excluded()
        # Markers with category != "chapter_candidate" → [] returned

    def test_chapter_candidate_converted_to_guide()
        # Marker(category=chapter_candidate, start_seconds=60.0, suggested_label="Intro")
        # result[0].label == "Intro"
        # result[0].position == 60 * 25 == 1500
        # result[0].category == "chapter"

    def test_reason_used_when_no_suggested_label()
        # Marker with suggested_label=None, reason="My Reason"
        # guide.label == "My Reason"

    def test_fallback_label_when_both_none()
        # Marker with suggested_label=None, reason=None
        # guide.label == "Chapter"

# ── export_chapters_to_markdown ───────────────────────────────────────────────

class TestExportChaptersToMarkdown:
    def test_empty_chapters_returns_no_chapters_message()
        # export_chapters_to_markdown([]) == "# Chapters\n\n_No chapters found._\n"

    def test_single_chapter_formatted()
        # Guide(position=0, label="Intro", category="chapter")
        # result contains "00:00:00" and "Intro"

    def test_chapters_sorted_by_position()
        # Guides at positions 2500, 500 → position 500 appears first in output

    def test_timestamp_conversion_correct()
        # position=3750, fps=25.0 → 3750/25 = 150s = 00:02:30
        # output contains "00:02:30"

    def test_custom_fps()
        # position=300, fps=30.0 → 300/30 = 10s → "00:00:10"

    def test_output_starts_with_chapters_heading()
        # "# Chapters" is first line

# ── build_review_timeline ─────────────────────────────────────────────────────

class TestBuildReviewTimeline:
    def test_returns_path_to_kdenlive_file(tmp_path)
        # Patch serialize_versioned → returns tmp_path/"review_timeline_v1.kdenlive"
        # build_review_timeline([marker], [], tmp_path) returns that Path

    def test_ranked_mode_orders_by_confidence(tmp_path)
        # Two markers with different confidences
        # Patched serialize_versioned receives project; check producers order matches
        # highest-confidence marker first

    def test_chronological_mode_orders_by_start_seconds(tmp_path)
        # markers at t=30 and t=5; mode="chronological"
        # First PlaylistEntry corresponds to t=5 marker

    def test_empty_markers_creates_empty_project(tmp_path)
        # build_review_timeline([], [], tmp_path)
        # serialize_versioned called with project having no producers/playlists entries

    def test_asset_resolved_by_clip_ref(tmp_path)
        # MediaAsset with path=="/real/path.mp4"
        # Marker with clip_ref=="/real/path.mp4"
        # Producer.resource == "/real/path.mp4"

    def test_unknown_clip_ref_uses_clip_ref_as_resource(tmp_path)
        # No matching MediaAsset for clip_ref
        # Producer.resource == clip_ref

    def test_guide_label_includes_category_reason_and_confidence(tmp_path)
        # Marker(category=step_explanation, reason="saw the cut", confidence=0.85)
        # guide.label contains "step_explanation", "saw the cut", "0.85"

    def test_review_report_markdown_written(tmp_path)
        # After build_review_timeline, tmp_path/reports/ contains a .md file

    def test_duplicate_clip_refs_reuse_same_producer(tmp_path)
        # Two markers with identical clip_ref → one producer, two playlist entries

    def test_in_out_points_match_marker_timestamps(tmp_path)
        # Marker at start=10.0, end=20.0, fps=25
        # in_point == 250, out_point == 500
```

## Steps
1. Read source module to understand current API
2. Create test file at `tests/unit/test_review_timeline.py`
3. Implement test cases with mocked dependencies
4. Run: `uv run pytest tests/unit/test_review_timeline.py -v`

## Expected Results
- `rank_markers` sorts by `confidence_score * category_weight` descending, with
  unknown categories defaulting to weight 0.5
- `chronological_order` sorts by `start_seconds` ascending without mutating input
- `generate_chapter_markers` filters to `MarkerCategory.chapter_candidate` only and
  converts to `Guide` with frame position = `start_seconds * 25`
- `export_chapters_to_markdown` sorts guides by position and formats as `HH:MM:SS`
- `build_review_timeline` writes a review report `.md` to `reports/` as a side effect

## Pass / Fail Criteria
- Pass: All test cases pass, no import errors
- Fail: Any test fails or source API doesn't match expectations
