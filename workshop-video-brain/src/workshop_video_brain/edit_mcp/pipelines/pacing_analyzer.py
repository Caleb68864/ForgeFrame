"""Pacing and energy analysis pipeline for transcripts."""
from __future__ import annotations

import re

from workshop_video_brain.core.models.pacing import PacingReport, PacingSegment
from workshop_video_brain.core.models.transcript import Transcript

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SLOW_WPM = 100.0
_FAST_WPM = 160.0
_SENTENCE_SPLIT_RE = re.compile(r"[.!?]+")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _classify_pace(wpm: float) -> str:
    """Return "slow", "medium", or "fast" based on WPM."""
    if wpm < _SLOW_WPM:
        return "slow"
    if wpm <= _FAST_WPM:
        return "medium"
    return "fast"


def _sentence_count(text: str) -> int:
    """Count sentences in text by splitting on . ! ?"""
    parts = [p.strip() for p in _SENTENCE_SPLIT_RE.split(text) if p.strip()]
    return max(len(parts), 1)


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def analyze_pacing(
    transcript: Transcript,
    segment_duration: float = 30.0,
) -> PacingReport:
    """Analyse pacing of a transcript divided into time-based segments.

    Args:
        transcript: The transcript to analyse.
        segment_duration: Duration of each analysis window in seconds.

    Returns:
        A PacingReport with per-segment metrics and overall stats.
    """
    # Handle empty transcript
    if not transcript.segments:
        return PacingReport(
            segments=[],
            overall_wpm=0.0,
            overall_pace="slow",
            weak_intro=True,
            energy_drops=[],
            summary="No transcript data available.",
        )

    # Determine overall time range
    all_starts = [s.start_seconds for s in transcript.segments]
    all_ends = [s.end_seconds for s in transcript.segments]
    video_start = min(all_starts)
    video_end = max(all_ends)
    total_duration = video_end - video_start

    if total_duration <= 0:
        return PacingReport(
            segments=[],
            overall_wpm=0.0,
            overall_pace="slow",
            weak_intro=True,
            energy_drops=[],
            summary="No transcript data available.",
        )

    # Build time-based windows
    pacing_segments: list[PacingSegment] = []
    window_start = video_start

    while window_start < video_end:
        window_end = min(window_start + segment_duration, video_end)
        actual_window = window_end - window_start

        # Collect transcript segments that overlap with this window
        overlapping = [
            seg for seg in transcript.segments
            if seg.end_seconds > window_start and seg.start_seconds < window_end
        ]

        if not overlapping:
            window_start = window_end
            continue

        # Gather all words in the window
        all_words: list[str] = []
        speech_time = 0.0
        combined_text = ""

        for seg in overlapping:
            # Clamp segment to window boundaries
            clipped_start = max(seg.start_seconds, window_start)
            clipped_end = min(seg.end_seconds, window_end)
            clipped_duration = clipped_end - clipped_start
            seg_duration = seg.end_seconds - seg.start_seconds

            if seg_duration > 0 and clipped_duration > 0:
                speech_time += clipped_duration

            # Use word timings if available, otherwise fall back to text
            if seg.words:
                seg_words = [
                    w.word.strip()
                    for w in seg.words
                    if w.start >= window_start and w.end <= window_end and w.word.strip()
                ]
                all_words.extend(seg_words)
            else:
                # Proportional word count from text
                raw_words = [w for w in seg.text.split() if w.strip()]
                if seg_duration > 0 and actual_window > 0:
                    ratio = clipped_duration / seg_duration
                    count = round(len(raw_words) * ratio)
                    all_words.extend(raw_words[:count])
                else:
                    all_words.extend(raw_words)

            combined_text += " " + seg.text

        combined_text = combined_text.strip()
        word_count = len(all_words)

        # Metrics
        duration_minutes = actual_window / 60.0
        wpm = word_count / duration_minutes if duration_minutes > 0 else 0.0
        speech_density = min(speech_time / actual_window, 1.0) if actual_window > 0 else 0.0

        lower_words = [w.lower() for w in all_words if w]
        word_variety = (
            len(set(lower_words)) / len(lower_words) if lower_words else 0.0
        )

        sentence_cnt = _sentence_count(combined_text)
        avg_sentence_length = word_count / sentence_cnt if sentence_cnt > 0 else 0.0

        pace = _classify_pace(wpm)
        text_preview = combined_text[:50]

        pacing_segments.append(
            PacingSegment(
                start=window_start,
                end=window_end,
                wpm=round(wpm, 2),
                speech_density=round(speech_density, 4),
                word_variety=round(word_variety, 4),
                avg_sentence_length=round(avg_sentence_length, 2),
                pace=pace,
                text_preview=text_preview,
            )
        )

        window_start = window_end

    # Overall stats
    total_words = sum(
        len([w for w in seg.text.split() if w.strip()])
        for seg in transcript.segments
    )
    total_speech_seconds = sum(
        (seg.end_seconds - seg.start_seconds)
        for seg in transcript.segments
        if seg.end_seconds > seg.start_seconds
    )
    overall_wpm = (
        total_words / (total_speech_seconds / 60.0)
        if total_speech_seconds > 0
        else 0.0
    )
    overall_pace = _classify_pace(overall_wpm)

    # Weak intro: first segment slow OR low speech density
    weak_intro = False
    if pacing_segments:
        first = pacing_segments[0]
        weak_intro = first.pace == "slow" or first.speech_density < 0.3

    # Energy drops: 3+ consecutive slow segments
    energy_drops: list[dict] = []
    i = 0
    while i < len(pacing_segments):
        if pacing_segments[i].pace == "slow":
            j = i
            while j < len(pacing_segments) and pacing_segments[j].pace == "slow":
                j += 1
            run_length = j - i
            if run_length >= 3:
                drop_start = pacing_segments[i].start
                drop_end = pacing_segments[j - 1].end
                energy_drops.append(
                    {
                        "start": drop_start,
                        "end": drop_end,
                        "duration": round(drop_end - drop_start, 2),
                    }
                )
            i = j
        else:
            i += 1

    # Summary
    intro_str = "weak" if weak_intro else "strong"
    drop_count = len(energy_drops)
    drop_str = (
        f"{drop_count} energy drop{'s' if drop_count != 1 else ''} detected."
        if drop_count
        else "No energy drops detected."
    )
    summary = (
        f"Your video averages {overall_wpm:.0f} WPM. "
        f"Intro is {intro_str}. "
        f"{drop_str}"
    )

    return PacingReport(
        segments=pacing_segments,
        overall_wpm=round(overall_wpm, 2),
        overall_pace=overall_pace,
        weak_intro=weak_intro,
        energy_drops=energy_drops,
        summary=summary,
    )


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------


