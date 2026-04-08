"""Subtitle pipeline: SRT generation, parsing, and export.

Converts a Transcript into SRT subtitle cues, and provides import/export
utilities.
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path

from workshop_video_brain.core.models.timeline import SubtitleCue
from workshop_video_brain.core.models.transcript import Transcript


# ---------------------------------------------------------------------------
# SRT helpers
# ---------------------------------------------------------------------------


def _seconds_to_srt_time(seconds: float) -> str:
    """Convert float seconds to SRT timestamp HH:MM:SS,mmm."""
    total_ms = int(round(seconds * 1000))
    ms = total_ms % 1000
    total_s = total_ms // 1000
    s = total_s % 60
    total_m = total_s // 60
    m = total_m % 60
    h = total_m // 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _srt_time_to_seconds(time_str: str) -> float:
    """Parse SRT timestamp HH:MM:SS,mmm to float seconds."""
    time_str = time_str.strip().replace(",", ".")
    parts = time_str.split(":")
    if len(parts) != 3:
        raise ValueError(f"Invalid SRT time: {time_str!r}")
    h = int(parts[0])
    m = int(parts[1])
    s_ms = float(parts[2])
    return h * 3600 + m * 60 + s_ms


def _wrap_text(text: str, max_line_length: int) -> str:
    """Wrap *text* to *max_line_length* characters per line."""
    lines = textwrap.wrap(text, width=max_line_length)
    return "\n".join(lines) if lines else text


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_srt(
    transcript: Transcript,
    max_line_length: int = 42,
    max_duration: float = 5.0,
) -> str:
    """Generate SRT subtitle content from a Transcript.

    Each TranscriptSegment longer than *max_duration* seconds is split.
    Lines are wrapped to *max_line_length* characters.

    Args:
        transcript:       The transcript to convert.
        max_line_length:  Maximum characters per subtitle line.
        max_duration:     Maximum cue duration in seconds; longer segments
                          are split at word boundaries.

    Returns:
        SRT-formatted string.
    """
    cues: list[SubtitleCue] = []

    for segment in transcript.segments:
        start = segment.start_seconds
        end = segment.end_seconds
        text = segment.text.strip()
        if not text:
            continue

        duration = end - start
        if duration <= max_duration:
            cues.append(SubtitleCue(start_seconds=start, end_seconds=end, text=text))
        else:
            # Split at approximate word boundaries
            words = text.split()
            total_words = len(words)
            # Compute how many chunks we need
            chunks_needed = max(1, int(duration / max_duration + 0.5))
            words_per_chunk = max(1, total_words // chunks_needed)
            chunk_duration = duration / chunks_needed

            chunk_start = start
            for i in range(0, total_words, words_per_chunk):
                chunk_words = words[i: i + words_per_chunk]
                chunk_end = min(end, chunk_start + chunk_duration)
                cues.append(
                    SubtitleCue(
                        start_seconds=chunk_start,
                        end_seconds=chunk_end,
                        text=" ".join(chunk_words),
                    )
                )
                chunk_start = chunk_end

    return export_srt(cues, max_line_length=max_line_length)


def export_srt(cues: list[SubtitleCue], max_line_length: int = 42) -> str:
    """Serialise a list of SubtitleCue objects to an SRT string."""
    blocks: list[str] = []
    for idx, cue in enumerate(cues, start=1):
        start_ts = _seconds_to_srt_time(cue.start_seconds)
        end_ts = _seconds_to_srt_time(cue.end_seconds)
        wrapped = _wrap_text(cue.text, max_line_length)
        blocks.append(f"{idx}\n{start_ts} --> {end_ts}\n{wrapped}")
    return "\n\n".join(blocks) + "\n" if blocks else ""


def import_srt(path: Path) -> list[SubtitleCue]:
    """Parse an SRT file and return a list of SubtitleCue objects."""
    path = Path(path)
    content = path.read_text(encoding="utf-8-sig")
    return _parse_srt_content(content)


def _parse_srt_content(content: str) -> list[SubtitleCue]:
    """Parse raw SRT text into SubtitleCue objects."""
    cues: list[SubtitleCue] = []
    # Split on blank lines separating blocks
    blocks = re.split(r"\n\s*\n", content.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        # First line: index (skip)
        # Second line: timecode
        timecode_line = lines[1]
        match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
            timecode_line,
        )
        if not match:
            continue
        try:
            start = _srt_time_to_seconds(match.group(1))
            end = _srt_time_to_seconds(match.group(2))
        except ValueError:
            continue
        text = "\n".join(lines[2:]).strip()
        cues.append(SubtitleCue(start_seconds=start, end_seconds=end, text=text))
    return cues


def save_srt(content: str, workspace_root: Path, filename: str) -> Path:
    """Write SRT *content* to ``workspace_root/reports/{filename}``.

    The reports directory is created if it does not exist.

    Returns:
        The path that was written.
    """
    workspace_root = Path(workspace_root)
    reports_dir = workspace_root / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    out_path = reports_dir / filename
    out_path.write_text(content, encoding="utf-8")
    return out_path
