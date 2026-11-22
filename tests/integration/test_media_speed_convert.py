"""media_speed / media_rotate_flip / media_convert / media_extract_audio on real files (prompt 31)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, make_test_clip, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
from workshop_video_brain.edit_mcp.server.bundles.media_convert import media_convert
from workshop_video_brain.edit_mcp.server.bundles.media_extract_audio import media_extract_audio
from workshop_video_brain.edit_mcp.server.bundles.media_rotate_flip import media_rotate_flip
from workshop_video_brain.edit_mcp.server.bundles.media_speed import media_speed

pytestmark = requires_ffmpeg_ffprobe
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "media_generated"
CLIP = FIX / "test_clip_1080p2997_5s.mp4"


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def test_registered():
    assert_registered("media_speed", "media_rotate_flip", "media_convert", "media_extract_audio")


@pytest.mark.parametrize("factor, expected, tol", [(2.0, 2.5, 0.12), (0.5, 10.0, 0.15)])
def test_speed(tmp_path, factor, expected, tol):
    data = _ok(call_tool(media_speed, str(CLIP), factor, output_dir=str(tmp_path)))
    assert data["duration_seconds"] == pytest.approx(expected, abs=tol) and data["has_audio"]


def test_speed_video_only(tmp_path):
    clip = make_test_clip(tmp_path / "mute.mp4", duration=2.0, with_audio=False)
    data = _ok(call_tool(media_speed, str(clip), 2.0, output_dir=str(tmp_path / "o")))
    assert data["has_audio"] is False and data["duration_seconds"] == pytest.approx(1.0, abs=0.1)


def test_rotate_and_flip(tmp_path):
    PIL = pytest.importorskip("PIL.Image")
    clip = make_test_clip(tmp_path / "c.mp4", duration=1.0, size=(320, 240))
    data = _ok(call_tool(media_rotate_flip, str(clip), rotate=90, output_dir=str(tmp_path / "r")))
    assert (data["width"], data["height"]) == (240, 320)
    halves = tmp_path / "halves.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=red:s=320x240:d=1,drawbox=x=0:y=0:w=160:h=240:color=blue:t=fill",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(halves)], check=True, capture_output=True, timeout=60)
    flipped = Path(_ok(call_tool(media_rotate_flip, str(halves), flip="horizontal",
                                 output_dir=str(tmp_path / "f")))["output_path"])
    png = tmp_path / "frame.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(flipped), "-frames:v", "1", str(png)],
                   check=True, capture_output=True, timeout=60)
    with PIL.open(png) as image:
        r, g, b = image.convert("RGB").getpixel((40, 120))
    assert r > 150 and b < 100, (r, g, b)


def test_convert_webm_and_scale(tmp_path):
    webm = _ok(call_tool(media_convert, str(CLIP), format="webm", output_dir=str(tmp_path)))
    asset = probe_media(Path(webm["output_path"]))
    assert asset.video_codec == "vp9" and asset.audio_codec == "opus"
    small = _ok(call_tool(media_convert, str(CLIP), max_height=720, output_dir=str(tmp_path / "s")))
    assert (small["width"], small["height"]) == (1280, 720)


def test_convert_mp3_to_wav_keeps_stereo(tmp_path):
    data = _ok(call_tool(media_convert, str(FIX / "music_cinematic_short.mp3"), format="wav", output_dir=str(tmp_path)))
    assert (data["sample_rate"], data["channels"]) == (44100, 2)


def test_extract_audio(tmp_path):
    wav = _ok(call_tool(media_extract_audio, str(CLIP), output_dir=str(tmp_path)))
    assert (wav["sample_rate"], wav["channels"]) == (48000, 2)
    assert wav["duration_seconds"] == pytest.approx(5.0, abs=0.05)
    mp3 = _ok(call_tool(media_extract_audio, str(CLIP), format="mp3", output_dir=str(tmp_path)))
    assert probe_media(Path(mp3["output_path"])).audio_codec == "mp3"


def test_extract_audio_from_silent_video_is_refused(tmp_path):
    result = call_tool(media_extract_audio, str(FIX / "greenscreen_reporter_720.mp4"), output_dir=str(tmp_path))
    assert result["status"] == "error" and result["error_type"] == "media_unreadable"
    assert list(tmp_path.iterdir()) == []
