"""audio_mix_music / audio_fade_file on real files (prompt 34)."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.server.bundles.audio_fade_file import audio_fade_file
from workshop_video_brain.edit_mcp.server.bundles.audio_mix_music import audio_mix_music

pytestmark = requires_ffmpeg_ffprobe
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "media_generated"


def _ffmpeg(*args):
    subprocess.run(["ffmpeg", "-v", "error", "-y", *args], check=True, capture_output=True, timeout=120)


def _band_db(path, t, freq=None, dur=0.5) -> float:
    af = (f"bandpass=f={freq}:width_type=q:w=2," if freq else "") + "volumedetect"
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-ss", str(t), "-t", str(dur), "-i", str(path), "-af", af,
                           "-f", "null", "-"], capture_output=True, text=True, timeout=120)
    match = re.search(r"mean_volume:\s*(-?[\d.]+|-inf)", proc.stderr)
    return float("-inf") if match.group(1) == "-inf" else float(match.group(1))


@pytest.fixture(scope="module")
def tones(tmp_path_factory):
    d = tmp_path_factory.mktemp("tones")
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=1000:duration=6", "-af",
            "volume='if(lt(mod(t,2),1),1,0)':eval=frame", "-ar", "48000", str(d / "voice.wav"))
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=200:duration=10", "-ar", "48000", str(d / "music.wav"))
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=200:duration=2", "-ar", "48000", str(d / "short.wav"))
    _ffmpeg("-f", "lavfi", "-i", "sine=frequency=440:duration=5", "-ar", "48000", str(d / "tone5.wav"))
    return d


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def test_registered():
    assert_registered("audio_mix_music", "audio_fade_file")


def _gap(path):
    on = (_band_db(path, 0.3, 200) + _band_db(path, 2.3, 200)) / 2
    off = (_band_db(path, 1.5, 200) + _band_db(path, 3.5, 200)) / 2
    return off - on, on, off


def test_ducking_is_measurable(tones, tmp_path):
    ducked = _ok(call_tool(audio_mix_music, str(tones / "voice.wav"), str(tones / "music.wav"), music_gain_db=-6,
                           duck_preset="strong", fade_in_seconds=0, fade_out_seconds=0, output_dir=str(tmp_path)))
    gap, on, off = _gap(ducked["output_path"])
    assert gap >= 6, (gap, on, off)
    assert ducked["duration_seconds"] == pytest.approx(6.0, abs=0.05)
    assert (ducked["sample_rate"], ducked["channels"]) == (48000, 2)
    flat = _ok(call_tool(audio_mix_music, str(tones / "voice.wav"), str(tones / "music.wav"), music_gain_db=-6,
                         duck=False, fade_in_seconds=0, fade_out_seconds=0, output_dir=str(tmp_path / "flat")))
    assert abs(_gap(flat["output_path"])[0]) < 1.5


def test_video_source_keeps_its_picture(tmp_path):
    data = _ok(call_tool(audio_mix_music, str(FIX / "test_clip_1080p2997_5s.mp4"),
                         str(FIX / "music_cinematic_short.mp3"), output_dir=str(tmp_path)))
    asset = probe_media(Path(data["output_path"]))
    assert (asset.video_codec, asset.width, asset.height) == ("h264", 1920, 1080)
    assert data["duration_seconds"] == pytest.approx(5.0, abs=0.1)
    assert (asset.audio_codec, asset.channels, asset.sample_rate) == ("aac", 2, 48000)


def test_short_music_loops(tones, tmp_path):
    data = _ok(call_tool(audio_mix_music, str(tones / "voice.wav"), str(tones / "short.wav"), duck=False,
                         fade_in_seconds=0, fade_out_seconds=0, output_dir=str(tmp_path)))
    assert data["music_looped"] and _band_db(data["output_path"], 4.5, 200) > -50


def test_fade_ends_are_quieter(tones, tmp_path):
    data = _ok(call_tool(audio_fade_file, str(tones / "tone5.wav"), 1.0, 1.0, output_dir=str(tmp_path)))
    start, middle, end = (_band_db(data["output_path"], t, dur=0.25) for t in (0.0, 2.5, 4.75))
    assert start <= middle - 10 and end <= middle - 10, (start, middle, end)


def test_fade_keeps_video(tmp_path):
    data = _ok(call_tool(audio_fade_file, str(FIX / "test_clip_1080p2997_5s.mp4"), 1.0, output_dir=str(tmp_path)))
    assert probe_media(Path(data["output_path"])).video_codec == "h264"


def test_silent_source_refused(tmp_path):
    result = call_tool(audio_fade_file, str(FIX / "greenscreen_reporter_720.mp4"), 1.0, output_dir=str(tmp_path))
    assert result["error_type"] == "media_unreadable"
    result = call_tool(audio_mix_music, str(FIX / "greenscreen_reporter_720.mp4"),
                       str(FIX / "music_cinematic_short.mp3"), output_dir=str(tmp_path))
    assert result["error_type"] == "media_unreadable"
    assert list(tmp_path.iterdir()) == []
    assert call_tool(audio_mix_music, str(FIX / "test_clip_1080p2997_5s.mp4"), str(tmp_path / "x.mp3"))["error_type"] == "missing_file"