def format_pacing_report(report: PacingReport) -> str:
    """Format a PacingReport as a Markdown string.

    Returns:
        A Markdown document with a segment table, flagged sections, and
        overall stats.
    """
    lines: list[str] = []

    lines.append("# Pacing & Energy Report")
    lines.append("")

    # Overall stats section
    lines.append("## Overall Stats")
    lines.append("")
    lines.append(f"- **Overall WPM:** {report.overall_wpm:.0f}")
    lines.append(f"- **Overall Pace:** {report.overall_pace}")
    lines.append(f"- **Weak Intro:** {'Yes' if report.weak_intro else 'No'}")
    lines.append(f"- **Energy Drops:** {len(report.energy_drops)}")
    lines.append("")
    lines.append(f"> {report.summary}")
    lines.append("")

    if not report.segments:
        lines.append("_No segments to display._")
        return "\n".join(lines)

    # Segment table
    lines.append("## Segment Breakdown")
    lines.append("")
    lines.append(
        "| # | Start | End | WPM | Pace | Speech Density | Word Variety | Avg Sent. Len | Preview |"
    )
    lines.append(
        "|---|-------|-----|-----|------|----------------|--------------|---------------|---------|"
    )

    for idx, seg in enumerate(report.segments, start=1):
        flag = " ⚠" if seg.pace == "slow" else ""
        lines.append(
            f"| {idx} "
            f"| {seg.start:.1f}s "
            f"| {seg.end:.1f}s "
            f"| {seg.wpm:.0f}{flag} "
            f"| {seg.pace} "
            f"| {seg.speech_density:.2f} "
            f"| {seg.word_variety:.2f} "
            f"| {seg.avg_sentence_length:.1f} "
            f"| {seg.text_preview[:40]}... |"
        )

    lines.append("")

    # Flagged sections
    if report.energy_drops:
        lines.append("## Flagged Sections")
        lines.append("")
        lines.append("The following time ranges have 3+ consecutive slow segments:")
        lines.append("")
        for drop in report.energy_drops:
            lines.append(
                f"- **{drop['start']:.1f}s – {drop['end']:.1f}s** "
                f"({drop['duration']:.0f}s drop)"
            )
        lines.append("")

    if report.weak_intro:
        lines.append("## Intro Warning")
        lines.append("")
        lines.append(
            "> The first 30 seconds have a slow pace or low speech density. "
            "Consider tightening the intro to hook viewers faster."
        )
        lines.append("")

    return "\n".join(lines)
