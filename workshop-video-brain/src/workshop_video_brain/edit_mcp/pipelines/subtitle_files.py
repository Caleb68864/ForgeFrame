"""Subtitle files: load and write SRT / VTT / JSON / TXT cues (shared by prompts 36-38)."""
from __future__ import annotations

from pathlib import Path

from workshop_video_brain.core.models.timeline import SubtitleCue
from workshop_video_brain.edit_mcp.pipelines.subtitle_pipeline import (
    _parse_srt_content,
    _wrap_text,
    export_srt,
    transcript_to_cues,
)

__all__ = ["seconds_to_vtt_time", "export_vtt", "transcript_to_cues", "load_cues", "write_cues", "export_txt"]

FORMATS = ("srt", "vtt", "txt")


def seconds_to_vtt_time(seconds: float) -> str:
    """``HH:MM:SS.mmm`` (total milliseconds rounded once, as the SRT writer does)."""
    total_ms = int(round(seconds * 1000))
    h, rem = divmod(total_ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def export_vtt(cues: list[SubtitleCue], max_line_length: int = 42) -> str:
    blocks = ["WEBVTT"]
    for cue in cues:
        blocks.append(f"{seconds_to_vtt_time(cue.start_seconds)} --> {seconds_to_vtt_time(cue.end_seconds)}\n"
                      f"{_wrap_text(cue.text, max_line_length)}")
    return "\n\n".join(blocks) + "\n"


def export_txt(cues: list[SubtitleCue]) -> str:
    return "".join(" ".join(c.text.split()) + "\n" for c in cues)


def load_cues(path: Path) -> list[SubtitleCue]:
    """Cues from ``.srt`` (line breaks kept), ``.vtt`` or ``.json`` (a ForgeFrame transcript or cue list)."""
    from workshop_video_brain.edit_mcp.adapters.transcript.parsers import parse_json_transcript, parse_vtt

    path = Path(path)
    ext = path.suffix.lower()
    text = path.read_text(encoding="utf-8-sig")
    if ext == ".srt":
        return _parse_srt_content(text)
    if ext == ".vtt":
        segments = parse_vtt(text)
    elif ext == ".json":
        segments = parse_json_transcript(text)
    else:
        raise ValueError(f"unsupported subtitle file {ext!r}; use .srt, .vtt or .json")
    return [SubtitleCue(start_seconds=s.start_seconds, end_seconds=s.end_seconds, text=s.text) for s in segments]


def write_cues(cues: list[SubtitleCue], path: Path, fmt: str, max_line_length: int = 42) -> Path:
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}, got {fmt!r}")
    text = {"srt": lambda: export_srt(cues, max_line_length), "vtt": lambda: export_vtt(cues, max_line_length),
            "txt": lambda: export_txt(cues)}[fmt]()
    from workshop_video_brain.workspace.safe_write import atomic_write_text
    return atomic_write_text(Path(path), text)
