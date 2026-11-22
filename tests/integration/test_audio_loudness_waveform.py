"""audio_loudness / audio_waveform_image on real files (prompt 35)."""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import measure_loudness, probe_media
from workshop_video_brain.edit_mcp.server.bundles.audio_loudness import audio_loudness
from workshop_video_brain.edit_mcp.server.bundles.audio_waveform_image import audio_waveform_image

pytestmark = requires_ffmpeg_ffprobe
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "media_generated"


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def test_registered():
    assert_registered("audio_loudness", "audio_waveform_image")


def test_measure_file_and_folder(tmp_path):
    data = _ok(call_tool(audio_loudness, str(FIX / "music_cinematic_short.mp3")))
    assert data["results"][0]["lufs"] == pytest.approx(-13.3, abs=0.5)
    folder = tmp_path / "set"
    folder.mkdir()
    shutil.copy(FIX / "music_cinematic_short.mp3", folder / "a.mp3")
    shutil.copy(FIX / "test_audio_with_silence.mp4", folder / "b.mp4")
    data = _ok(call_tool(audio_loudness, str(folder)))
    assert data["clips_scanned"] == 2 and "lufs_spread" in data["summary"]


def test_normalize_two_pass(tmp_path):
    data = _ok(call_tool(audio_loudness, str(FIX / "test_audio_with_silence.mp4"), target_lufs=-16.0,
                         output_dir=str(tmp_path)))
    remeasured = measure_loudness(Path(data["output_path"]))
    assert remeasured.input_i == pytest.approx(-16.0, abs=1.0)
    assert probe_media(Path(data["output_path"])).width > 0  # the video stream is still there
    assert call_tool(audio_loudness, str(tmp_path), target_lufs=-16.0)["error_type"] == "invalid_input"
    assert call_tool(audio_loudness, str(FIX / "test_audio_with_silence.mp4"), target_lufs=3.0)["error_type"] == "invalid_input"


def test_waveform(tmp_path):
    PIL = pytest.importorskip("PIL.Image")
    data = _ok(call_tool(audio_waveform_image, str(FIX / "music_cinematic_short.mp3"), width=1280, height=240,
                         output_dir=str(tmp_path)))
    with PIL.open(data["output_path"]) as image:
        assert image.size == (1280, 240)
        assert any(lo != hi for lo, hi in image.convert("RGB").getextrema())


def test_waveform_of_silent_video_refused(tmp_path):
    result = call_tool(audio_waveform_image, str(FIX / "greenscreen_reporter_720.mp4"), output_dir=str(tmp_path))
    assert result["error_type"] == "media_unreadable" and list(tmp_path.iterdir()) == []
