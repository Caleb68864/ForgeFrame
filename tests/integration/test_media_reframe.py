"""media_reframe / media_render_social_clips on real files (prompt 33)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests._testkit import assert_registered, call_tool, make_test_clip, requires_ffmpeg_ffprobe
from workshop_video_brain.edit_mcp.server.bundles.media_reframe import media_reframe
from workshop_video_brain.edit_mcp.server.bundles.social_render import media_render_social_clips

pytestmark = requires_ffmpeg_ffprobe
ROOT = Path(__file__).resolve().parents[1]
CLIP = ROOT / "fixtures" / "media_generated" / "test_clip_1080p2997_5s.mp4"


def _ok(result):
    assert result["status"] == "success", result
    return result["data"]


def test_registered():
    assert_registered("media_reframe", "media_render_social_clips")


def test_pad_and_blur(tmp_path):
    pad = _ok(call_tool(media_reframe, str(CLIP), aspect="9:16", mode="pad", output_dir=str(tmp_path)))
    assert (pad["width"], pad["height"]) == (1080, 1920)
    assert pad["duration_seconds"] == pytest.approx(5.0, abs=0.1) and pad["has_audio"]
    blur = _ok(call_tool(media_reframe, str(CLIP), aspect="1:1", mode="blur", output_dir=str(tmp_path)))
    assert (blur["width"], blur["height"]) == (1080, 1080)


def test_smart_follows_the_moving_box(tmp_path):
    PIL = pytest.importorskip("PIL.Image")
    src = tmp_path / "box.mp4"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
                    "color=c=black:s=640x360:r=25:d=3,drawbox=x='480+40*sin(t*6)':y=150:w=60:h=60:color=white:t=fill",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True, capture_output=True, timeout=60)
    data = _ok(call_tool(media_reframe, str(src), aspect="9:16", mode="smart", output_dir=str(tmp_path / "o")))
    assert data["focus_x"] > 0.6
    png = tmp_path / "mid.png"
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", "1.5", "-i", data["output_path"], "-frames:v", "1", str(png)],
                   check=True, capture_output=True, timeout=60)
    with PIL.open(png) as image:
        assert max(image.convert("L").getdata()) > 200  # the white box is in frame


def test_render_manifest(tmp_path):
    manifest = tmp_path / "clips_manifest.json"
    manifest.write_text(json.dumps([
        {"clip_id": "a", "start_seconds": 0.0, "end_seconds": 2.0, "aspect_ratio": "9:16", "title": "A"},
        {"clip_id": "b", "start_seconds": 2.5, "end_seconds": 4.5, "aspect_ratio": "9:16", "title": "B"},
        {"clip_id": "c", "start_seconds": 99.0, "end_seconds": 100.0, "aspect_ratio": "9:16"},
    ]))
    data = _ok(call_tool(media_render_social_clips, str(CLIP), str(manifest), output_dir=str(tmp_path / "out"),
                         mode="pad"))
    assert [r["clip_id"] for r in data["rendered"]] == ["a", "b"]
    assert all((r["width"], r["height"]) == (1080, 1920) for r in data["rendered"])
    assert all(r["duration_seconds"] == pytest.approx(2.0, abs=0.1) for r in data["rendered"])
    assert [s["clip_id"] for s in data["skipped"]] == ["c"] and data["failed"] == []


def test_real_social_package_manifest(tmp_path):
    from workshop_video_brain.edit_mcp.pipelines.social_clips import generate_social_package

    ws = tmp_path / "ws"
    (ws / "transcripts").mkdir(parents=True)
    shutil.copy(ROOT / "fixtures" / "transcripts" / "sample_tutorial.json", ws / "transcripts" / "clip_transcript.json")
    generate_social_package(ws, max_clips=1)
    manifest = ws / "reports" / "social" / "clips_manifest.json"
    entry = json.loads(manifest.read_text())[0]
    src = make_test_clip(tmp_path / "long.mp4", duration=90.0, size=(320, 180), with_audio=True)
    data = _ok(call_tool(media_render_social_clips, str(src), str(manifest), height=320, mode="pad",
                         output_dir=str(tmp_path / "out")))
    assert len(data["rendered"]) == 1
    span = min(entry["end_seconds"], 90.0) - entry["start_seconds"]
    assert data["rendered"][0]["duration_seconds"] == pytest.approx(span, abs=0.15)
    assert (data["rendered"][0]["width"], data["rendered"][0]["height"]) == (180, 320)


def test_validation(tmp_path):
    assert call_tool(media_reframe, str(CLIP), aspect="2:1")["error_type"] == "invalid_input"
    assert call_tool(media_reframe, str(CLIP), mode="zoom")["error_type"] == "invalid_input"
    assert call_tool(media_reframe, str(CLIP), mode="crop", focus_x=1.5)["error_type"] == "invalid_input"
    bad = tmp_path / "m.json"
    bad.write_text("[1, 2]")
    assert call_tool(media_render_social_clips, str(CLIP), str(bad), clip_indices="[5]")["error_type"] == "invalid_index"
