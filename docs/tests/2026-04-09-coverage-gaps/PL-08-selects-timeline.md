---
scenario_id: "PL-08"
title: "Selects Timeline"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario PL-08: Selects Timeline

## Description
Tests `build_selects`, `build_selects_timeline`, `selects_to_json`, and
`selects_to_markdown` from `selects_timeline.py`. `build_selects` filters
markers by confidence threshold and excluded categories (`dead_air`,
`repetition`), computes a `usefulness_score`, and returns a sorted
`SelectsEntry` list. `build_selects_timeline` constructs a Kdenlive project
from the selects list. Covers: empty input, below-threshold markers, excluded
categories, usefulness scoring and sort order, JSON serialization round-trip,
markdown table format, and Kdenlive project construction.

## Preconditions
- `workshop-video-brain` installed in editable mode
- `Marker`, `MarkerConfig`, `MarkerCategory` from core models
- `serialize_versioned` patched to prevent real file writes
- No filesystem or network access beyond `tmp_path`

## Test Cases

```
tests/unit/test_selects_timeline.py

from unittest.mock import patch
import json

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_marker(start=0.0, end=5.0, confidence=0.8,
                category="step_explanation", clip_ref="/clip.mp4", reason="r")
    # Returns a Marker with the given fields

def make_config(weights=None)
    # Returns a MarkerConfig; weights default to {"step_explanation": 0.9}

# ── SelectsEntry model ────────────────────────────────────────────────────────

class TestSelectsEntry:
    def test_fields_match_marker(tmp_path)
        # SelectsEntry fields: marker, clip_ref, start_seconds, end_seconds,
        # reason, usefulness_score all present and correct type

# ── build_selects ─────────────────────────────────────────────────────────────

class TestBuildSelects:
    def test_empty_markers_returns_empty_list()
        # build_selects([], config) == []

    def test_marker_below_min_confidence_excluded()
        # marker with confidence=0.4, min_confidence=0.5
        # result == []

    def test_marker_at_min_confidence_included()
        # marker with confidence=0.5, min_confidence=0.5
        # len(result) == 1

    def test_dead_air_category_excluded()
        # marker with category="dead_air", confidence=0.9
        # result == []

    def test_repetition_category_excluded()
        # marker with category="repetition", confidence=0.9
        # result == []

    def test_non_excluded_category_included()
        # marker with category="step_explanation", confidence=0.7
        # len(result) == 1

    def test_usefulness_score_is_confidence_times_weight()
        # marker confidence=0.8, weight=0.9 (step_explanation)
        # entry.usefulness_score == round(0.8 * 0.9, 6) == 0.72

    def test_missing_category_weight_defaults_to_0_5()
        # category not in config.category_weights
        # usefulness_score == round(confidence * 0.5, 6)

    def test_entries_sorted_by_usefulness_descending()
        # markers: score=0.9 and score=0.4 (after weight)
        # result[0].usefulness_score > result[1].usefulness_score

    def test_clip_ref_copied_from_marker()
        # entry.clip_ref == marker.clip_ref

    def test_start_end_copied_from_marker()
        # entry.start_seconds == marker.start_seconds
        # entry.end_seconds == marker.end_seconds

    def test_reason_copied_from_marker()
        # entry.reason == marker.reason

    def test_multiple_markers_mixed_filter()
        # 3 markers: 1 excluded (dead_air), 1 below threshold, 1 valid
        # len(result) == 1

# ── selects_to_json ───────────────────────────────────────────────────────────

class TestSelectsToJson:
    def test_empty_selects_returns_empty_json_array()
        # selects_to_json([]) == "[]"  (or parses to [])

    def test_valid_selects_serializes_to_list()
        # selects_to_json([entry]) → parse → list of length 1

    def test_output_is_valid_json()
        # json.loads(selects_to_json([entry])) does not raise

    def test_usefulness_score_preserved_in_json()
        # Parsed output[0]["usefulness_score"] == entry.usefulness_score

    def test_all_required_fields_present_in_json()
        # Each item has: marker, clip_ref, start_seconds, end_seconds,
        # reason, usefulness_score

# ── selects_to_markdown ───────────────────────────────────────────────────────

class TestSelectsToMarkdown:
    def test_empty_selects_returns_header_and_empty_table()
        # Output is table header rows only (no data rows)

    def test_table_has_four_columns()
        # First row: "| Time | Category | Reason | Score |"

    def test_time_formatted_correctly()
        # entry with start=10.5, end=20.0 → "10.5s – 20.0s"

    def test_reason_pipe_escaped()
        # entry.reason = "cut | measure"
        # output contains "cut \\| measure"

    def test_score_formatted_to_three_decimal_places()
        # usefulness_score=0.72 → "0.720"

    def test_category_string_in_row()
        # category "step_explanation" appears in row

    def test_output_ends_with_newline()
        # selects_to_markdown([entry]).endswith("\n")

# ── build_selects_timeline ────────────────────────────────────────────────────

class TestBuildSelectsTimeline:
    def test_returns_path(tmp_path)
        # Patch serialize_versioned → returns a Path
        # build_selects_timeline(selects, [], tmp_path) returns that Path

    def test_empty_selects_creates_empty_project(tmp_path)
        # selects=[] → serialize_versioned called with project having no producers

    def test_producer_created_per_unique_clip_ref(tmp_path)
        # Two selects with same clip_ref → one producer
        # Two selects with different clip_refs → two producers

    def test_in_out_points_from_selects_seconds(tmp_path)
        # entry with start=10.0, end=20.0, fps=25
        # PlaylistEntry: in_point=250, out_point=500

    def test_asset_resolved_when_available(tmp_path)
        # MediaAsset.path=="/real/path.mp4" matches clip_ref
        # producer.resource == "/real/path.mp4"

    def test_guide_added_per_entry(tmp_path)
        # Two selects → two guides in project.guides

    def test_guide_label_is_reason_or_category(tmp_path)
        # entry.reason == "Intro section"
        # guide.label == "Intro section"

    def test_no_high_confidence_markers_produces_empty_selects(tmp_path)
        # All markers below threshold → build_selects returns []
        # build_selects_timeline with empty list → empty project

    def test_out_point_never_less_than_in_point(tmp_path)
        # entry with start==end (zero-length)
        # out_point >= in_point
```

## Steps
1. Read source module to understand current API
2. Create test file at `tests/unit/test_selects_timeline.py`
3. Implement test cases with mocked dependencies
4. Run: `uv run pytest tests/unit/test_selects_timeline.py -v`

## Expected Results
- `build_selects` excludes `dead_air` and `repetition` categories and markers
  below `min_confidence`, sorts by `usefulness_score` descending
- `usefulness_score` = `confidence_score * category_weight` (default 0.5)
- `selects_to_json` produces valid JSON with all `SelectsEntry` fields
- `selects_to_markdown` produces a 4-column table; pipe characters in reasons
  are escaped as `\|`
- `build_selects_timeline` reuses producers for duplicate clip_refs and ensures
  `out_point >= in_point` for zero-length entries

## Pass / Fail Criteria
- Pass: All test cases pass, no import errors
- Fail: Any test fails or source API doesn't match expectations
