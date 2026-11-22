"""Edit a recording by deleting transcript words: the cut list, and a retimed transcript (prompt 38).

Pure logic, no I/O beyond reading the transcript. Times stay in seconds here;
frames are only computed once, by the ``.kdenlive`` builder.
"""
from __future__ import annotations

import re
import string
from dataclasses import dataclass
from pathlib import Path

from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment, WordTiming

FILLERS = {"um", "uh", "erm", "er", "ah", "hmm", "mm"}


@dataclass(frozen=True)
class Word:
    index: int
    text: str
    start: float
    end: float
    segment_index: int


def load_transcript(path: Path) -> Transcript:
    from workshop_video_brain.edit_mcp.adapters.transcript.parsers import parse_transcript
    from uuid import uuid4

    path = Path(path)
    if path.suffix.lower() == ".json":
        try:
            return Transcript.from_json(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 -- not a ForgeFrame transcript: fall back to the generic parser
            pass
    return Transcript(asset_id=uuid4(), segments=parse_transcript(path))


def units_of(transcript: Transcript) -> tuple[list[Word], str]:
    """Words (numbered from 0) when any segment has word timings, else one unit per segment."""
    units: list[Word] = []
    if any(s.words for s in transcript.segments):
        for si, seg in enumerate(transcript.segments):
            for w in seg.words:
                if w.end > w.start:
                    units.append(Word(len(units), w.word.strip(), w.start, w.end, si))
        return units, "word"
    for si, seg in enumerate(transcript.segments):
        if seg.end_seconds > seg.start_seconds:
            units.append(Word(len(units), seg.text.strip(), seg.start_seconds, seg.end_seconds, si))
    return units, "segment"


def load_units(transcript_path: Path) -> tuple[list[Word], str]:
    return units_of(load_transcript(transcript_path))


def numbered_view(units: list[Word], start: int = 0, limit: int = 400) -> tuple[str, int | None]:
    """``S3 [41] the [42] zipper ...`` lines, one per segment; returns (text, next_start or None)."""
    chosen = units[start:start + limit]
    lines, current, parts = [], None, []
    for u in chosen:
        if u.segment_index != current:
            if parts:
                lines.append(f"S{current} " + " ".join(parts))
            current, parts = u.segment_index, []
        parts.append(f"[{u.index}] {u.text}")
    if parts:
        lines.append(f"S{current} " + " ".join(parts))
    next_start = start + limit if start + limit < len(units) else None
    return "\n".join(lines), next_start


def normalise(word: str) -> str:
    return word.lower().strip().strip(string.punctuation + "“”‘’…")


def select_deletions(units: list[Word], spec: list[dict], remove_fillers: bool = False) -> set[int]:
    """Indices to delete from ``{"words": [a, b]}``, ``{"segment": i}``, ``{"text": "..."}``, ``{"time": [s, e]}``."""
    deleted: set[int] = set()
    n = len(units)
    segments = {u.segment_index for u in units}
    norm = [normalise(u.text) for u in units]
    for item in spec:
        if not isinstance(item, dict) or len(item) != 1:
            raise ValueError(f"each delete item needs exactly one of words/segment/text/time: {item!r}")
        (key, value), = item.items()
        if key == "words":
            if not (isinstance(value, list) and len(value) == 2 and all(isinstance(v, int) for v in value)):
                raise ValueError(f"words needs [first, last] indices: {item!r}")
            a, b = value
            if not (0 <= a <= b < n):
                raise ValueError(f"word range {value} is outside 0-{n - 1}: {item!r}")
            deleted.update(range(a, b + 1))
        elif key == "segment":
            if value not in segments:
                raise ValueError(f"segment {value!r} does not exist: {item!r}")
            deleted.update(u.index for u in units if u.segment_index == value)
        elif key == "text":
            phrase = [normalise(w) for w in str(value).split() if normalise(w)]
            if not phrase:
                raise ValueError(f"text is empty: {item!r}")
            for i in range(n - len(phrase) + 1):
                if norm[i:i + len(phrase)] == phrase:
                    deleted.update(range(i, i + len(phrase)))
        elif key == "time":
            if not (isinstance(value, list) and len(value) == 2):
                raise ValueError(f"time needs [start, end] seconds: {item!r}")
            s, e = float(value[0]), float(value[1])
            deleted.update(u.index for u in units if s <= (u.start + u.end) / 2 <= e)
        else:
            raise ValueError(f"unknown delete key {key!r} (use words, segment, text or time): {item!r}")
    if remove_fillers:
        deleted.update(i for i, w in enumerate(norm) if w in FILLERS)
    return deleted


def keep_ranges(units: list[Word], deleted: set[int], duration: float, pad: float = 0.05,
                min_keep: float = 0.2) -> list[tuple[float, float]]:
    """Source ranges to keep: each run of deleted units is cut from ``prev kept end + pad`` to
    ``next kept start - pad`` (file start / end when the run reaches it)."""
    cuts = []
    i = 0
    while i < len(units):
        if units[i].index not in deleted:
            i += 1
            continue
        j = i
        while j + 1 < len(units) and units[j + 1].index in deleted:
            j += 1
        start = units[i - 1].end + pad if i > 0 else 0.0
        end = units[j + 1].start - pad if j + 1 < len(units) else duration
        if end > start:
            cuts.append((start, end))
        i = j + 1
    ranges, cursor = [], 0.0
    for start, end in sorted(cuts):
        if start > cursor:
            ranges.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < duration:
        ranges.append((cursor, duration))
    merged: list[tuple[float, float]] = []
    for start, end in ranges:
        if end - start < min_keep:
            continue
        if merged and start <= merged[-1][1] + 1e-9:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((round(start, 6), round(end, 6)))
    return merged


def remap_time(t: float, ranges: list[tuple[float, float]]) -> float | None:
    """Where source time *t* lands in the edited output, or None if it was cut."""
    offset = 0.0
    for start, end in ranges:
        if start - 1e-9 <= t <= end + 1e-9:
            return round(offset + (t - start), 6)
        offset += end - start
    return None


def retime_transcript(transcript: Transcript, ranges: list[tuple[float, float]], deleted: set[int]) -> Transcript:
    """The transcript of the edited media: deleted units gone, the rest remapped, segments rebuilt."""
    units, granularity = units_of(transcript)
    deleted_keys = {(u.segment_index, u.start, u.end) for u in units if u.index in deleted}
    segments = []
    for si, seg in enumerate(transcript.segments):
        if granularity == "word":
            words = []
            for w in seg.words:
                if (si, w.start, w.end) in deleted_keys:
                    continue
                start, end = remap_time(w.start, ranges), remap_time(w.end, ranges)
                if start is None or end is None:
                    continue
                words.append(WordTiming(word=w.word, start=start, end=end, confidence=w.confidence))
            if not words:
                continue
            segments.append(TranscriptSegment(start_seconds=words[0].start, end_seconds=words[-1].end,
                                              text=re.sub(r"\s+", " ", " ".join(w.word.strip() for w in words)).strip(),
                                              confidence=seg.confidence, words=words))
        else:
            if (si, seg.start_seconds, seg.end_seconds) in deleted_keys:
                continue
            start, end = remap_time(seg.start_seconds, ranges), remap_time(seg.end_seconds, ranges)
            if start is None or end is None:
                continue
            segments.append(seg.model_copy(update={"start_seconds": start, "end_seconds": end}))
    return transcript.model_copy(update={"segments": segments,
                                         "raw_text": " ".join(s.text for s in segments)})


def edit_summary(ranges: list[tuple[float, float]], duration: float) -> dict:
    kept = sum(e - s for s, e in ranges)
    return {"kept_seconds": round(kept, 3), "removed_seconds": round(max(0.0, duration - kept), 3),
            "cut_count": max(0, len(ranges) - 1 + (1 if ranges and ranges[0][0] > 0 else 0)
                             + (1 if ranges and ranges[-1][1] < duration - 1e-6 else 0))}
