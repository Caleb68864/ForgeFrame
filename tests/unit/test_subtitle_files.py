"""Subtitle file module: VTT writer, loaders, word-aware cues (prompt 36; no ffmpeg)."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from workshop_video_brain.core.models.timeline import SubtitleCue
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment, WordTiming
from workshop_video_brain.edit_mcp.adapters.transcript.parsers import parse_vtt
from workshop_video_brain.edit_mcp.pipelines.subtitle_files import (
    export_vtt,
    load_cues,
    seconds_to_vtt_time,
    transcript_to_cues,
    write_cues,
)
from workshop_video_brain.edit_mcp.pipelines.subtitle_pipeline import generate_srt

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "transcripts"


def test_vtt_time():
    assert seconds_to_vtt_time(3661.2346) == "01:01:01.235"


def test_export_vtt_round_trips():
    cues = [SubtitleCue(start_seconds=0.5, end_seconds=2.25, text="Hello there"),
            SubtitleCue(start_seconds=3.0, end_seconds=4.125, text="Second cue")]
    text = export_vtt(cues)
    assert text.startswith("WEBVTT\n\n00:00:00.500 --> 00:00:02.250")
    parsed = parse_vtt(text)
    assert [(round(s.start_seconds, 3), round(s.end_seconds, 3), s.text) for s in parsed] == [
        (0.5, 2.25, "Hello there"), (3.0, 4.125, "Second cue")]


def test_generate_srt_unchanged_by_the_refactor():
    transcript = Transcript.from_json((FIX / "sample_tutorial.json").read_text())
    assert generate_srt(transcript) == (FIX / "sample_tutorial.expected.srt").read_text()


def test_word_aware_split():
    words = [WordTiming(word=f"w{i}", start=i * 0.5, end=i * 0.5 + 0.4) for i in range(24)]
    transcript = Transcript(asset_id=uuid4(), segments=[TranscriptSegment(
        start_seconds=0.0, end_seconds=12.0, text=" ".join(w.word for w in words), words=words)])
    cues = transcript_to_cues(transcript, max_duration=5.0)
    assert len(cues) == 3
    starts, ends = {w.start for w in words}, {w.end for w in words}
    assert all(c.start_seconds in starts and c.end_seconds in ends for c in cues)
    assert all(c.end_seconds - c.start_seconds <= 5.0 for c in cues)


def test_write_and_load(tmp_path):
    cues = [SubtitleCue(start_seconds=1.0, end_seconds=2.0, text="one\ntwo")]
    for fmt in ("srt", "vtt", "txt"):
        write_cues(cues, tmp_path / f"c.{fmt}", fmt)
    assert load_cues(tmp_path / "c.srt")[0].text == "one\ntwo"  # SRT keeps line breaks
    assert load_cues(tmp_path / "c.vtt")[0].start_seconds == 1.0
    assert (tmp_path / "c.txt").read_text() == "one two\n"
    with pytest.raises(ValueError):
        load_cues(tmp_path / "c.txt")
