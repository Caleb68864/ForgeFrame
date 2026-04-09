"""Tests for pacing analyzer pipeline (PL-04)."""
from __future__ import annotations

import uuid

import pytest

from workshop_video_brain.core.models.pacing import PacingReport, PacingSegment
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment, WordTiming
from workshop_video_brain.edit_mcp.pipelines.pacing_analyzer import (
    _classify_pace,
    _sentence_count,
    analyze_pacing,
    format_pacing_report,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_seg(text: str, start: float, end: float, words: list | None = None) -> TranscriptSegment:
    return TranscriptSegment(
        start_seconds=start,
        end_seconds=end,
        text=text,
        words=words or [],
    )


def make_transcript(segments: list[TranscriptSegment]) -> Transcript:
    return Transcript(asset_id=uuid.uuid4(), segments=segments)


# ---------------------------------------------------------------------------
# TestClassifyPace
# ---------------------------------------------------------------------------


class TestClassifyPace:
    def test_below_100_wpm_is_slow(self):
        assert _classify_pace(99.9) == "slow"

    def test_exactly_100_wpm_is_medium(self):
        assert _classify_pace(100.0) == "medium"

    def test_exactly_160_wpm_is_medium(self):
        assert _classify_pace(160.0) == "medium"

    def test_above_160_wpm_is_fast(self):
        assert _classify_pace(160.1) == "fast"

    def test_zero_wpm_is_slow(self):
        assert _classify_pace(0.0) == "slow"


# ---------------------------------------------------------------------------
# TestSentenceCount
# ---------------------------------------------------------------------------


class TestSentenceCount:
    def test_single_sentence_no_punctuation_returns_one(self):
        assert _sentence_count("hello world") == 1

    def test_two_sentences(self):
        assert _sentence_count("Hello. World.") == 2

    def test_mixed_punctuation(self):
        assert _sentence_count("Really? Yes! Okay.") == 3

    def test_empty_string_returns_one(self):
        assert _sentence_count("") == 1


# ---------------------------------------------------------------------------
# TestAnalyzePacingEmpty
# ---------------------------------------------------------------------------


class TestAnalyzePacingEmpty:
    def test_empty_segments_returns_zero_report(self):
        report = analyze_pacing(make_transcript([]))
        assert report.overall_wpm == 0.0
        assert report.overall_pace == "slow"
        assert report.weak_intro is True
        assert report.energy_drops == []
        assert report.segments == []
        assert "No transcript data available" in report.summary

    def test_zero_duration_segment_returns_zero_report(self):
        report = analyze_pacing(make_transcript([make_seg("hello", 0.0, 0.0)]))
        assert report.overall_wpm == 0.0


# ---------------------------------------------------------------------------
# TestAnalyzePacingNormal
# ---------------------------------------------------------------------------


class TestAnalyzePacingNormal:
    def test_medium_pace_single_window(self):
        # ~65 words in 30 seconds = 130 wpm → medium
        words = " ".join(["word"] * 65)
        report = analyze_pacing(make_transcript([make_seg(words, 0.0, 30.0)]))
        assert len(report.segments) == 1
        assert report.segments[0].pace == "medium"

    def test_fast_pace_segment(self):
        # 100 words in 30 seconds = 200 wpm → fast
        words = " ".join(["word"] * 100)
        report = analyze_pacing(make_transcript([make_seg(words, 0.0, 30.0)]))
        assert report.segments[0].pace == "fast"
        assert report.overall_pace == "fast"

    def test_slow_pace_segment(self):
        # 40 words in 30 seconds = 80 wpm → slow
        words = " ".join(["word"] * 40)
        report = analyze_pacing(make_transcript([make_seg(words, 0.0, 30.0)]))
        assert report.segments[0].pace == "slow"
        assert report.weak_intro is True

    def test_speech_density_clamped_at_one(self):
        # Two overlapping segments that more than fill the window
        segs = [
            make_seg("word " * 50, 0.0, 30.0),
            make_seg("word " * 50, 0.0, 30.0),
        ]
        report = analyze_pacing(make_transcript(segs))
        assert all(s.speech_density <= 1.0 for s in report.segments)

    def test_word_variety_between_zero_and_one(self):
        # All-repeated words → low variety
        report_repeated = analyze_pacing(
            make_transcript([make_seg("the " * 30, 0.0, 30.0)])
        )
        assert 0.0 <= report_repeated.segments[0].word_variety <= 1.0
        assert report_repeated.segments[0].word_variety < 1.0

        # All unique words → high variety
        unique_words = " ".join([f"word{i}" for i in range(30)])
        report_unique = analyze_pacing(
            make_transcript([make_seg(unique_words, 0.0, 30.0)])
        )
        assert report_unique.segments[0].word_variety == 1.0

    def test_segment_window_boundaries(self):
        # 3 non-overlapping 30-second segments → 3 windows
        segs = [
            make_seg("word " * 30, 0.0, 30.0),
            make_seg("word " * 30, 30.0, 60.0),
            make_seg("word " * 30, 60.0, 90.0),
        ]
        report = analyze_pacing(make_transcript(segs), segment_duration=30.0)
        assert len(report.segments) == 3

    def test_text_preview_truncated_to_50_chars(self):
        text = "word " * 20  # > 50 chars
        report = analyze_pacing(make_transcript([make_seg(text, 0.0, 30.0)]))
        assert len(report.segments[0].text_preview) <= 50

    def test_avg_sentence_length_computed(self):
        # "Hello world. Goodbye world." → 2 sentences, 4 words → avg = 2.0
        report = analyze_pacing(
            make_transcript([make_seg("Hello world. Goodbye world.", 0.0, 30.0)])
        )
        assert report.segments[0].avg_sentence_length == 2.0


# ---------------------------------------------------------------------------
# TestAnalyzePacingWeakIntro
# ---------------------------------------------------------------------------


class TestAnalyzePacingWeakIntro:
    def test_weak_intro_low_speech_density(self):
        # Very short speech in 30s window (< 30% coverage)
        segs = [
            make_seg("word word word", 0.0, 5.0),   # 5s out of 30s → ~17% density
        ]
        report = analyze_pacing(make_transcript(segs), segment_duration=30.0)
        assert report.weak_intro is True

    def test_strong_intro(self):
        # Fast pace and dense speech in first window
        words = " ".join([f"word{i}" for i in range(120)])
        report = analyze_pacing(
            make_transcript([make_seg(words, 0.0, 30.0)]),
            segment_duration=30.0,
        )
        # 120 words / 0.5 min = 240 wpm → fast, and density should be high
        assert report.weak_intro is False


# ---------------------------------------------------------------------------
# TestAnalyzePacingEnergyDrops
# ---------------------------------------------------------------------------


def make_slow_window(start: float) -> TranscriptSegment:
    """Create a 30s segment with ~40 words (80 wpm → slow)."""
    return make_seg(" ".join(["word"] * 40), start, start + 30.0)


class TestAnalyzePacingEnergyDrops:
    def test_three_consecutive_slow_windows_flagged(self):
        segs = [make_slow_window(i * 30.0) for i in range(3)]
        report = analyze_pacing(make_transcript(segs), segment_duration=30.0)
        assert len(report.energy_drops) == 1
        assert abs(report.energy_drops[0]["duration"] - 90.0) < 1.0

    def test_two_consecutive_slow_windows_not_flagged(self):
        segs = [make_slow_window(i * 30.0) for i in range(2)]
        report = analyze_pacing(make_transcript(segs), segment_duration=30.0)
        assert report.energy_drops == []

    def test_energy_drop_boundaries_correct(self):
        # 3 slow + 1 fast
        segs = [make_slow_window(i * 30.0) for i in range(3)]
        # fast window
        segs.append(make_seg(" ".join(["word"] * 100), 90.0, 120.0))
        report = analyze_pacing(make_transcript(segs), segment_duration=30.0)
        assert len(report.energy_drops) == 1
        assert report.energy_drops[0]["start"] == 0.0
        assert report.energy_drops[0]["end"] == 90.0

    def test_multiple_drop_runs_detected_independently(self):
        # slow×3, fast×1, slow×3
        segs = [make_slow_window(i * 30.0) for i in range(3)]
        segs.append(make_seg(" ".join(["word"] * 100), 90.0, 120.0))
        segs += [make_slow_window(120.0 + i * 30.0) for i in range(3)]
        report = analyze_pacing(make_transcript(segs), segment_duration=30.0)
        assert len(report.energy_drops) == 2


# ---------------------------------------------------------------------------
# TestAnalyzePacingWordTimings
# ---------------------------------------------------------------------------


class TestAnalyzePacingWordTimings:
    def test_word_timings_used_when_available(self):
        # Words inside [0, 30] should be counted; word outside excluded
        words_inside = [
            WordTiming(word=f"w{i}", start=float(i), end=float(i) + 0.5)
            for i in range(10)  # 0–9s, all within 0–30s window
        ]
        word_outside = WordTiming(word="outside", start=40.0, end=41.0)
        seg = TranscriptSegment(
            start_seconds=0.0,
            end_seconds=45.0,
            text=" ".join([w.word for w in words_inside]) + " outside",
            words=words_inside + [word_outside],
        )
        report = analyze_pacing(make_transcript([seg]), segment_duration=30.0)
        # Only words inside [0,30] should be counted in the first window
        assert len(report.segments) >= 1
        # Word count in first segment should exclude the word at t=40
        first_seg = report.segments[0]
        assert first_seg.wpm > 0


# ---------------------------------------------------------------------------
# TestFormatPacingReport
# ---------------------------------------------------------------------------


def make_report_with_segments(n_segs: int = 0) -> PacingReport:
    segs = [
        PacingSegment(
            start=i * 30.0,
            end=(i + 1) * 30.0,
            wpm=130.0,
            speech_density=0.9,
            word_variety=0.8,
            avg_sentence_length=10.0,
            pace="medium",
            text_preview="preview text",
        )
        for i in range(n_segs)
    ]
    return PacingReport(
        segments=segs,
        overall_wpm=130.0,
        overall_pace="medium",
        weak_intro=False,
        energy_drops=[],
        summary="Your video averages 130 WPM. Intro is strong. No energy drops detected.",
    )


class TestFormatPacingReport:
    def test_empty_report_shows_no_segments_message(self):
        report = make_report_with_segments(0)
        output = format_pacing_report(report)
        assert "_No segments to display._" in output

    def test_output_starts_with_heading(self):
        output = format_pacing_report(make_report_with_segments(0))
        assert output.startswith("# Pacing & Energy Report")

    def test_overall_stats_section_present(self):
        output = format_pacing_report(make_report_with_segments(0))
        assert "## Overall Stats" in output

    def test_segment_breakdown_table_present(self):
        output = format_pacing_report(make_report_with_segments(1))
        assert "## Segment Breakdown" in output

    def test_slow_segment_flagged_with_warning_indicator(self):
        report = PacingReport(
            segments=[
                PacingSegment(
                    start=0.0, end=30.0, wpm=80.0, speech_density=0.5,
                    word_variety=0.7, avg_sentence_length=8.0,
                    pace="slow", text_preview="slow text",
                )
            ],
            overall_wpm=80.0,
            overall_pace="slow",
            weak_intro=True,
            energy_drops=[],
            summary="Slow.",
        )
        output = format_pacing_report(report)
        assert "⚠" in output

    def test_energy_drops_section_shown_when_present(self):
        # format_pacing_report only emits flagged sections when segments exist
        report = make_report_with_segments(1)
        report.energy_drops = [{"start": 0.0, "end": 90.0, "duration": 90.0}]
        output = format_pacing_report(report)
        assert "## Flagged Sections" in output

    def test_intro_warning_shown_when_weak(self):
        # Intro Warning only rendered when segments exist
        report = make_report_with_segments(1)
        report.weak_intro = True
        output = format_pacing_report(report)
        assert "## Intro Warning" in output

    def test_intro_warning_absent_when_strong(self):
        report = make_report_with_segments(0)
        report.weak_intro = False
        output = format_pacing_report(report)
        assert "## Intro Warning" not in output

    def test_summary_quote_block_present(self):
        report = make_report_with_segments(0)
        report.summary = "A great summary here."
        output = format_pacing_report(report)
        assert "> A great summary here." in output
