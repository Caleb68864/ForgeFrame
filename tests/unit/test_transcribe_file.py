"""transcribe_file with the engine faked (prompt 36; needs ffmpeg for a real source, no model)."""
from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest

from tests._testkit import call_tool, make_test_clip, requires_ffmpeg_ffprobe
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment, WordTiming
from workshop_video_brain.edit_mcp.adapters.stt import whisper_engine
from workshop_video_brain.edit_mcp.server.bundles.transcribe_file import transcribe_file


@pytest.fixture
def fake_engine(monkeypatch):
    def extract(src, out):
        Path(out).write_bytes(b"RIFF")
        return Path(out)

    def transcribe(wav, model="small", language=None, asset_id=None):
        words = [WordTiming(word=w, start=i * 0.4, end=i * 0.4 + 0.3) for i, w in enumerate("hello there world".split())]
        return Transcript(asset_id=uuid4(), engine="fake", model=model, language="en",
                          segments=[TranscriptSegment(start_seconds=0.0, end_seconds=1.1, text="hello there world",
                                                      words=words)])

    monkeypatch.setattr(whisper_engine, "is_available", lambda: True)
    monkeypatch.setattr(whisper_engine, "extract_audio", extract)
    monkeypatch.setattr(whisper_engine, "transcribe", transcribe)


@requires_ffmpeg_ffprobe
def test_writes_all_formats(tmp_path, fake_engine):
    clip = make_test_clip(tmp_path / "talk.mp4", duration=1.5, with_audio=True)
    result = call_tool(transcribe_file, str(clip), output_dir=str(tmp_path / "out"))
    assert result["status"] == "success", result
    data = result["data"]
    assert set(data["paths"]) == {"srt", "vtt", "json"} and data["has_word_timings"]
    back = Transcript.from_json(Path(data["paths"]["json"]).read_text())
    assert len(back.segments[0].words) == 3
    assert Path(data["paths"]["vtt"]).read_text().startswith("WEBVTT")
    assert not list((tmp_path / "out").glob("*.wav"))


@requires_ffmpeg_ffprobe
def test_protected_output_dir(tmp_path, fake_engine):
    clip = make_test_clip(tmp_path / "talk.mp4", duration=1.0, with_audio=True)
    raw = tmp_path / "ws" / "media" / "raw"
    raw.mkdir(parents=True)
    result = call_tool(transcribe_file, str(clip), output_dir=str(raw))
    assert result["error_type"] == "invalid_input" and list(raw.iterdir()) == []


def test_missing_engine_and_bad_args(tmp_path, monkeypatch):
    src = tmp_path / "a.mp4"
    src.write_bytes(b"x")
    monkeypatch.setattr(whisper_engine, "is_available", lambda: False)
    assert call_tool(transcribe_file, str(src))["error_type"] == "missing_dependency"
    assert call_tool(transcribe_file, str(src), formats="srt,docx")["error_type"] == "invalid_input"
    assert call_tool(transcribe_file, str(src), model="gigantic")["error_type"] == "invalid_input"
