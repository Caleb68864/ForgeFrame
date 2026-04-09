---
scenario_id: "PL-04"
title: "Pacing Analyzer"
tool: "bash"
type: test-scenario
tags:
  - test-scenario
---

# Scenario PL-04: Pacing Analyzer

## Description
Tests `analyze_pacing` and `format_pacing_report` from `pacing_analyzer.py`.
The module windows a `Transcript` into 30-second buckets, computes words-per-minute
(WPM), speech density, word variety, and sentence length per window, classifies
each as slow/medium/fast, detects energy drops (3+ consecutive slow windows),
and flags a weak intro. Covers: empty transcript, zero-duration transcript,
normal/fast/slow speech, energy-drop detection, window-boundary clamping, and
the markdown formatter.

## Preconditions
- `workshop-video-brain` installed in editable mode
- `Transcript`, `TranscriptSegment` from `workshop_video_brain.core.models.transcript`
- `PacingReport`, `PacingSegment` from `workshop_video_brain.core.models.pacing`
- No external calls; all data self-contained in fixtures

## Test Cases

```
tests/unit/test_pacing_analyzer.py

# ── Helpers ──────────────────────────────────────────────────────────────────

def make_seg(text, start, end, words=None)
    # Returns a TranscriptSegment; words is optional list of WordTiming

def make_transcript(segments)
    # Returns a Transcript wrapping the segments list

# ── _classify_pace (private helper, tested indirectly & directly) ─────────────

class TestClassifyPace:
    def test_below_100_wpm_is_slow()
        # _classify_pace(99.9) == "slow"
    def test_exactly_100_wpm_is_medium()
        # _classify_pace(100.0) == "medium"
    def test_exactly_160_wpm_is_medium()
        # _classify_pace(160.0) == "medium"
    def test_above_160_wpm_is_fast()
        # _classify_pace(160.1) == "fast"
    def test_zero_wpm_is_slow()
        # _classify_pace(0.0) == "slow"

# ── _sentence_count ──────────────────────────────────────────────────────────

class TestSentenceCount:
    def test_single_sentence_no_punctuation_returns_one()
        # _sentence_count("hello world") == 1
    def test_two_sentences()
        # _sentence_count("Hello. World.") == 2
    def test_mixed_punctuation()
        # _sentence_count("Really? Yes! Okay.") == 3
    def test_empty_string_returns_one()
        # _sentence_count("") == 1  (max guard)

# ── analyze_pacing ────────────────────────────────────────────────────────────

class TestAnalyzePacingEmpty:
    def test_empty_segments_returns_zero_report()
        # Transcript(segments=[])
        # report.overall_wpm == 0.0
        # report.overall_pace == "slow"
        # report.weak_intro is True
        # report.energy_drops == []
        # report.segments == []
        # "No transcript data available" in report.summary

    def test_zero_duration_segment_returns_zero_report()
        # Single segment with start==end (0.0, 0.0)
        # Same as empty: overall_wpm==0.0

class TestAnalyzePacingNormal:
    def test_medium_pace_single_window()
        # One 30-second segment, ~130 words (≈260 wpm over full segment; window=30s)
        # But proportional calc: 130 words / 0.5 min = 260 wpm → fast
        # Test with ~65 words in 30s → 130 wpm → medium
        # report.segments[0].pace == "medium"

    def test_fast_pace_segment()
        # One 30-second segment with 100 words → 200 wpm → fast
        # report.segments[0].pace == "fast"
        # report.overall_pace == "fast"

    def test_slow_pace_segment()
        # One 30-second segment with 40 words → 80 wpm → slow
        # report.segments[0].pace == "slow"
        # report.weak_intro is True  (first segment is slow)

    def test_speech_density_clamped_at_one()
        # Overlapping segments fill more than the window duration
        # speech_density <= 1.0

    def test_word_variety_between_zero_and_one()
        # Segment with repeated words ("the the the the")
        # report.segments[0].word_variety < 1.0
        # Segment with all unique words → word_variety == 1.0

    def test_segment_window_boundaries()
        # Transcript spanning 0–90s with segment_duration=30
        # len(report.segments) == 3

    def test_text_preview_truncated_to_50_chars()
        # Window text > 50 chars
        # len(report.segments[0].text_preview) <= 50

    def test_avg_sentence_length_computed()
        # "Hello world. Goodbye world." in one segment
        # avg_sentence_length == 2.0

class TestAnalyzePacingWeakIntro:
    def test_weak_intro_low_speech_density()
        # First window has very sparse speech coverage (< 30% of window)
        # report.weak_intro is True

    def test_strong_intro()
        # First 30-second window with 120 wpm and >30% density
        # report.weak_intro is False

class TestAnalyzePacingEnergyDrops:
    def test_three_consecutive_slow_windows_flagged()
        # 3 × 30-second windows each at ~50 wpm (slow)
        # len(report.energy_drops) == 1
        # report.energy_drops[0]["duration"] == 90.0  (approx)

    def test_two_consecutive_slow_windows_not_flagged()
        # 2 slow windows → not a drop (threshold is 3)
        # report.energy_drops == []

    def test_energy_drop_boundaries_correct()
        # Windows: slow(0-30), slow(30-60), slow(60-90), fast(90-120)
        # drop["start"] == 0.0, drop["end"] == 90.0

    def test_multiple_drop_runs_detected_independently()
        # Windows: slow×3, fast×1, slow×3
        # len(report.energy_drops) == 2

class TestAnalyzePacingWordTimings:
    def test_word_timings_used_when_available()
        # Segment with explicit WordTiming list; words outside window excluded
        # Only words inside window boundaries counted

# ── format_pacing_report ─────────────────────────────────────────────────────

class TestFormatPacingReport:
    def test_empty_report_shows_no_segments_message()
        # PacingReport with segments=[]
        # "_No segments to display._" in output

    def test_output_starts_with_heading()
        # "# Pacing & Energy Report" is first line

    def test_overall_stats_section_present()
        # "## Overall Stats" in output

    def test_segment_breakdown_table_present()
        # "## Segment Breakdown" in output when segments exist

    def test_slow_segment_flagged_with_warning_indicator()
        # Segment with pace=="slow" → row contains " ⚠"

    def test_energy_drops_section_shown_when_present()
        # report with energy_drops → "## Flagged Sections" in output

    def test_intro_warning_shown_when_weak()
        # report.weak_intro=True → "## Intro Warning" in output

    def test_intro_warning_absent_when_strong()
        # report.weak_intro=False → "## Intro Warning" NOT in output

    def test_summary_quote_block_present()
        # output contains "> " followed by report.summary text
```

## Steps
1. Read source module to understand current API
2. Create test file at `tests/unit/test_pacing_analyzer.py`
3. Implement test cases with mocked dependencies
4. Run: `uv run pytest tests/unit/test_pacing_analyzer.py -v`

## Expected Results
- Empty/zero-duration transcripts return a zeroed `PacingReport` with a safe summary string
- WPM thresholds: < 100 → slow, 100–160 → medium, > 160 → fast
- Energy drops require exactly 3 or more consecutive slow windows
- `weak_intro` is `True` when the first window is slow OR speech density < 0.3
- `format_pacing_report` emits a `⚠` flag on slow rows and correct section headings

## Pass / Fail Criteria
- Pass: All test cases pass, no import errors
- Fail: Any test fails or source API doesn't match expectations
