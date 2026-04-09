---
scenario_id: "PL-02"
title: "B-Roll Suggestions"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario PL-02: B-Roll Suggestions

## Description
Tests `detect_broll_opportunities` and `format_broll_suggestions` from
`broll_suggestions.py`. The module scans `Transcript.segments` for five visual
pattern categories (process_shot, material_closeup, tool_in_use, result_reveal,
measurement_shot) using keyword and regex matching, returning scored suggestion
dicts. Covers: normal transcript with hits across multiple categories, empty
transcript, transcript with no matching text, multi-category segments, confidence
values, and markdown formatting of results.

## Preconditions
- `workshop-video-brain` installed in editable mode (`uv run pytest`)
- `Transcript` and `TranscriptSegment` imported from
  `workshop_video_brain.core.models.transcript`
- All test data is self-contained; no filesystem or network access needed

## Test Cases

```
tests/unit/test_broll_suggestions.py

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_segment(text, start=0.0, end=5.0)
    # Returns a TranscriptSegment with the given text and timestamps

def make_transcript(segments)
    # Returns a Transcript wrapping a list of TranscriptSegment objects

# ── detect_broll_opportunities ────────────────────────────────────────────────

class TestDetectBrollOpportunities:
    def test_empty_transcript_returns_empty_list()
        # Transcript with segments=[]
        # assert result == []

    def test_blank_segment_text_skipped()
        # Segment with text="   " (whitespace only)
        # assert result == []

    def test_process_shot_keyword_detected()
        # Segment: "Now we sew the panels together"
        # Exactly one suggestion with category=="process_shot"
        # confidence == 0.8

    def test_material_closeup_detected()
        # Segment: "This fabric is really nice"
        # category == "material_closeup", confidence == 0.75

    def test_tool_in_use_detected()
        # Segment: "Use the rotary cutter along the edge"
        # category == "tool_in_use"
        # confidence == round(0.85 * 0.7, 4) = 0.595 (multi-word → strength 0.7)

    def test_tool_in_use_exact_phrase_full_confidence()
        # Segment: "put the scissors away"
        # confidence == 0.85 (exact single-word keyword)

    def test_result_reveal_detected()
        # Segment: "Here's what it looks like when finished"
        # category == "result_reveal"

    def test_measurement_shot_with_numeric_unit()
        # Segment: "Cut to 12 inches from the edge"
        # category == "measurement_shot", confidence == 0.85

    def test_measurement_shot_via_keyword()
        # Segment: "measure along the seam" (no numeric unit)
        # category == "measurement_shot", confidence == 0.75

    def test_multi_category_segment_returns_multiple_suggestions()
        # Segment: "cut the fabric to 5cm" → process_shot + material_closeup + measurement_shot
        # len(result) >= 3

    def test_suggestion_dict_has_required_keys()
        # For any matched segment, result[0] contains keys:
        # timestamp, end_timestamp, category, description, context, confidence

    def test_timestamps_copied_from_segment()
        # Segment with start=10.5, end=15.0
        # suggestion["timestamp"] == 10.5
        # suggestion["end_timestamp"] == 15.0

    def test_context_truncated_at_120_chars()
        # Segment text of 150 characters
        # suggestion["context"] ends with "..." and len <= 120

    def test_context_not_truncated_when_under_120_chars()
        # Segment text of 80 chars
        # suggestion["context"] == text (no ellipsis)

    def test_description_includes_label()
        # process_shot → description starts with "Show Process Shot:"

    def test_no_hits_returns_empty_list()
        # Segment: "Hello and welcome to my video today" (no keywords)
        # result == []

    def test_partial_word_not_matched_as_process_shot()
        # Segment: "sewing kit" — "sew" is NOT a whole-word match for "sewing"
        # The regex uses \b word boundary — "sew" does NOT match inside "sewing"
        # result has no process_shot entry

    def test_multiple_segments_aggregated()
        # Two segments: first has process_shot, second has result_reveal
        # len(result) == 2, categories in order

# ── format_broll_suggestions ─────────────────────────────────────────────────

class TestFormatBrollSuggestions:
    def test_empty_list_returns_no_opportunities_message()
        # format_broll_suggestions([]) contains "No B-roll opportunities detected"

    def test_output_starts_with_heading()
        # result starts with "# B-Roll Suggestions"

    def test_total_count_present()
        # suggestions with 3 items → "Total suggestions: 3" in output

    def test_categories_grouped_under_headings()
        # Mix of process_shot and tool_in_use suggestions
        # "## Process Shot" and "## Tool in Use" appear as section headings

    def test_items_sorted_by_timestamp_within_category()
        # Two process_shot suggestions: ts=30.0 and ts=5.0
        # ts=5.0 appears before ts=30.0 in output

    def test_timestamp_formatted_as_mm_ss()
        # suggestion with timestamp=125.0, end_timestamp=130.0
        # output contains "2:05"

    def test_confidence_displayed_to_two_decimal_places()
        # confidence=0.8 → "confidence: 0.80"

    def test_unknown_category_falls_back_to_category_key()
        # Inject a suggestion dict with category="custom_cat" (not in _CATEGORY_LABELS)
        # format_broll_suggestions handles KeyError gracefully or uses raw key
```

## Steps
1. Read source module to understand current API
2. Create test file at `tests/unit/test_broll_suggestions.py`
3. Implement test cases with mocked dependencies
4. Run: `uv run pytest tests/unit/test_broll_suggestions.py -v`

## Expected Results
- `detect_broll_opportunities` returns one dict per (segment × matched category)
- Word-boundary regex prevents false positives on substrings (e.g. "sewing" ≠ "sew")
- Multi-word keywords with partial match reduce confidence to 0.7× base
- `format_broll_suggestions` groups by category and sorts items by timestamp
- Empty input returns the "no opportunities" sentinel message without crashing

## Pass / Fail Criteria
- Pass: All test cases pass, no import errors
- Fail: Any test fails or source API doesn't match expectations
