"""transcribe_file with the real faster-whisper tiny model, only where it is already cached (prompt 36)."""
from __future__ import annotations

from pathlib import Path

import pytest

from tests._testkit import call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.core.models.transcript import Transcript
from workshop_video_brain.edit_mcp.pipelines.subtitle_files import load_cues
from workshop_video_brain.edit_mcp.server.bundles.transcribe_file import transcribe_file

TINY = Path.home() / ".cache/huggingface/hub/models--Systran--faster-whisper-tiny"
pytestmark = [requires_ffmpeg_ffprobe,
              pytest.mark.skipif(not TINY.exists(), reason="faster-whisper tiny model not cached (no downloads in tests)")]
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "media_generated"


def test_tiny_model_writes_parseable_files(tmp_path):
    result = call_tool(transcribe_file, str(FIX / "test_audio_with_silence.mp4"), formats="srt,vtt,json,txt",
                       model="tiny", output_dir=str(tmp_path))
    assert result["status"] == "success", result
    paths = result["data"]["paths"]
    assert all(Path(p).exists() for p in paths.values())
    load_cues(Path(paths["srt"]))
    load_cues(Path(paths["vtt"]))
    Transcript.from_json(Path(paths["json"]).read_text())  # tones: no assertion on words
