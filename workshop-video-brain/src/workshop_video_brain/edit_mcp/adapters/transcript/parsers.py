"""Parsers for SRT, VTT, and JSON transcript formats.

All parsers normalize into a flat ``list[TranscriptSegment]``. Format is
detected from the file extension, falling back to content sniffing when the
extension is missing or ambiguous.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment

_SRT_TIME_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*"
    r"(\d{2}):(\d{2}):(\d{2})[,.](\d{3})"
)
_VTT_TIME_RE = re.compile(
    r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})\s*-->\s*"
    r"(?:(\d+):)?(\d{2}):(\d{2})[.,](\d{3})"
)


def _srt_ts_to_seconds(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(text: str) -> list[TranscriptSegment]:
    """Parse an SRT subtitle document into transcript segments."""
    segments: list[TranscriptSegment] = []
    blocks = re.split(r"\r?\n\r?\n+", text.strip())
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if not lines:
            continue
        time_line_idx = None
        for idx, line in enumerate(lines):
            if _SRT_TIME_RE.search(line):
                time_line_idx = idx
                break
        if time_line_idx is None:
            continue
        match = _SRT_TIME_RE.search(lines[time_line_idx])
        assert match is not None
        start = _srt_ts_to_seconds(*match.groups()[0:4])
        end = _srt_ts_to_seconds(*match.groups()[4:8])
        text_lines = lines[time_line_idx + 1 :]
        segment_text = " ".join(text_lines).strip()
        segments.append(
            TranscriptSegment(start_seconds=start, end_seconds=end, text=segment_text)
        )
    return segments


def _vtt_ts_to_seconds(h: str | None, m: str, s: str, ms: str) -> float:
    hours = int(h) if h else 0
    return hours * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_vtt(text: str) -> list[TranscriptSegment]:
    """Parse a WebVTT document into transcript segments."""
    segments: list[TranscriptSegment] = []
    blocks = re.split(r"\r?\n\r?\n+", text.strip())
    for block in blocks:
        lines = [ln for ln in block.splitlines() if ln.strip() != ""]
        if not lines:
            continue
        time_line_idx = None
        for idx, line in enumerate(lines):
            if _VTT_TIME_RE.search(line):
                time_line_idx = idx
                break
        if time_line_idx is None:
            continue
        match = _VTT_TIME_RE.search(lines[time_line_idx])
        assert match is not None
        groups = match.groups()
        start = _vtt_ts_to_seconds(groups[0], groups[1], groups[2], groups[3])
        end = _vtt_ts_to_seconds(groups[4], groups[5], groups[6], groups[7])
        text_lines = lines[time_line_idx + 1 :]
        segment_text = " ".join(text_lines).strip()
        segments.append(
            TranscriptSegment(start_seconds=start, end_seconds=end, text=segment_text)
        )
    return segments


def parse_json_transcript(raw: str) -> list[TranscriptSegment]:
    """Parse a JSON transcript.

    Accepts either a serialized ForgeFrame :class:`Transcript` (with a
    ``segments`` key), a bare list of segment dicts, or a list of dicts using
    ``start``/``end`` instead of ``start_seconds``/``end_seconds``.
    """
    data = json.loads(raw)

    if isinstance(data, dict) and "segments" in data:
        try:
            return Transcript.model_validate(data).segments
        except Exception:
            raw_segments = data["segments"]
    elif isinstance(data, list):
        raw_segments = data
    else:
        raise ValueError("Unrecognized JSON transcript shape")

    segments: list[TranscriptSegment] = []
    for item in raw_segments:
        if "start_seconds" in item and "end_seconds" in item:
            start = float(item["start_seconds"])
            end = float(item["end_seconds"])
        else:
            start = float(item["start"])
            end = float(item["end"])
        segments.append(
            TranscriptSegment(
                start_seconds=start,
                end_seconds=end,
                text=str(item.get("text", "")),
                confidence=float(item.get("confidence", 1.0)),
                speaker=item.get("speaker"),
            )
        )
    return segments


def parse_transcript(path: str | Path) -> list[TranscriptSegment]:
    """Auto-detect the format of *path* and parse it into segments."""
    path = Path(path)
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8")

    if suffix == ".srt":
        return parse_srt(raw)
    if suffix == ".vtt":
        return parse_vtt(raw)
    if suffix == ".json":
        return parse_json_transcript(raw)

    stripped = raw.lstrip()
    if stripped.upper().startswith("WEBVTT"):
        return parse_vtt(raw)
    if stripped.startswith("{") or stripped.startswith("["):
        return parse_json_transcript(raw)
    if _SRT_TIME_RE.search(raw):
        return parse_srt(raw)

    raise ValueError(f"Unable to detect transcript format for {path}")
