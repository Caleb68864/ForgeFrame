"""Transcribe a plain media file to SRT / VTT / TXT and word-level JSON (prompt 36)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.adapters.stt import whisper_engine
from workshop_video_brain.edit_mcp.pipelines.media_files import require_streams, resolve_output
from workshop_video_brain.edit_mcp.pipelines.subtitle_files import transcript_to_cues, write_cues

FORMATS = ("srt", "vtt", "json", "txt")


def target_paths(source: Path, out_dir: Path, stem: str, formats, overwrite: bool) -> dict[str, Path]:
    """Every output checked (protected trees, overwrite) before any is written."""
    names = {"json": f"{stem}_transcript.json"}
    paths = {}
    for fmt in formats:
        name = names.get(fmt, f"{stem}.{fmt}")
        paths[fmt] = resolve_output(source, output_path=str(Path(out_dir) / name), overwrite=overwrite)
    return paths


def transcribe_to_files(source: Path, out_dir: Path, stem: str, formats=("srt", "vtt", "json"), model: str = "small",
                        language: str | None = None, max_line_length: int = 42, max_cue_seconds: float = 5.0,
                        overwrite: bool = False) -> dict:
    asset = probe_media(source)
    require_streams(asset, audio=True)
    paths = target_paths(source, out_dir, stem, formats, overwrite)
    with tempfile.TemporaryDirectory(prefix="wvb_stt_") as tmp:
        wav = whisper_engine.extract_audio(source, Path(tmp) / "audio.wav")
        transcript = whisper_engine.transcribe(wav, model=model, language=language)
    cues = transcript_to_cues(transcript, max_line_length, max_cue_seconds)
    for fmt, path in paths.items():
        if fmt == "json":
            from workshop_video_brain.workspace.safe_write import atomic_write_text
            atomic_write_text(path, transcript.to_json())
        else:
            write_cues(cues, path, fmt, max_line_length)
    words = sum(len(s.words) for s in transcript.segments)
    return {"paths": {k: str(v) for k, v in paths.items()}, "language": transcript.language,
            "engine": transcript.engine, "model": transcript.model or model,
            "segment_count": len(transcript.segments), "cue_count": len(cues), "word_count": words,
            "duration_seconds": round(asset.duration_seconds or 0.0, 3), "has_word_timings": words > 0}
