"""media_burn_subtitles: the cue renders, is timed, and is sized to the real video (prompt 37)."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tests._testkit import call_tool, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.pipelines.subtitle_files import burn_subtitles_file
from workshop_video_brain.edit_mcp.server.tools.subtitle_files import media_burn_subtitles

pytestmark = requires_ffmpeg_ffprobe
STYLE = '{"size": 72, "position": "center"}'


@pytest.fixture
def clip_and_srt(tmp_path):
    clip = tmp_path / "black.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=black:s=640x360:r=25:d=3",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(clip)], check=True, capture_output=True, timeout=60)
    srt = tmp_path / "s.srt"
    srt.write_text("1\n00:00:00,500 --> 00:00:02,500\nHELLO\n")
    return clip, srt


def _white_box(video: Path, t: float, tmp: Path):
    PIL = pytest.importorskip("PIL.Image")
    png = tmp / f"f{t}.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", str(t), "-i", str(video), "-frames:v", "1", str(png)],
                   check=True, capture_output=True, timeout=60)
    with PIL.open(png) as image:
        gray = image.convert("L")
        box = gray.point(lambda v: 255 if v > 200 else 0).getbbox()
    return box


def _check(video: Path, tmp: Path):
    from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import probe_media
    asset = probe_media(video)
    assert (asset.width, asset.height) == (640, 360)
    assert asset.duration_seconds == pytest.approx(3.0, abs=0.1)
    box = _white_box(video, 1.5, tmp)
    assert box is not None and box[1] < 200 < box[3] + 40, box  # text near the middle band
    assert box[3] - box[1] > 30, f"text too small ({box}): PlayRes not the real size"
    assert _white_box(video, 2.8, tmp) is None


def test_burn(clip_and_srt, tmp_path):
    clip, srt = clip_and_srt
    result = call_tool(media_burn_subtitles, str(clip), str(srt), style=STYLE, output_dir=str(tmp_path / "o"))
    assert result["status"] == "success", result
    _check(Path(result["data"]["output_path"]), tmp_path)


def test_burn_escapes_an_awkward_scratch_path(clip_and_srt, tmp_path):
    clip, srt = clip_and_srt
    out = tmp_path / "escaped.mp4"
    result, _count = burn_subtitles_file(clip, srt, out, style=STYLE, scratch_dir=tmp_path / "it's a dir: x")
    assert result.success, result.stderr_tail
    _check(out, tmp_path)
