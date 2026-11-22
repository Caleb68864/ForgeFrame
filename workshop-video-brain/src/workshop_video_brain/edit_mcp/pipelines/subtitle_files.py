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

FORMATS = ("srt", "vtt", "txt", "ass")


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
    if ext == ".ass":
        raise ValueError("ASS input is not supported; convert from the SRT/VTT source")
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


def write_cues(cues: list[SubtitleCue], path: Path, fmt: str, max_line_length: int = 42, *,
               style=None, width: int = 1920, height: int = 1080) -> Path:
    """Write *cues* as srt / vtt / txt / ass (``style`` and the play size apply to ass)."""
    if fmt not in FORMATS:
        raise ValueError(f"format must be one of {', '.join(FORMATS)}, got {fmt!r}")
    if fmt == "ass":
        from workshop_video_brain.edit_mcp.pipelines.subtitle_track import SubtitleStyle, cues_to_ass
        text = cues_to_ass(cues, SubtitleStyle.from_input(style), width, height)
    else:
        text = {"srt": lambda: export_srt(cues, max_line_length), "vtt": lambda: export_vtt(cues, max_line_length),
                "txt": lambda: export_txt(cues)}[fmt]()
    from workshop_video_brain.workspace.safe_write import atomic_write_text
    return atomic_write_text(Path(path), text)


# ---------------------------------------------------------------------------
# pure transforms (prompt 37)
# ---------------------------------------------------------------------------

def _cue(start: float, end: float, text: str) -> SubtitleCue:
    return SubtitleCue(start_seconds=start, end_seconds=end, text=text)


def shift_cues(cues: list[SubtitleCue], offset: float = 0.0, scale: float = 1.0,
               from_seconds: float = 0.0) -> tuple[list[SubtitleCue], int]:
    """``t' = t * scale + offset`` for cues starting at/after ``from_seconds``; returns (cues, dropped).

    A cue that ends at or before 0 is dropped; a start below 0 is clamped.
    ``scale`` fixes frame-rate drift (25 vs 23.976 fps: 25/23.976).
    """
    if not 0.5 <= scale <= 2.0:
        raise ValueError(f"scale must be between 0.5 and 2.0, got {scale}")
    out, dropped = [], 0
    for cue in cues:
        if cue.start_seconds < from_seconds:
            out.append(cue.model_copy())
            continue
        start, end = cue.start_seconds * scale + offset, cue.end_seconds * scale + offset
        if end <= 0:
            dropped += 1
            continue
        out.append(_cue(max(0.0, start), end, cue.text))
    return out, dropped


def merge_cues(groups: list[tuple[list[SubtitleCue], float]]) -> tuple[list[SubtitleCue], int]:
    """Each group shifted by its offset, all sorted by (start, end); returns (cues, overlapping pairs)."""
    merged = [_cue(c.start_seconds + off, c.end_seconds + off, c.text) for cues, off in groups for c in cues]
    merged.sort(key=lambda c: (c.start_seconds, c.end_seconds))
    overlaps = sum(1 for a, b in zip(merged, merged[1:]) if b.start_seconds < a.end_seconds)
    return merged, overlaps


def split_cues(cues: list[SubtitleCue], at_seconds: float, rebase: bool = True):
    """(before, after) at ``at_seconds``; a straddling cue is cut in two (same text)."""
    first, second = [], []
    for cue in cues:
        if cue.end_seconds <= at_seconds:
            first.append(cue.model_copy())
        elif cue.start_seconds >= at_seconds:
            second.append(cue.model_copy())
        else:
            first.append(_cue(cue.start_seconds, at_seconds, cue.text))
            second.append(_cue(at_seconds, cue.end_seconds, cue.text))
    if rebase:
        second = [_cue(c.start_seconds - at_seconds, c.end_seconds - at_seconds, c.text) for c in second]
    return first, second


def rewrap_cues(cues: list[SubtitleCue], max_line_length: int = 42, max_lines: int = 2) -> list[SubtitleCue]:
    """Rewrap to ``max_line_length``; a cue needing more than ``max_lines`` lines becomes several cues
    sharing its time in proportion to their characters."""
    import textwrap

    out = []
    for cue in cues:
        lines = textwrap.wrap(" ".join(cue.text.split()), width=max_line_length) or [""]
        chunks = ["\n".join(lines[i:i + max_lines]) for i in range(0, len(lines), max_lines)]
        total_chars = sum(len(c) for c in chunks) or 1
        start, duration = cue.start_seconds, cue.end_seconds - cue.start_seconds
        for n, chunk in enumerate(chunks):
            end = cue.end_seconds if n == len(chunks) - 1 else start + duration * len(chunk) / total_chars
            out.append(_cue(start, end, chunk))
            start = end
    return out


def cues_to_text(cues: list[SubtitleCue]) -> str:
    return export_txt(cues)


def burn_subtitles_file(source: Path, subtitles: Path, output: Path, style=None,
                        scratch_dir: Path | None = None):
    """Burn *subtitles* into *source* with an ASS sized to the real video (not a fixed 1920x1080)."""
    import tempfile

    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.runner import run_ffmpeg
    from workshop_video_brain.edit_mcp.pipelines._common import escape_filter_path
    from workshop_video_brain.edit_mcp.pipelines.media_files import ENCODE_VIDEO_ARGS, has_audio, require_streams

    asset = probe_media(source)
    require_streams(asset, video=True)
    cues = load_cues(subtitles)

    def run(folder: Path):
        ass = Path(folder) / "subtitles.ass"
        write_cues(cues, ass, "ass", style=style, width=asset.width, height=asset.height)
        args = ["-vf", f"ass={escape_filter_path(ass)}", *ENCODE_VIDEO_ARGS]
        args += ["-c:a", "copy"] if has_audio(asset) else []
        return run_ffmpeg(args, source, output, overwrite=True, pre_input_args=["-hide_banner"])

    if scratch_dir is not None:
        Path(scratch_dir).mkdir(parents=True, exist_ok=True)
        return run(Path(scratch_dir)), len(cues)
    with tempfile.TemporaryDirectory(prefix="wvb_burn_") as tmp:
        return run(Path(tmp)), len(cues)
