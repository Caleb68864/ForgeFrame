"""Integration test for the two-pass loudnorm pipeline (real FFmpeg).

Generates a quiet sine-wave clip, runs it through ``normalize_two_pass_file`` /
the ``audio_normalize_two_pass`` MCP tool, then re-measures with the existing
``measure_loudness`` adapter and asserts the integrated loudness lands within
+/-1 LU of target. Also exercises the video re-mux path (video stream-copied,
audio normalized). Skipped automatically when ffmpeg/ffprobe are not on PATH.

Lives in ``tests/integration/`` (not ``external/``) because it only uses the
local FFmpeg install -- no network or third-party service.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from workshop_video_brain.edit_mcp.adapters.ffmpeg.probe import measure_loudness
from workshop_video_brain.edit_mcp.pipelines.loudnorm_two_pass import (
    normalize_two_pass_file,
)

ffmpeg_available = shutil.which("ffmpeg") is not None
ffprobe_available = shutil.which("ffprobe") is not None
pytestmark = pytest.mark.skipif(
    not (ffmpeg_available and ffprobe_available),
    reason="ffmpeg/ffprobe not available on PATH",
)

_TARGET_I = -16.0
_TOLERANCE_LU = 1.0


def _invoke(tool, *args, **kwargs):
    fn = getattr(tool, "fn", tool)
    return fn(*args, **kwargs)


def _make_quiet_sine(path: Path, seconds: int = 3, gain_db: int = -14) -> None:
    """Render a quiet sine tone well below the -16 LUFS target."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:duration={seconds}",
        "-af", f"volume={gain_db}dB",
        "-c:a", "pcm_s16le",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _make_quiet_video(path: Path, seconds: int = 3, gain_db: int = -14) -> None:
    """Render a short video with a quiet sine audio track."""
    cmd = [
        "ffmpeg", "-y",
        "-f", "lavfi",
        "-i", f"testsrc=size=320x240:rate=24:duration={seconds}",
        "-f", "lavfi",
        "-i", f"sine=frequency=440:duration={seconds}",
        "-af", f"volume={gain_db}dB",
        "-c:v", "libx264", "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        str(path),
    ]
    subprocess.run(cmd, check=True, capture_output=True)


def _stream(path: Path, codec_type: str) -> dict:
    proc = subprocess.run(
        [
            "ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path),
        ],
        capture_output=True, text=True, check=True,
    )
    for s in json.loads(proc.stdout).get("streams", []):
        if s.get("codec_type") == codec_type:
            return s
    raise AssertionError(f"no {codec_type} stream in {path}")


@pytest.fixture()
def quiet_clip(tmp_path: Path) -> Path:
    clip = tmp_path / "media" / "raw" / "quiet.wav"
    clip.parent.mkdir(parents=True, exist_ok=True)
    _make_quiet_sine(clip)
    assert clip.exists() and clip.stat().st_size > 0
    return clip


class TestLoudnormTwoPassReal:
    def test_lands_within_1_lu_of_target(self, quiet_clip, tmp_path):
        out = tmp_path / "media" / "processed" / "quiet_normalized.wav"
        out.parent.mkdir(parents=True, exist_ok=True)

        # Source starts well below target.
        before = measure_loudness(quiet_clip)
        assert before is not None
        assert before.input_i < _TARGET_I - 3  # genuinely quiet

        result = normalize_two_pass_file(quiet_clip, out, target_i=_TARGET_I)
        assert result["success"] is True, result
        assert result["has_video"] is False
        assert out.exists() and out.stat().st_size > 0
        # measured pass-1 values were captured
        assert result["measured"]["thresh"] is not None

        # Re-measure the output: must land within +/-1 LU of target.
        after = measure_loudness(out)
        assert after is not None
        delta = abs(after.input_i - _TARGET_I)
        assert delta <= _TOLERANCE_LU, (
            f"integrated loudness {after.input_i} not within "
            f"+/-{_TOLERANCE_LU} LU of {_TARGET_I} (delta={delta:.3f})"
        )

        # Source untouched.
        assert quiet_clip.exists()

    def test_video_source_remux_keeps_video_and_normalizes_audio(self, tmp_path):
        raw = tmp_path / "media" / "raw"
        raw.mkdir(parents=True, exist_ok=True)
        clip = raw / "quiet_vid.mp4"
        _make_quiet_video(clip)

        out = tmp_path / "media" / "processed" / "quiet_vid_normalized.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)

        result = normalize_two_pass_file(clip, out, target_i=_TARGET_I)
        assert result["success"] is True, result
        assert result["has_video"] is True
        assert out.exists() and out.stat().st_size > 0

        # Video stream preserved (same codec/resolution).
        vs = _stream(out, "video")
        assert vs["codec_name"] == "h264"
        assert int(vs["width"]) == 320 and int(vs["height"]) == 240
        # Audio present and normalized within tolerance.
        _stream(out, "audio")
        after = measure_loudness(out)
        assert after is not None
        assert abs(after.input_i - _TARGET_I) <= _TOLERANCE_LU

    def test_mcp_tool_end_to_end(self, quiet_clip, tmp_path):
        from workshop_video_brain.edit_mcp.server.bundles.audio_normalize_two_pass import (  # noqa: E501
            audio_normalize_two_pass,
        )

        res = _invoke(
            audio_normalize_two_pass, str(tmp_path), source="media/raw/quiet.wav"
        )
        assert res["status"] == "success", res
        data = res["data"]
        out = Path(data["output"])
        assert out.parent == tmp_path / "media" / "processed"
        assert out.exists() and out.stat().st_size > 0

        after = measure_loudness(out)
        assert after is not None
        assert abs(after.input_i - _TARGET_I) <= _TOLERANCE_LU
        # achieved_i reported by the tool also lands in tolerance.
        assert data["achieved_i"] is not None
        assert abs(data["achieved_i"] - _TARGET_I) <= _TOLERANCE_LU
