"""Integration test for the video denoise pipeline (real FFmpeg).

Generates a noisy clip (testsrc + noise filter), runs it through
``denoise_video_file`` / the ``media_denoise_video`` MCP tool, and asserts the
output exists with matching duration/resolution AND that noise actually
decreased -- measured via the mean temporal frame-difference
(``signalstats.YDIF``), which is dominated by frame-to-frame noise. Skipped
automatically when ffmpeg/ffprobe are not on PATH.

Lives in ``tests/integration/`` (not ``external/``) because it only uses the
local FFmpeg install -- no network or third-party service.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.pipelines.denoise_video import (
    denoise_video_file,
)

ffmpeg_available = shutil.which("ffmpeg") is not None
ffprobe_available = shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(
    not (ffmpeg_available and ffprobe_available),
    reason="ffmpeg/ffprobe not available on PATH",
)

_YDIF_RE = re.compile(r"YDIF=([0-9.]+)")


def _invoke(tool, *args, **kwargs):
    fn = getattr(tool, "fn", tool)
    return fn(*args, **kwargs)


def _make_noisy_clip(path: Path, seconds: int = 2, fps: int = 24) -> None:
    """Render a testsrc clip with heavy additive noise."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"testsrc=size=320x240:rate={fps}:duration={seconds}",
        "-vf", "noise=alls=40:allf=t+u",
        "-c:v", "libx264", "-qp", "10", "-pix_fmt", "yuv420p",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _video_stream(path: Path) -> dict:
    proc = subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)],
        capture_output=True, text=True, check=True,
    )
    for s in json.loads(proc.stdout).get("streams", []):
        if s.get("codec_type") == "video":
            return s
    raise AssertionError(f"no video stream in {path}")


def _mean_ydif(path: Path) -> float:
    """Mean temporal frame-difference (signalstats.YDIF) over the clip.

    Higher = more frame-to-frame variation; additive noise inflates it, so a
    successful denoise lowers this value.
    """
    proc = subprocess.run(
        [
            "ffmpeg", "-i", str(path),
            "-vf", "signalstats,metadata=print:key=lavfi.signalstats.YDIF",
            "-f", "null", "-",
        ],
        capture_output=True, text=True, check=False,
    )
    vals = [float(m) for m in _YDIF_RE.findall(proc.stderr)]
    assert vals, f"no YDIF samples parsed for {path}"
    return sum(vals) / len(vals)


@pytest.fixture()
def noisy_clip(tmp_path: Path) -> Path:
    clip = tmp_path / "media" / "raw" / "noisy.mp4"
    clip.parent.mkdir(parents=True, exist_ok=True)
    _make_noisy_clip(clip)
    assert clip.exists() and clip.stat().st_size > 0
    return clip


class TestDenoiseVideoReal:
    def test_hqdn3d_reduces_noise_and_preserves_geometry(
        self, noisy_clip, tmp_path
    ):
        out = tmp_path / "media" / "processed" / "noisy_denoised.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)

        noisy_ydif = _mean_ydif(noisy_clip)

        result = denoise_video_file(noisy_clip, out, strength="strong")
        assert result["success"] is True, result
        assert result["method"] == "hqdn3d"
        assert out.exists() and out.stat().st_size > 0

        # Resolution preserved.
        src_vs = _video_stream(noisy_clip)
        out_vs = _video_stream(out)
        assert int(out_vs["width"]) == int(src_vs["width"]) == 320
        assert int(out_vs["height"]) == int(src_vs["height"]) == 240

        # Duration preserved (within a couple of frames).
        src_dur = float(src_vs.get("duration") or 0) or 2.0
        out_dur = float(out_vs.get("duration") or 0) or 2.0
        assert abs(out_dur - src_dur) < 0.25

        # Noise actually decreased.
        denoised_ydif = _mean_ydif(out)
        assert denoised_ydif < noisy_ydif, (
            f"denoise did not reduce temporal noise: "
            f"noisy YDIF={noisy_ydif:.3f}, denoised YDIF={denoised_ydif:.3f}"
        )

        # Source untouched.
        assert noisy_clip.exists()

    def test_atadenoise_method_runs(self, noisy_clip, tmp_path):
        out = tmp_path / "ata.mp4"
        result = denoise_video_file(
            noisy_clip, out, strength="strong", method="atadenoise"
        )
        assert result["success"] is True
        assert result["method"] == "atadenoise"
        assert out.exists() and out.stat().st_size > 0
        assert _mean_ydif(out) < _mean_ydif(noisy_clip)

    def test_mcp_tool_end_to_end(self, noisy_clip, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.media_denoise_video import (  # noqa: E501
            media_denoise_video,
        )

        noisy_ydif = _mean_ydif(noisy_clip)
        res = _invoke(
            media_denoise_video, str(tmp_path),
            source="media/raw/noisy.mp4", strength="strong",
        )
        assert res["status"] == "success", res
        data = res["data"]
        out = Path(data["output"])
        assert out.parent == tmp_path / "media" / "processed"
        assert out.exists() and out.stat().st_size > 0
        assert data["method"] == "hqdn3d"
        assert data["strength"] == "strong"
        assert _video_stream(out)["codec_name"] == "h264"
        assert _mean_ydif(out) < noisy_ydif
