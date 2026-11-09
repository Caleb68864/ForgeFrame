"""qc_check against real ffmpeg output (not hand-written stderr fixtures).

The unit tests mock ``subprocess.run``; their old clipping fixture was text
ffmpeg never prints, so the clipping check was a no-op that stayed green.
These cases generate real media with lavfi and assert the verdicts.
"""
from __future__ import annotations

import subprocess

import pytest

from tests._testkit import requires_ffmpeg
from workshop_video_brain.edit_mcp.pipelines.qc_check import run_qc


def _ffmpeg(*args: str) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", *args],
        check=True, capture_output=True, timeout=60,
    )


@pytest.fixture
def clipped_wav(tmp_path):
    out = tmp_path / "clipped.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=1,volume=20", str(out))
    return out


@pytest.fixture
def clean_wav(tmp_path):
    out = tmp_path / "clean.wav"
    _ffmpeg("-f", "lavfi", "-i", "sine=f=440:d=1", str(out))
    return out


@pytest.fixture
def video_only_mp4(tmp_path):
    out = tmp_path / "video_only.mp4"
    _ffmpeg("-f", "lavfi", "-i", "color=c=gray:s=64x64:d=1", "-pix_fmt", "yuv420p", str(out))
    return out


@requires_ffmpeg
def test_real_clipping_detected(clipped_wav):
    report = run_qc(clipped_wav, checks=["clipping"])
    assert report.audio_clipping is True, report.model_dump()
    assert "clipping" in report.checks_failed
    assert report.audio_peak_db is not None and report.audio_peak_db > -0.1
    assert report.audio_flat_factor and report.audio_flat_factor > 0


@requires_ffmpeg
def test_real_clean_audio_not_clipping(clean_wav):
    report = run_qc(clean_wav, checks=["clipping"])
    assert report.audio_clipping is False, report.model_dump()
    assert "clipping" in report.checks_passed
    assert report.overall_pass


@requires_ffmpeg
def test_video_only_audio_checks_skip_with_reason(video_only_mp4):
    report = run_qc(video_only_mp4, checks=["silence", "clipping"])
    assert report.checks_passed == [], report.model_dump()
    assert set(report.checks_skipped) == {"silence", "clipping"}
    assert all("ffmpeg exited" in report.check_errors[c] for c in ("silence", "clipping"))
    assert not report.overall_pass


@requires_ffmpeg
def test_qc_tool_rejects_unknown_check(clean_wav):
    from tests._testkit import call_tool
    from workshop_video_brain.edit_mcp.server.tools.render import qc_check

    result = call_tool(qc_check, file_path=str(clean_wav), checks="clipping,blackframes")
    assert result["status"] == "error", result
    assert "blackframes" in result["message"]
