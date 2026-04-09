"""TDD tests for QC automation pipeline."""
from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from workshop_video_brain.core.models.qc import QCReport, TimeRange
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

CLIPPING_STDERR = "Flat_factor detected on channel 0\n"

CLEAN_STDERR = "size=N/A time=00:01:00.00 bitrate=N/A speed=120x\n"


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
    assert report.overall_pass  # skipped != failed


# --- clean file passes all --------------------------------------------------

@patch("workshop_video_brain.edit_mcp.pipelines.qc_check.subprocess.run")
def test_clean_file_passes_all(mock_run):
    mock_run.return_value = _mock_subprocess(CLEAN_STDERR)
    mock_loudness = MagicMock(return_value={"input_i": -14.0, "input_tp": -2.0, "input_lra": 6.0})

    with patch(
        "workshop_video_brain.edit_mcp.adapters.ffmpeg.probe.measure_loudness",
        mock_loudness,
        create=True,
    ):
        report = run_qc(SAMPLE_PATH)

    assert report.overall_pass
    assert len(report.checks_failed) == 0
    assert len(report.checks_passed) == len(ALL_CHECKS)
