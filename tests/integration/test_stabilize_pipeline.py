"""Integration test for the video stabilization pipeline.

Empirically generates a tiny synthetic *shaky* clip with FFmpeg (a testsrc
pattern crop-jittered by a per-frame expression), runs it through
``stabilize_file`` / the ``media_stabilize`` MCP tool, and verifies the output
with ffprobe. Skipped automatically when ffmpeg/ffprobe are not on PATH.

Lives in ``tests/integration/`` (not ``external/``) because it only uses the
local FFmpeg install -- no network or third-party service.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines.stabilize import (
    stabilize_file,
    vidstab_available,
)

ffmpeg_available = shutil.which("ffmpeg") is not None
ffprobe_available = shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(
    not (ffmpeg_available and ffprobe_available),
    reason="ffmpeg/ffprobe not available on PATH",
)


def _invoke(tool, *args, **kwargs):
    """Call an MCP tool, unwrapping FastMCP's FunctionTool if present."""
    fn = getattr(tool, "fn", tool)
    return fn(*args, **kwargs)


def _make_shaky_clip(path: Path, seconds: int = 2, fps: int = 24) -> None:
    """Render a short clip whose framing jitters frame-to-frame (fake shake).

    Uses a larger testsrc pattern cropped with a sinusoidal per-frame offset so
    vidstabdetect has real inter-frame motion to measure.
    """
    crop = (
        "crop=320:240"
        ":x='16+8*sin(n/2)+4*sin(n*1.7)'"
        ":y='16+8*cos(n/3)+4*cos(n*2.1)'"
    )
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"testsrc=size=360x280:rate={fps}:duration={seconds}",
        "-vf", crop,
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _ffprobe_streams(path: Path) -> list[dict]:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error",
            "-show_streams", "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout).get("streams", [])


def _video_stream(path: Path) -> dict:
    for s in _ffprobe_streams(path):
        if s.get("codec_type") == "video":
            return s
    raise AssertionError(f"no video stream in {path}")


@pytest.fixture()
def shaky_clip(tmp_path: Path) -> Path:
    clip = tmp_path / "media" / "raw" / "shaky.mp4"
    clip.parent.mkdir(parents=True, exist_ok=True)
    _make_shaky_clip(clip)
    assert clip.exists() and clip.stat().st_size > 0
    return clip


class TestStabilizePipelineReal:
    def test_pipeline_produces_playable_video(self, shaky_clip, tmp_path):
        out = tmp_path / "media" / "processed" / "shaky_stabilized.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)

        result = stabilize_file(shaky_clip, out)

        assert result["success"] is True, result
        assert result["method"] in ("vidstab", "deshake")
        # Expected method matches what this build actually supports.
        assert result["method"] == ("vidstab" if vidstab_available() else "deshake")
        assert out.exists() and out.stat().st_size > 0

        vs = _video_stream(out)
        assert vs["codec_name"] == "h264"
        assert int(vs["width"]) == 320
        assert int(vs["height"]) == 240

        # Source is untouched.
        assert shaky_clip.exists() and shaky_clip.stat().st_size > 0

    def test_deshake_fallback_runs(self, shaky_clip, tmp_path):
        out = tmp_path / "deshaked.mp4"
        result = stabilize_file(shaky_clip, out, force_deshake=True)
        assert result["success"] is True
        assert result["method"] == "deshake"
        assert out.exists() and out.stat().st_size > 0
        assert _video_stream(out)["codec_name"] == "h264"

    def test_media_stabilize_tool_end_to_end(self, shaky_clip, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.stabilize import (
            media_stabilize,
        )

        # Workspace root = the tmp_path that already holds media/raw/shaky.mp4.
        res = _invoke(media_stabilize, str(tmp_path), source="media/raw/shaky.mp4")
        assert res["status"] == "success", res
        data = res["data"]
        out = Path(data["output"])
        assert out.exists() and out.stat().st_size > 0
        assert out.parent == tmp_path / "media" / "processed"
        assert data["method"] in ("vidstab", "deshake")
        assert _video_stream(out)["codec_name"] == "h264"
        # Raw source preserved.
        assert shaky_clip.exists()
