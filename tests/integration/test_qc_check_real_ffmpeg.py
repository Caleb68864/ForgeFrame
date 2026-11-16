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


# --- ROADMAP next #5: silence that matters, against real silencedetect -------

def _tone_with_gap(path, gap_start: float, gap_end: float, duration: float = 20.0):
    expr = f"if(between(t\\,{gap_start}\\,{gap_end})\\,0\\,0.3*sin(2*PI*440*t))"
    _ffmpeg("-f", "lavfi", "-i", f"aevalsrc={expr}:d={duration}:s=48000", str(path))
    return path


@requires_ffmpeg
def test_real_short_pause_passes(tmp_path):
    """One 1.5 s pause in a 20 s render used to fail the whole render."""
    wav = _tone_with_gap(tmp_path / "pause.wav", 8.0, 9.5)
    report = run_qc(wav, checks=["silence"])
    assert len(report.silence_regions) == 1
    assert "silence" in report.checks_passed, report.model_dump()
    assert report.duration_seconds == pytest.approx(20.0, abs=0.1)


@requires_ffmpeg
def test_real_long_gap_fails(tmp_path):
    wav = _tone_with_gap(tmp_path / "gap.wav", 8.0, 13.0)
    report = run_qc(wav, checks=["silence"])
    assert "silence" in report.checks_failed, report.model_dump()


@requires_ffmpeg
def test_real_dead_air_at_end_fails(tmp_path):
    wav = _tone_with_gap(tmp_path / "tail.wav", 17.0, 21.0)
    report = run_qc(wav, checks=["silence"])
    assert "silence" in report.checks_failed, report.model_dump()
    assert "end" in report.check_notes["silence"]


@requires_ffmpeg
def test_real_profile_check(tmp_path):
    from tests._testkit import make_test_clip
    from workshop_video_brain.edit_mcp.pipelines.qc_check import ExpectedProfile

    clip = make_test_clip(tmp_path / "bars.mp4", duration=1, fps=25, size=(320, 240))
    ok = run_qc(clip, checks=["profile"], expected_profile=ExpectedProfile(
        width=320, height=240, fps=25.0, video_codec="libx264", source="test"))
    assert ok.checks_passed == ["profile"], ok.model_dump()
    bad = run_qc(clip, checks=["profile"], expected_profile=ExpectedProfile(
        width=1920, height=1080, fps=30.0, video_codec="libx264", source="test"))
    assert bad.checks_failed == ["profile"]
    assert len(bad.profile_mismatches) == 2  # resolution, fps


@requires_ffmpeg
def test_qc_tool_profile_sources(tmp_path):
    from tests._testkit import call_tool, make_test_clip, solid_color_project
    from workshop_video_brain.edit_mcp.adapters.kdenlive.serializer import serialize_project
    from workshop_video_brain.edit_mcp.server.tools.render import qc_check

    clip = make_test_clip(tmp_path / "bars.mp4", duration=1, fps=25, size=(320, 240))

    # Render profile: preview is 1280x720 -> resolution mismatch.
    res = call_tool(qc_check, file_path=str(clip), checks="profile", profile="preview")
    assert res["status"] == "success", res
    assert res["data"]["checks_failed"] == ["profile"]
    assert "render profile 'preview'" in res["data"]["check_notes"]["profile"]

    # Project profile from the workspace's latest working copy.
    ws = tmp_path / "ws"
    wc = ws / "projects" / "working_copies"
    wc.mkdir(parents=True)
    serialize_project(solid_color_project(width=320, height=240, fps=25.0), wc / "p_v1.kdenlive")
    res = call_tool(qc_check, file_path=str(clip), checks="profile", workspace_path=str(ws))
    assert res["status"] == "success", res
    assert res["data"]["checks_passed"] == ["profile"], res["data"]

    bad = call_tool(qc_check, file_path=str(clip), profile="no-such-profile")
    assert bad["status"] == "error" and bad["error_type"] == "not_found", bad
