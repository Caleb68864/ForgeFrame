"""media_text_edit on a real file with a hand-written word transcript (prompt 38)."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pytest

from tests._testkit import assert_registered, call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.core.models.transcript import Transcript, TranscriptSegment, WordTiming
from workshop_video_brain.edit_mcp.pipelines.subtitle_files import load_cues
from workshop_video_brain.edit_mcp.server.tools.text_edit import media_text_edit, transcript_words

pytestmark = requires_ffmpeg_ffprobe
CLIP = Path(__file__).resolve().parents[1] / "fixtures" / "media_generated" / "test_clip_1080p2997_5s.mp4"


def write_transcript(path: Path, step=0.5, count=10):
    words = [WordTiming(word=f"w{i}", start=step * i, end=step * i + 0.4) for i in range(count)]
    t = Transcript(asset_id=uuid4(), segments=[TranscriptSegment(start_seconds=0.0, end_seconds=words[-1].end,
                                                                 text=" ".join(w.word for w in words), words=words)])
    path.write_text(t.to_json())
    return path


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def test_registered_and_words(tmp_path):
    assert_registered("transcript_words", "media_text_edit")
    data = _ok(call_tool(transcript_words, str(write_transcript(tmp_path / "t.json"))))
    assert data["granularity"] == "word" and data["numbered_view"].startswith("S0 [0] w0 [1] w1")


def test_file_output(tmp_path):
    t = write_transcript(tmp_path / "t.json")
    data = _ok(call_tool(media_text_edit, str(CLIP), str(t), delete='[{"words": [3, 5]}]', output_dir=str(tmp_path)))
    from workshop_video_brain.edit_mcp.pipelines.media_files import output_summary
    out = output_summary(Path(data["paths"]["file"]))
    assert out["duration_seconds"] == pytest.approx(5.005 - 1.5, abs=0.1) and out["has_audio"] and out["width"] == 1920
    assert load_cues(Path(data["paths"]["srt"]))[-1].end_seconds <= 3.6


def test_cutlist_output(tmp_path):
    t = write_transcript(tmp_path / "t.json")
    data = _ok(call_tool(media_text_edit, str(CLIP), str(t), delete='[{"words": [3, 5]}]', output="cutlist",
                         output_dir=str(tmp_path)))
    saved = json.loads(Path(data["paths"]["cutlist"]).read_text())
    assert saved["ranges"][0] == [0.0, 1.45] and saved["ranges"][1][0] == 2.95
    assert saved["ranges"][1][1] == pytest.approx(5.005, abs=0.01)
    assert "file" not in data["paths"]


def test_wrong_transcript_and_bad_spec(tmp_path):
    long = write_transcript(tmp_path / "long.json", step=1.0, count=12)
    assert call_tool(media_text_edit, str(CLIP), str(long))["error_type"] == "invalid_input"
    t = write_transcript(tmp_path / "t.json")
    assert call_tool(media_text_edit, str(CLIP), str(t), delete="{nope")["error_type"] == "bad_json_param"
    assert call_tool(media_text_edit, str(CLIP), str(t), delete='[{"words": [3, 50]}]')["error_type"] == "invalid_input"
