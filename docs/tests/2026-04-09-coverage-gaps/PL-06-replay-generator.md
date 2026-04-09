---
scenario_id: "PL-06"
title: "Replay Generator"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario PL-06: Replay Generator

## Description
Tests `generate_replay` from `replay_generator.py` and the `ReplayReport` /
`ReplaySegment` Pydantic models. The pipeline reads `*_markers.json` files from
`workspace/markers/`, ranks them, greedily selects non-overlapping segments up
to `target_duration`, applies 2 s padding, merges adjacent segments (gap < 3 s),
and serializes a `.kdenlive` project. Internal helpers (`_select_segments`,
`_apply_padding`, `_merge_adjacent`) are exercised through thin wrappers or
direct import to maximize coverage. Covers: no markers → `ValueError`, empty
markers dir, segment selection logic, merge logic, padding boundary clamping,
and serializer invocation.

## Preconditions
- `workshop-video-brain` installed in editable mode
- `tmp_path` provides workspace directory structure
- `serialize_versioned` and `scan_directory` patched to avoid filesystem/FFmpeg calls
- `Marker` from `workshop_video_brain.core.models.markers`
- `MarkerCategory` from `workshop_video_brain.core.models.enums`

## Test Cases

```
tests/unit/test_replay_generator.py

from unittest.mock import patch, MagicMock
import json, uuid

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_marker(start, end, confidence=0.8, category="chapter_candidate",
                clip_ref="/fake/clip.mp4", reason="test reason")
    # Returns a Marker instance with the given fields

def write_markers_json(markers_dir, filename, markers)
    # Writes markers as JSON to markers_dir/filename

# ── ReplaySegment / ReplayReport models ──────────────────────────────────────

class TestReplayModels:
    def test_replay_segment_fields()
        # ReplaySegment(start=0.0, end=10.0, reason="r", source_clip="/x.mp4")
        # .start == 0.0, .end == 10.0, .reason == "r"

    def test_replay_report_fields()
        # ReplayReport(segment_count=2, total_duration=20.0,
        #              target_duration=60.0, segments_used=[...])
        # .segment_count == 2

    def test_replay_segment_is_pydantic_model()
        # isinstance(ReplaySegment(...), BaseModel) is True

# ── _load_markers ─────────────────────────────────────────────────────────────

class TestLoadMarkers:
    def test_missing_markers_dir_returns_empty_list(tmp_path)
        # workspace_root/markers/ does not exist
        # _load_markers(workspace_root) == []

    def test_loads_markers_from_json(tmp_path)
        # Write one *_markers.json with two marker dicts
        # len(_load_markers(tmp_path)) == 2

    def test_only_files_matching_pattern_loaded(tmp_path)
        # Write a non-matching file "notes.txt" and a matching "*_markers.json"
        # Only markers from the matching file returned

    def test_corrupt_json_file_skipped(tmp_path)
        # Write "NOTJSON" to a *_markers.json file
        # _load_markers returns [] without raising

# ── _select_segments ─────────────────────────────────────────────────────────

class TestSelectSegments:
    def test_empty_ranked_returns_empty(tmp_path)
        # _select_segments([], target_duration=60.0) == []

    def test_single_marker_selected(tmp_path)
        # One marker within target_duration
        # len(result) == 1

    def test_stops_when_target_duration_met(tmp_path)
        # Three markers, target_duration=15; first two fill it
        # len(result) <= 2

    def test_overlapping_markers_excluded()
        # Marker at 0–5 and marker at 3–8 (padded ranges overlap)
        # Only first selected; second skipped

    def test_non_overlapping_markers_both_selected()
        # Marker at 0–5, marker at 10–15 (gap > 2*padding)
        # Both selected

    def test_padding_clamped_to_zero()
        # Marker with start_seconds=0.5 and padding=2.0
        # padded_start == 0.0 (max(0, 0.5-2) = 0)

# ── _apply_padding ────────────────────────────────────────────────────────────

class TestApplyPadding:
    def test_results_sorted_chronologically()
        # Markers at t=20 and t=5 → sorted result starts at t=5

    def test_start_padded()
        # marker.start_seconds=10.0, padding=2.0 → padded_start=8.0

    def test_end_padded()
        # marker.end_seconds=15.0, padding=2.0 → padded_end=17.0

# ── _merge_adjacent ───────────────────────────────────────────────────────────

class TestMergeAdjacent:
    def test_empty_input_returns_empty()
        # _merge_adjacent([]) == []

    def test_single_segment_returned_as_is()
        # _merge_adjacent([(0, 10, marker)]) → [(0, 10, [marker])]

    def test_gap_less_than_merge_threshold_merges()
        # Segments (0,10) and (12,20) with merge_gap=3
        # Gap = 2 < 3 → merged into one (0,20)

    def test_gap_equal_to_merge_threshold_does_not_merge()
        # Segments (0,10) and (13,20) with merge_gap=3
        # Gap = 3 (not < 3) → two separate entries

    def test_gap_larger_than_merge_threshold_not_merged()
        # Segments (0,10) and (20,30) → two separate entries

    def test_merged_segment_contains_all_source_markers()
        # Two markers merged → merged group has both in marker list

# ── generate_replay (integration with mocks) ─────────────────────────────────

class TestGenerateReplay:
    def test_no_markers_raises_value_error(tmp_path)
        # No *_markers.json in workspace/markers/
        # pytest.raises(ValueError, match="No markers found")

    def test_returns_path_on_success(tmp_path)
        # Write one valid *_markers.json; patch serialize_versioned to return a Path
        # generate_replay(tmp_path) returns that Path

    def test_serialize_versioned_called_once(tmp_path)
        # Patch serialize_versioned; assert called exactly once

    def test_producers_created_per_unique_clip_ref(tmp_path)
        # Two markers with same clip_ref → one producer
        # Two markers with different clip_refs → two producers

    def test_guides_added_per_merged_segment(tmp_path)
        # Two markers that do NOT merge → two guide labels containing "Highlight:"

    def test_crossfade_added_between_multiple_segments(tmp_path)
        # Two non-adjacent segments → one OpaqueElement transition added

    def test_no_crossfade_for_single_segment(tmp_path)
        # Only one merged segment → no OpaqueElement in project.opaque_elements

    def test_target_duration_respected(tmp_path)
        # 10 markers × 5 s each, target=20 s
        # Serialized project has ≤ 5 producers (only segments up to ~20 s selected)
```

## Steps
1. Read source module to understand current API
2. Create test file at `tests/unit/test_replay_generator.py`
3. Implement test cases with mocked dependencies
4. Run: `uv run pytest tests/unit/test_replay_generator.py -v`

## Expected Results
- `generate_replay` raises `ValueError` when the markers directory is missing or empty
- Greedy selection stops when `target_duration` is reached
- Adjacent segments with gap < 3 s are merged into a single KdenliveProject entry
- Each merged segment gets exactly one `Guide` labelled "Highlight: {reason}"
- Crossfade `OpaqueElement` transitions appear between every pair of adjacent segments
  but not after the last one

## Pass / Fail Criteria
- Pass: All test cases pass, no import errors
- Fail: Any test fails or source API doesn't match expectations
