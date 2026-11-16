"""TDD tests for QC automation pipeline."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.edit_mcp.pipelines.qc_check import ALL_CHECKS, run_qc


# --- fixtures ---------------------------------------------------------------

SAMPLE_PATH = Path("/tmp/test_render.mp4")

BLACK_DETECT_STDERR = (
    "[blackdetect @ 0x1234] black_start:0.00 black_end:2.50 black_duration:2.50\n"
    "[blackdetect @ 0x1234] black_start:58.00 black_end:60.00 black_duration:2.00\n"
)

SILENCE_DETECT_STDERR = (
    "[silencedetect @ 0x5678] silence_start: 10.5\n"
    "[silencedetect @ 0x5678] silence_end: 15.2 | silence_duration: 4.7\n"
)

# Real astats summary shape (ffmpeg 7.x) for a sine driven 20x into the rails.
# The previous fixture ("Flat_factor detected ...") was text ffmpeg never
# prints, which is how a no-op clipping check stayed green.
CLIPPING_STDERR = (
    "[Parsed_astats_0 @ 0x1] Channel: 1\n"
    "[Parsed_astats_0 @ 0x1] Peak level dB: 0.000265\n"
    "[Parsed_astats_0 @ 0x1] Flat factor: 31.336683\n"
    "[Parsed_astats_0 @ 0x1] Overall\n"
    "[Parsed_astats_0 @ 0x1] Peak level dB: 0.000265\n"
    "[Parsed_astats_0 @ 0x1] Flat factor: 31.336683\n"
)

# Clean decoder output carrying a clean astats summary, so one stderr can
# stand in for every ffmpeg-backed check.
CLEAN_STDERR = (
    "[Parsed_astats_0 @ 0x1] Overall\n"
    "[Parsed_astats_0 @ 0x1] Peak level dB: -18.063656\n"
    "[Parsed_astats_0 @ 0x1] Flat factor: 0.000000\n"
    "size=N/A time=00:01:00.00 bitrate=N/A speed=120x\n"
)


def _mock_subprocess(stderr: str):
    """Return a mock subprocess.run result with the given stderr."""
    result = MagicMock()
    result.stderr = stderr
    result.returncode = 0
    return result


# --- black frames -----------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_black_frames_detected(mock_run):
    mock_run.return_value = _mock_subprocess(BLACK_DETECT_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["black_frames"])

    assert len(report.black_frames) == 2
    assert report.black_frames[0].start_seconds == 0.0
    assert report.black_frames[0].end_seconds == 2.5
    assert "black_frames" in report.checks_failed
    assert not report.overall_pass


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_no_black_frames(mock_run):
    mock_run.return_value = _mock_subprocess(CLEAN_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["black_frames"])

    assert len(report.black_frames) == 0
    assert "black_frames" in report.checks_passed
    assert report.overall_pass


# --- silence ----------------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_silence_detected(mock_run):
    mock_run.return_value = _mock_subprocess(SILENCE_DETECT_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["silence"])

    assert len(report.silence_regions) == 1
    assert report.silence_regions[0].start_seconds == pytest.approx(10.5)
    assert report.silence_regions[0].end_seconds == pytest.approx(15.2)
    assert "silence" in report.checks_failed


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_no_silence(mock_run):
    mock_run.return_value = _mock_subprocess(CLEAN_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["silence"])

    assert len(report.silence_regions) == 0
    assert "silence" in report.checks_passed


# --- loudness ---------------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
@patch(
    "workshop_video_brain.edit_mcp.pipelines.qc_check.measure_loudness",
    create=True,
)
def test_loudness_good(mock_loudness, mock_run):
    mock_loudness.return_value = {"input_i": -16.0, "input_tp": -3.0, "input_lra": 7.0}
    with patch(
        "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.measure_loudness",
        mock_loudness,
        create=True,
    ):
        report = run_qc(SAMPLE_PATH, checks=["loudness"])

    assert report.loudness_lufs == -16.0
    assert report.true_peak_dbtp == -3.0
    assert "loudness" in report.checks_passed


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_loudness_too_quiet(mock_run):
    mock_loudness = MagicMock(return_value={"input_i": -28.0, "input_tp": -6.0, "input_lra": 12.0})
    with patch(
        "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.measure_loudness",
        mock_loudness,
        create=True,
    ):
        report = run_qc(SAMPLE_PATH, checks=["loudness"])

    assert report.loudness_lufs == -28.0
    assert "loudness" in report.checks_failed


# --- clipping ---------------------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_clipping_detected(mock_run):
    mock_run.return_value = _mock_subprocess(CLIPPING_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["clipping"])

    assert report.audio_clipping is True
    assert "clipping" in report.checks_failed


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_no_clipping(mock_run):
    mock_run.return_value = _mock_subprocess(CLEAN_STDERR)
    report = run_qc(SAMPLE_PATH, checks=["clipping"])

    assert report.audio_clipping is False
    assert "clipping" in report.checks_passed


# --- file size --------------------------------------------------------------

def test_file_size_too_small(tmp_path):
    tiny = tmp_path / "tiny.mp4"
    tiny.write_bytes(b"\x00" * 100)  # 100 bytes
    report = run_qc(tiny, checks=["file_size"])

    assert "file_size" in report.checks_failed
    assert not report.overall_pass


def test_file_size_reasonable(tmp_path):
    normal = tmp_path / "normal.mp4"
    normal.write_bytes(b"\x00" * 50_000)  # 50 KB
    report = run_qc(normal, checks=["file_size"])

    assert "file_size" in report.checks_passed
    assert report.overall_pass


# --- missing filter (skip, not fail) ---------------------------------------

@patch(
    "workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run",
    side_effect=FileNotFoundError("ffmpeg not found"),
)
def test_missing_filter_skips(mock_run):
    report = run_qc(SAMPLE_PATH, checks=["black_frames"])

    assert "black_frames" in report.checks_skipped
    assert "black_frames" not in report.checks_failed
    assert "black_frames" not in report.checks_passed
    # Nothing was verified, so the report must not claim a pass.
    assert not report.overall_pass
    assert "ffmpeg unavailable" in report.check_errors["black_frames"]


def _mock_failed_subprocess(returncode: int, stderr: str):
    result = MagicMock()
    result.stderr = stderr
    result.returncode = returncode
    return result


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_ffmpeg_nonzero_exit_is_skip_not_pass(mock_run):
    """A video-only file has no audio for silencedetect: ffmpeg exits non-zero
    with empty detector output. That used to be recorded as 'silence passed'."""
    mock_run.return_value = _mock_failed_subprocess(
        234, "Output file does not contain any stream\n"
    )
    report = run_qc(SAMPLE_PATH, checks=["silence", "clipping"])

    assert report.checks_passed == []
    assert sorted(report.checks_skipped) == ["clipping", "silence"]
    assert "exited 234" in report.check_errors["silence"]
    assert not report.overall_pass


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_clipping_needs_astats_numbers(mock_run):
    mock_run.return_value = _mock_subprocess("size=N/A time=00:00:01.00\n")
    report = run_qc(SAMPLE_PATH, checks=["clipping"])

    assert "clipping" in report.checks_skipped
    assert "Peak level dB" in report.check_errors["clipping"]


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_full_scale_without_flat_tops_is_not_clipping(mock_run):
    mock_run.return_value = _mock_subprocess(
        "Peak level dB: -0.050000\nFlat factor: 0.000000\n"
    )
    report = run_qc(SAMPLE_PATH, checks=["clipping"])

    assert report.audio_clipping is False
    assert report.audio_peak_db == pytest.approx(-0.05)


def test_missing_file_size_is_skip(tmp_path):
    report = run_qc(tmp_path / "nope.mp4", checks=["file_size"])
    assert "file_size" in report.checks_skipped
    assert not report.overall_pass


# --- clean file passes all --------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_clean_file_passes_all(mock_run, tmp_path):
    mock_run.return_value = _mock_subprocess(CLEAN_STDERR)
    render = tmp_path / "render.mp4"
    render.write_bytes(b"\0" * 4096)
    mock_loudness = MagicMock(return_value={"input_i": -14.0, "input_tp": -2.0, "input_lra": 6.0})

    with patch(
        "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.measure_loudness",
        mock_loudness,
        create=True,
    ):
        report = run_qc(render)

    assert report.overall_pass
    assert len(report.checks_failed) == 0
    assert len(report.checks_passed) == len(ALL_CHECKS)


# --- ROADMAP next #5: silence that matters, loudness target, profile -------

def _silence_stderr(runs, duration=None):
    lines = []
    if duration is not None:
        h, rem = divmod(duration, 3600)
        m, s = divmod(rem, 60)
        lines.append(f"  Duration: {int(h):02d}:{int(m):02d}:{s:05.2f}, start: 0.000000, bitrate: 128 kb/s")
    for start, end in runs:
        lines.append(f"[silencedetect @ 0x1] silence_start: {start}")
        lines.append(f"[silencedetect @ 0x1] silence_end: {end} | silence_duration: {end - start}")
    return "\n".join(lines) + "\n"


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_single_short_pause_passes(mock_run):
    """A 1.2 s pause mid-video is a normal tutorial pause, not a failure."""
    mock_run.return_value = _mock_subprocess(_silence_stderr([(30.0, 31.2)], duration=120.0))
    report = run_qc(SAMPLE_PATH, checks=["silence"])
    assert len(report.silence_regions) == 1  # still reported
    assert "silence" in report.checks_passed
    assert report.silence_longest_seconds == pytest.approx(1.2)


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_many_short_pauses_pass_below_ratio(mock_run):
    runs = [(10.0 * i + 5, 10.0 * i + 6.5) for i in range(10)]  # 15 s of 120 s
    mock_run.return_value = _mock_subprocess(_silence_stderr(runs, duration=120.0))
    report = run_qc(SAMPLE_PATH, checks=["silence"])
    assert "silence" in report.checks_passed
    assert report.silence_total_seconds == pytest.approx(15.0)


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_long_run_fails(mock_run):
    mock_run.return_value = _mock_subprocess(_silence_stderr([(40.0, 44.0)], duration=120.0))
    report = run_qc(SAMPLE_PATH, checks=["silence"])
    assert "silence" in report.checks_failed
    assert "longest" in report.check_notes["silence"]


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_mostly_silent_fails_on_total(mock_run):
    runs = [(3.4 * i, 3.4 * i + 1.8) for i in range(1, 18)]  # 30.6 s of 60 s, each 1.8 s
    mock_run.return_value = _mock_subprocess(_silence_stderr(runs, duration=60.0))
    report = run_qc(SAMPLE_PATH, checks=["silence"])
    assert "silence" in report.checks_failed
    assert "total" in report.check_notes["silence"]
    assert "longest" not in report.check_notes["silence"]


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_dead_air_at_start_fails(mock_run):
    mock_run.return_value = _mock_subprocess(_silence_stderr([(0.0, 1.6)], duration=120.0))
    report = run_qc(SAMPLE_PATH, checks=["silence"])
    assert "silence" in report.checks_failed
    assert report.check_notes["silence"].endswith("at the start (> 1 s)")


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_dead_air_at_end_fails(mock_run):
    mock_run.return_value = _mock_subprocess(_silence_stderr([(118.4, 120.0)], duration=120.0))
    report = run_qc(SAMPLE_PATH, checks=["silence"])
    assert "silence" in report.checks_failed
    assert report.check_notes["silence"].endswith("at the end (> 1 s)")


def _loudness(i, tp=-3.0):
    return MagicMock(return_value={"input_i": i, "input_tp": tp, "input_lra": 7.0})


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
@pytest.mark.parametrize("lufs, passes", [(-14.0, True), (-16.0, True), (-18.0, True),
                                          (-10.0, True), (-18.5, False), (-9.5, False),
                                          (-20.0, False)])
def test_loudness_against_default_target(mock_run, lufs, passes):
    """Default target -14 LUFS integrated, +/-4 LU (the guide's -18..-10
    window). -20 (quiet) and -9.5 (over-loud) used to pass: only < -24 failed."""
    with patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.measure_loudness", _loudness(lufs)):
        report = run_qc(SAMPLE_PATH, checks=["loudness"])
    assert report.loudness_target_lufs == -14.0
    assert report.loudness_delta_lu == pytest.approx(lufs + 14.0)
    assert ("loudness" in report.checks_passed) is passes


@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_loudness_target_configurable(mock_run):
    with patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.measure_loudness", _loudness(-23.0)):
        report = run_qc(SAMPLE_PATH, checks=["loudness"], target_lufs=-23.0, lufs_tolerance=1.0)
    assert "loudness" in report.checks_passed
    assert report.loudness_delta_lu == pytest.approx(0.0)


def _asset(width=1920, height=1080, fps=30.0, codec="h264"):
    a = MagicMock()
    a.width, a.height, a.fps, a.video_codec = width, height, fps, codec
    return a


def test_profile_match_passes():
    from workshop_video_brain.edit_mcp.pipelines.qc_check import ExpectedProfile
    exp = ExpectedProfile(width=1920, height=1080, fps=30.0, video_codec="libx264", source="t")
    with patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media", return_value=_asset()):
        report = run_qc(SAMPLE_PATH, expected_profile=exp)
    assert "profile" in report.checks_passed or "profile" in report.checks_failed  # ran by default
    report = None
    with patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media", return_value=_asset()):
        report = run_qc(SAMPLE_PATH, checks=["profile"], expected_profile=exp)
    assert report.checks_passed == ["profile"]
    assert report.profile_mismatches == []


@pytest.mark.parametrize("asset, field", [
    (_asset(width=1280, height=720), "resolution"),
    (_asset(fps=25.0), "fps"),
    (_asset(codec="hevc"), "codec"),
])
def test_profile_mismatch_fails(asset, field):
    from workshop_video_brain.edit_mcp.pipelines.qc_check import ExpectedProfile
    exp = ExpectedProfile(width=1920, height=1080, fps=30.0, video_codec="libx264", source="t")
    with patch("workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.probe_media", return_value=asset):
        report = run_qc(SAMPLE_PATH, checks=["profile"], expected_profile=exp)
    assert report.checks_failed == ["profile"]
    assert any(m.startswith(field) for m in report.profile_mismatches), report.profile_mismatches


def test_profile_requested_without_expected_is_skip():
    report = run_qc(SAMPLE_PATH, checks=["profile"])
    assert report.checks_skipped == ["profile"]
    assert "profile" in report.check_errors
    assert report.overall_pass is False


def test_expected_from_render_profile():
    from workshop_video_brain.edit_mcp.pipelines.qc_check import expected_from_render_profile
    exp = expected_from_render_profile("youtube-1080p")
    assert (exp.width, exp.height, exp.video_codec) == (1920, 1080, "libx264")
    assert exp.fps == pytest.approx(30.0)
