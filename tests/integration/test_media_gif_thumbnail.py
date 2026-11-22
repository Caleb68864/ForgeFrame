"""media_gif / media_thumbnail on real files (prompt 32)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.server.bundles.media_gif import media_gif
from workshop_video_brain.edit_mcp.server.bundles.media_thumbnail import media_thumbnail

pytestmark = requires_ffmpeg_ffprobe
FIX = Path(__file__).resolve().parents[1] / "fixtures" / "media_generated"


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


@pytest.fixture
def red_then_blue(tmp_path) -> Path:
    out = tmp_path / "rb.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=red:s=320x240:r=25:d=2",
                    "-f", "lavfi", "-i", "color=blue:s=320x240:r=25:d=2", "-filter_complex",
                    "[0:v][1:v]concat=n=2:v=1:a=0", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
                   check=True, capture_output=True, timeout=60)
    return out


def test_registered():
    assert_registered("media_gif", "media_thumbnail")


def test_gif_window(tmp_path, red_then_blue):
    PIL = pytest.importorskip("PIL.Image")
    data = _ok(call_tool(media_gif, str(red_then_blue), start_seconds=2.5, seconds=1.0, fps=10, width=160,
                         output_dir=str(tmp_path / "o")))
    assert data["frame_count"] == 10 and data["width"] == 160
    with PIL.open(data["output_path"]) as image:
        r, g, b = image.convert("RGB").getpixel((80, 60))
    assert b > r + 50
    assert not list((tmp_path / "o").glob("*palette*"))


def test_webp(tmp_path, red_then_blue):
    data = _ok(call_tool(media_gif, str(red_then_blue), seconds=1.0, format="webp", output_dir=str(tmp_path)))
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name", "-of", "csv=p=0",
                            data["output_path"]], capture_output=True, text=True, timeout=60)
    assert "webp" in probe.stdout


def test_thumbnail_at_time_and_clamp(tmp_path):
    clip = FIX / "test_clip_1080p2997_5s.mp4"
    data = _ok(call_tool(media_thumbnail, str(clip), at_seconds=1.0, width=640, output_dir=str(tmp_path)))
    assert (data["width"], data["height"], data["mode"]) == (640, 360, "at")
    assert data["output_path"].endswith(".jpg")
    late = _ok(call_tool(media_thumbnail, str(clip), at_seconds=99, output_dir=str(tmp_path), overwrite=True))
    assert late["at_seconds"] < 5.005


def test_thumbnail_auto(tmp_path):
    data = _ok(call_tool(media_thumbnail, str(FIX / "greenscreen_reporter_720.mp4"), output_dir=str(tmp_path)))
    assert data["mode"] == "auto" and data["searched_from_seconds"] == pytest.approx(2.0, abs=0.1)


def test_thumbnail_audio_only_refused(tmp_path):
    result = call_tool(media_thumbnail, str(FIX / "music_cinematic_short.mp3"), output_dir=str(tmp_path))
    assert result["status"] == "error" and result["error_type"] == "media_unreadable"
    assert list(tmp_path.iterdir()) == []
